"""Minimal asyncio-based IRC client (RFC 1459 compliant enough for bots).

Designed for experimentation – readable rather than bullet-proof.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import ssl
from pathlib import Path
from typing import Optional
import os
import time
import yaml

from core.llm_proxy import get_client

logger = logging.getLogger("irc_raw")

CRLF = "\r\n"
RATE_LIMIT = 1.1  # seconds between messages to avoid floods



class IRCBot:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.nick = cfg["nick"]
        self.channel = cfg["channel"]
        self.host = cfg.get("host", "localhost")
        self.port = int(cfg.get("port", 6667))
        self.tls = bool(cfg.get("tls", False))
        self.password = cfg.get("password")
        self.client = get_client(cfg.get("llm_node"))
        self.model = cfg.get("model", "llama3.2:3b")
        self.reply_to_all = bool(cfg.get("reply_to_all", False))
        self.last_activity = 0.0
        self.is_connected = False
        self.connection_timeout = float(cfg.get("connection_timeout", 15.0))  # Default 15 second timeout
        self.max_connection_attempts = int(cfg.get("max_connection_attempts", 3))  # Max retry attempts

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._send_lock = asyncio.Lock()
        self._last_sent = 0.0
        self._active_tasks = set()
        self._connection_event = asyncio.Event()
        self._shutdown_event = asyncio.Event()
        self._connection_attempts = 0

    # ---------------------------------------------------------------------
    # IRC primitives
    # ---------------------------------------------------------------------
    async def send_line(self, line: str) -> None:
        async with self._send_lock:
            delta = max(0.0, RATE_LIMIT - (asyncio.get_running_loop().time() - self._last_sent))
            if delta:
                await asyncio.sleep(delta)
            logger.debug(">>> %s", line)
            assert self.writer is not None
            self.writer.write((line + CRLF).encode())
            await self.writer.drain()
            self._last_sent = asyncio.get_running_loop().time()

    # ------------------------------------------------------------------

    async def _connect_with_timeout(self):
        """Establish connection with timeout and retry logic."""
        ssl_ctx = ssl.create_default_context() if self.tls else None
        
        try:
            # Create connection with timeout
            connect_task = asyncio.open_connection(
                self.host, self.port, ssl=ssl_ctx)
            
            # Wait for connection with timeout
            self.reader, self.writer = await asyncio.wait_for(
                connect_task,
                timeout=self.connection_timeout
            )
            logger.info("Successfully connected to %s:%s", self.host, self.port)
            return True
            
        except asyncio.TimeoutError:
            logger.error("Connection to %s:%s timed out after %.1f seconds", 
                        self.host, self.port, self.connection_timeout)
            await self._cleanup_connection()
            return False
            
        except (ConnectionRefusedError, ConnectionResetError, ConnectionError, OSError) as e:
            logger.warning("Connection error to %s:%s: %s", self.host, self.port, e)
            await self._cleanup_connection()
            return False

    async def connect(self):
        """Connect to IRC server with timeout and retry logic."""
        self._connection_attempts = 0
        base_delay = 2  # Initial delay in seconds
        
        while not self._shutdown_event.is_set() and \
              (self.max_connection_attempts == 0 or 
               self._connection_attempts < self.max_connection_attempts):
                
            self._connection_attempts += 1
            logger.info("Connection attempt %d/%d to %s:%s...", 
                       self._connection_attempts, 
                       self.max_connection_attempts if self.max_connection_attempts > 0 else '∞',
                       self.host, self.port)
            
            # Ensure any previous connection is cleaned up
            await self._cleanup_connection()
            
            # Try to establish connection with timeout
            if not await self._connect_with_timeout():
                # Calculate exponential backoff
                delay = min(base_delay * (2 ** (self._connection_attempts - 1)), 60)
                logger.info("Retrying in %.1f seconds...", delay)
                await asyncio.sleep(delay)
                continue
                
            # Connection successful, proceed with registration
            try:
                # Set up reader task
                self._connection_event.clear()
                self._active_tasks.add(asyncio.create_task(self._read_loop()))
                
                # Send registration
                if self.password:
                    await self.send_line(f"PASS {self.password}")
                await self.send_line(f"NICK {self.nick}")
                await self.send_line(f"USER {self.nick} 0 * :AI Bot")
                
                # Wait for successful registration with timeout
                try:
                    await asyncio.wait_for(
                        self._connection_event.wait(),
                        timeout=self.connection_timeout
                    )
                    logger.info("Successfully registered with IRC server")
                    
                    # Join channel
                    await self.send_line(f"JOIN {self.channel}")
                    await asyncio.sleep(1)  # Small delay after JOIN
                    
                    # Run main loop
                    await self._main_loop()
                    
                except asyncio.TimeoutError as e:
                    logger.error("Registration with IRC server timed out")
                    if not self._shutdown_event.is_set():
                        logger.error("Max connection attempts (%d) reached. Giving up.", 
                                    self.max_connection_attempts)
                    await self._cleanup_connection()
                    if retry_count >= self.max_connection_attempts:
                        raise ConnectionError("Max reconnection attempts reached") from e
                    continue
                    
                except (ConnectionResetError, ConnectionError, OSError) as e:
                    logger.warning("Connection error during registration: %s", e)
                    await self._cleanup_connection()
                    
                    if retry_count >= self.max_connection_attempts:
                        logger.error("Max reconnection attempts reached. Giving up.")
                        raise ConnectionError("Max reconnection attempts reached") from e
                    
                    # Exponential backoff with jitter
                    delay = min(5 * (2 ** (retry_count - 1)), 60)  # Cap at 60 seconds
                    jitter = random.uniform(0.5, 1.5)  # Add some randomness
                    sleep_time = delay * jitter
                    
                    logger.warning(
                        "Connection error: %s. "
                        "Attempting to reconnect in %.1f seconds "
                        "(attempt %d/%d)...",
                        str(e), sleep_time, retry_count + 1, self.max_connection_attempts
                    )
                    
                    # Wait before retrying
                    await asyncio.sleep(sleep_time)
                    continue
                    
            except asyncio.CancelledError:
                logger.info("Connection task cancelled")
                await self.disconnect("Bot shutting down")
                raise
                
            except Exception as e:
                logger.error("Unexpected error: %s", e, exc_info=True)
                await self._cleanup_connection()
                
                # Wait before retrying, but cap the delay
                await asyncio.sleep(min(5 * (retry_count + 1), 30))  # Max 30 seconds

    # ------------------------------------------------------------------
    async def disconnect(self, quit_message="Leaving"):
        """Properly disconnect from the IRC server with a QUIT message."""
        if not self.is_connected:
            return
            
        logger.info(f"Disconnecting from IRC with message: {quit_message}")
        self.is_connected = False
        
        try:
            # Send QUIT message if we have a writer
            if self.writer and not self.writer.is_closing():
                try:
                    await self.send_line(f"QUIT :{quit_message}")
                    # Give the QUIT message a chance to be sent
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Error sending QUIT message: {e}")
        finally:
            # Ensure cleanup happens even if sending QUIT fails
            await self._cleanup_connection()
    
    async def _cleanup_connection(self):
        """Clean up connection resources."""
        # Cancel any pending tasks
        tasks_to_cancel = list(self._active_tasks)
        self._active_tasks.clear()
        
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception) as e:
                    logger.debug("Task cancelled during cleanup: %s", e)
        
        # Close writer if it exists
        if self.writer is not None:
            try:
                # Send QUIT message if possible
                try:
                    self.writer.write(b'QUIT :Connection closed\r\n')
                    await asyncio.wait_for(self.writer.drain(), timeout=1.0)
                except (ConnectionError, asyncio.TimeoutError, OSError) as e:
                    logger.debug("Error sending QUIT: %s", e)
                
                # Close the connection
                self.writer.close()
                if hasattr(self.writer, 'wait_closed'):
                    try:
                        await asyncio.wait_for(self.writer.wait_closed(), timeout=2.0)
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.debug("Error waiting for writer to close: %s", e)
            except Exception as e:
                logger.debug("Error during connection cleanup: %s", e, exc_info=True)
            finally:
                self.writer = None
                self.reader = None
                self.is_connected = False
                self._connection_event.clear()

    async def _read_loop(self):
        """Background task to read from the socket."""
        while self.is_connected and not self._shutdown_event.is_set():
            try:
                if self.reader is None or self.reader.at_eof():
                    logger.warning("Connection closed by server")
                    break
                    
                line = await asyncio.wait_for(
                    self.reader.readline(),
                    timeout=self.connection_timeout
                )
                
                if not line:
                    logger.warning("Connection closed by server (empty line)")
                    break
                    
                line = line.decode('utf-8', errors='replace').strip()
                if not line:
                    continue
                    
                logger.debug("<<< %s", line)
                self.last_activity = time.time()
                
                # Process PING/PONG
                if line.startswith('PING '):
                    try:
                        await self.send_line(f"PONG {line[5:]}")
                    except (ConnectionError, OSError) as e:
                        logger.error("Failed to send PONG: %s", e)
                        break
                    continue
                    
                # Process other messages
                parts = line.split()
                if len(parts) < 2:
                    continue
                    
                # Handle server messages
                if parts[0] == 'ERROR' and 'Closing Link:' in line:
                    logger.error("Server closed connection: %s", line)
                    break
                    
                # Handle registration responses
                if parts[1] == '001':  # Welcome message
                    logger.info("Successfully registered with IRC server")
                    self.is_connected = True
                    self._connection_event.set()
                    
                # Handle PRIVMSG (channel and private messages)
                elif parts[1] == 'PRIVMSG':
                    try:
                        self._active_tasks.add(asyncio.create_task(self._handle_privmsg(parts)))
                    except Exception as e:
                        logger.error("Error handling PRIVMSG: %s", e, exc_info=True)
                        
            except asyncio.TimeoutError:
                logger.error("Read timeout - no data received for %.1f seconds", 
                            self.connection_timeout)
                break
                
            except (ConnectionResetError, ConnectionError, OSError) as e:
                logger.error("Connection error in read loop: %s", e)
                break
                
            except asyncio.CancelledError:
                logger.debug("Read loop cancelled")
                raise
                
            except Exception as e:
                logger.exception("Unexpected error in read loop")
                await asyncio.sleep(1)  # Prevent tight loop on errors
                
        # Clean up if we exit the read loop
        self.is_connected = False
        if not self._shutdown_event.is_set():
            await self._cleanup_connection()

    async def _main_loop(self):
        """Main message processing loop."""
        try:
            while self.is_connected and not self._shutdown_event.is_set():
                # Just sleep and let the _read_loop handle everything
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.debug("Main loop cancelled")
            raise
        except Exception as e:
            logger.error("Error in main loop: %s", e, exc_info=True)
            await self._cleanup_connection()

    async def _background_activity(self):
        """Background task that sends periodic messages when the channel is quiet."""
        while self.is_connected and not self._shutdown_event.is_set():
            try:
                # Wait for a period of inactivity
                await asyncio.sleep(random.uniform(120, 300))  # 2-5 minutes
                
                if not self.is_connected or self._shutdown_event.is_set():
                    break
                    
                # Only send if channel has been quiet for a while
                if time.time() - self.last_activity > 60:  # 1 minute of inactivity
                    # Get a random message from the bot's personality
                    message = await self._generate_proactive_message()
                    if message:
                        try:
                            await self.send_line(f"PRIVMSG {self.channel} :{message}")
                        except (ConnectionError, OSError) as e:
                            logger.error("Connection lost in background activity: %s", e)
                            break
                            
            except asyncio.CancelledError:
                logger.debug("Background activity cancelled")
                raise
                
            except Exception as e:
                logger.error("Error in background activity: %s", e, exc_info=True)
                await asyncio.sleep(10)  # Prevent tight loop on errors

    # ------------------------------------------------------------------
    async def _handle_line(self, line: str):
        logger.debug("<<< %s", line)
        if line.startswith("PING"):
            await self.send_line("PONG " + line.split(" ", 1)[1])
            return

        parts = line.split(" ")
        if len(parts) < 2:
            return
        cmd = parts[1]

        if cmd == "001":  # welcome
            await self.send_line(f"JOIN {self.channel}")
        elif cmd == "PRIVMSG":
            prefix = parts[0]
            user = prefix.split("!", 1)[0][1:]
            target = parts[2]
            msg = " ".join(parts[3:])[1:]  # drop leading :

            await self._maybe_respond(user, target, msg)

    # ------------------------------------------------------------------
    async def _maybe_respond(self, user: str, target: str, msg: str):
        # Ignore our own messages
        if user.lower() == self.nick.lower():
            return
            
        # Update last activity time
        self.last_activity = asyncio.get_event_loop().time()
        
        # Decide whether to reply
        should = False
        if target.startswith("#"):
            # Reply to direct mentions or if reply_to_all is True
            if self.nick.lower() in msg.lower() or self.reply_to_all:
                should = True
        else:  # direct PM
            should = True
            
        if not should:
            return

        try:
            # Generate reply with context
            prompt = [
                {"role": "system", "content": self.cfg.get("prompt", "You are a helpful droid.")},
                {"role": "user", "content": msg},
            ]
            
            # Add some personality and context awareness
            prompt.append({
                "role": "system",
                "content": "You are in an IRC channel. Keep your responses concise and in character."
            })
            
            # Generate the response
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=prompt,
                max_tokens=150,
                temperature=0.7 if self.reply_to_all else 0.5
            )
            
            reply = completion.choices[0].message.content.strip()
            if not reply:
                reply = "..."  # Fallback response
                
        except Exception as exc:
            logger.error(f"Error generating response: {exc}")
            reply = "[I'm having trouble thinking of a response right now]"

        # Add a natural delay before responding
        await asyncio.sleep(random.uniform(1, 3))  # Reduced delay for more natural flow
        
        # If it was a private message to us, echo back to the *sender* instead of ourselves.
        reply_target = user if not target.startswith("#") else target
        
        try:
            await self.send_line(f"PRIVMSG {reply_target} :{reply}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")


# ---------------------------------------------------------------------------
async def main(cfg_path: Path):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
    with cfg_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    bot = IRCBot(cfg)
    while True:
        try:
            await bot.connect()
        except (ConnectionError, ssl.SSLError, OSError) as e:
            logger.warning("Disconnected: %s. Reconnecting in 5s…", e)
            await asyncio.sleep(5)
        else:
            logger.warning("Connection closed. Reconnecting in 5s…")
            await asyncio.sleep(5)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Run a raw-socket IRC AI bot")
    p.add_argument("config", type=Path, help="YAML config file")
    args = p.parse_args()
    asyncio.run(main(args.config))
