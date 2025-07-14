"""Reusable asyncio-based IRC bot engine.

Usage:
    python -m bots.irc_bot path/to/bot.yml

The YAML config must contain at least:
    nick: R2D2
    channel: "#cantina"
    prompt: path/to/prompt.md   # or inline string

Optional keys:
    host, port, tls, password – connection settings
    llm_node – IP / URL / env prefix for llm_proxy.get_client()
    model – LLM model name (default: llama3.2:3b)
    temperature – sampling temperature (default: 0.7)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import ssl
from pathlib import Path
from typing import Optional

import yaml
from openai.types.chat import ChatCompletion
import time
import socket
from collections import deque

from core.llm_proxy import get_client

logger = logging.getLogger("irc_bot")
CRLF = "\r\n"
RATE_LIMIT = 2.0  # seconds between messages


class IRCBot:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.nick: str = cfg["nick"]
        self.channel: str = cfg["channel"]
        self.host: str = cfg.get("host", "localhost")
        self.port: int = int(cfg.get("port", 6667))
        self.tls: bool = bool(cfg.get("tls", False))
        self.password: Optional[str] = cfg.get("password")
        self.client = get_client(cfg.get("llm_node"))
        self.model: str = cfg.get("model", "llama3.2:3b")
        self.temperature: float = float(cfg.get("temperature", 0.7))
        self.reply_to_all: bool = bool(cfg.get("reply_to_all", True))
        self.chatter: bool = bool(cfg.get("chatter", True))
        self.conversation_history: list[dict[str, str]] = []
        self.max_history: int = 10  # Keep last 10 messages for context

        prompt_val = cfg.get("prompt")
        if prompt_val is None:
            raise ValueError("Config must include 'prompt' (file path or string).")
        prompt_path = Path(prompt_val)
        if prompt_path.exists():
            self.system_prompt = prompt_path.read_text(encoding="utf-8")
        else:
            self.system_prompt = str(prompt_val)

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._send_lock = asyncio.Lock()
        self._last_sent = 0.0
        # Track processed lines to avoid duplicate handling
        self._seen_messages = deque(maxlen=100)

    # ------------------------------------------------------------- IRC helpers
    async def send_line(self, line: str) -> None:
        """Send a line, reconnecting if needed."""
        try:
            async with self._send_lock:
                delta = max(0.0, RATE_LIMIT - (asyncio.get_running_loop().time() - self._last_sent))
                if delta:
                    await asyncio.sleep(delta)
                logger.debug(">>> %s", line)
                if self.writer is None or self.writer.is_closing():
                    logger.warning("Writer not connected, attempting to reconnect before sending.")
                    await self._reconnect()
                    if self.writer is None or self.writer.is_closing():
                        logger.error("Reconnect failed, writer still not connected.")
                        raise ConnectionError("Writer is not connected after reconnect")
                self.writer.write((line + CRLF).encode())
                await self.writer.drain()
                self._last_sent = asyncio.get_running_loop().time()
        except (ConnectionResetError, BrokenPipeError) as e:
            logger.error(f"Connection error in send_line: {e}")
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
            raise

    # ---------------------------------------------------------------- connect
    async def connect(self):
        try:
            ssl_ctx = ssl.create_default_context() if self.tls else None
            logger.info(f"Attempting to connect to {self.host}:{self.port}...")
            
            # Only include ssl_handshake_timeout if using SSL/TLS
            connect_kwargs = {
                'host': self.host,
                'port': self.port,
                'ssl': ssl_ctx
            }
            if self.tls:
                connect_kwargs['ssl_handshake_timeout'] = 10.0
            
            logger.debug(f"Opening connection with params: {connect_kwargs}")
            self.reader, self.writer = await asyncio.open_connection(**connect_kwargs)
            # Enable TCP keepalive to maintain connection
            sock = self.writer.get_extra_info('socket')
            if sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                logger.debug("Enabled TCP keepalive on socket")
            logger.info("Successfully connected to %s:%s", self.host, self.port)
            
            try:
                logger.debug("Starting IRC handshake...")
                if self.password:
                    logger.debug("Sending PASS command")
                    await self.send_line(f"PASS {self.password}")
                
                logger.debug(f"Sending NICK {self.nick}")
                await self.send_line(f"NICK {self.nick}")
                
                logger.debug(f"Sending USER command for {self.nick}")
                await self.send_line(f"USER {self.nick} 0 * :AI Bot")
                
                logger.debug("Entering main loop")
                await self._main_loop()
                
            except (ConnectionResetError, BrokenPipeError) as e:
                logger.error(f"Connection error during handshake: {e}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"Unexpected error during handshake: {e}", exc_info=True)
                raise
                
        except Exception as e:
            logger.error(f"Failed to connect to {self.host}:{self.port}: {e}", exc_info=True)
            if self.writer:
                try:
                    logger.debug("Closing writer...")
                    self.writer.close()
                    await self.writer.wait_closed()
                    logger.debug("Writer closed successfully")
                except Exception as close_error:
                    logger.error(f"Error closing writer: {close_error}", exc_info=True)
            raise

    async def _reconnect(self) -> None:
        """Attempt to reconnect to the IRC server."""
        # Clear history on reconnect to prevent receive-queue growth and repetitive context
        self.conversation_history.clear()
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                if self.writer:
                    self.writer.close()
                    await self.writer.wait_closed()
                
                # Connect to the server with timeout
                try:
                    # Use same SSL context as initial connect
                    ssl_ctx = ssl.create_default_context() if self.tls else None
                    connect_kwargs = {'host': self.host, 'port': self.port, 'ssl': ssl_ctx}
                    if self.tls:
                        connect_kwargs['ssl_handshake_timeout'] = 10.0
                    self.reader, self.writer = await asyncio.wait_for(
                        asyncio.open_connection(**connect_kwargs),
                        timeout=10.0
                    )
                    logger.info(f"Connected to {self.host}:{self.port}")
                except asyncio.TimeoutError:
                    raise ConnectionError(f"Connection to {self.host}:{self.port} timed out")
                except Exception as e:
                    raise ConnectionError(f"Failed to connect to {self.host}:{self.port}: {e}")
                
                # Perform IRC handshake
                logger.debug("Initiating IRC handshake...")
                try:
                    if self.password:
                        await self.send_line(f"PASS {self.password}")
                    
                    await self.send_line(f"NICK {self.nick}")
                    await self.send_line(f"USER {self.nick} 0 * :{self.nick} IRC Bot")
                    # Rejoin channel after reconnect
                    logger.info(f"Joining channel {self.channel} after reconnect")
                    await self.send_line(f"JOIN {self.channel}")
                    logger.debug("IRC handshake initiated")
                    
                    # Start the main loop
                    await self._main_loop()
                    return  # Success - exit the retry loop
                    
                except (ConnectionResetError, ConnectionAbortedError) as e:
                    last_error = e
                    logger.warning(f"Connection lost during handshake: {e}")
                    await self._close_connection()
                    
            except ConnectionError as e:
                last_error = e
                logger.warning(f"Connection attempt {attempt} failed: {e}")
                if attempt < max_attempts:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error during connection: {e}")
                await self._close_connection()
                if attempt >= max_attempts:
                    break
                await asyncio.sleep(1)
        
        # If we get here, all attempts failed
        raise ConnectionError(f"Failed to connect after {max_attempts} attempts. Last error: {last_error}")
    
    async def _close_connection(self):
        """Safely close the connection if it's open."""
        if self.writer and not self.writer.is_closing():
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                logger.debug(f"Error closing connection: {e}")
            finally:
                self.writer = None
                self.reader = None

    # ------------------------------------------------------------- main loop
    async def _main_loop(self):
        """Main loop for handling IRC messages."""
        assert self.reader is not None
        buffer = b""
        idle_task = None
        
        logger.debug("Starting main loop")
        
        # Start idle chatter task if enabled
        if self.chatter:
            logger.debug("Starting idle chatter task")
            idle_task = asyncio.create_task(self._idle_chatter())
        
        try:
            while True:
                logger.debug("Top of main loop iteration")
                # Read data with timeout
                try:
                    logger.debug("Waiting for data from server...")
                    chunk = await asyncio.wait_for(self.reader.read(4096), timeout=60.0)
                    logger.debug(f"Received {len(chunk) if chunk else 0} bytes from server")
                    
                    if not chunk:
                        logger.warning("Received empty chunk, server closed connection; raising to reconnect")
                        raise ConnectionError("Server closed connection")
                    
                    # Process received data
                    buffer += chunk
                    logger.debug(f"Buffer size: {len(buffer)} bytes")
                    
                    while b"\r\n" in buffer:
                        line_bytes, buffer = buffer.split(b"\r\n", 1)
                        try:
                            line = line_bytes.decode(errors="ignore")
                            logger.debug(f"Processing line: {line}")
                            await self._handle_line(line)
                        except Exception as e:
                            logger.error(f"Error processing line: {e}", exc_info=True)
                
                except asyncio.TimeoutError:
                    logger.debug("No data received, sending PING...")
                    try:
                        ping_msg = f"PING :{int(time.time())}"
                        logger.debug(f"Sending: {ping_msg}")
                        await self.send_line(ping_msg)
                    except Exception as e:
                        logger.error(f"Error sending PING: {e}", exc_info=True)
                        raise
                
                except (ConnectionResetError, ConnectionError) as e:
                    logger.error(f"Connection error in main loop: {e}", exc_info=True)
                    try:
                        await asyncio.sleep(5)
                        logger.debug("Attempting to reconnect after connection error...")
                        await self._reconnect()
                        logger.debug("Reconnected after connection error")
                    except Exception as reconnect_error:
                        logger.error(f"Failed to reconnect after connection error: {reconnect_error}")
                        raise
                
                except Exception as e:
                    logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                    await asyncio.sleep(5)
        
        except asyncio.CancelledError:
            logger.info("Main loop cancelled")
            raise
            
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}", exc_info=True)
            raise
            
        finally:
            logger.debug("Cleaning up main loop...")
            # Cleanup idle chatter task if it exists
            if idle_task and not idle_task.done():
                logger.debug("Cancelling idle chatter task...")
                idle_task.cancel()
                try:
                    await idle_task
                except (asyncio.CancelledError, Exception) as e:
                    logger.debug(f"Idle task cleanup: {e}")
            
            logger.debug("Main loop cleanup complete")

    # ---------------------------------------------------------- idle chatter
    async def _idle_chatter(self):
        """Background idle chatter: respond only to new user messages."""
        # Track previous user message count
        prev_user_count = sum(1 for m in self.conversation_history if m.get('role')=='user')
        while True:
            # Sleep before polling new messages
            await asyncio.sleep(random.uniform(300, 600))
            # Count current user messages
            user_msgs = [m for m in self.conversation_history if m.get('role')=='user']
            if len(user_msgs) <= prev_user_count:
                continue
            # Build context for LLM
            messages = [{'role':'system','content':self.system_prompt}]
            messages += [{'role':m['role'],'name':m.get('name'),'content':m['content']} for m in self.conversation_history[-5:]]
            try:
                resp = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=self.model,
                    messages=messages+[{'role':'user','content':'Add a relevant comment to the ongoing conversation.'}],
                    temperature=min(0.9, self.temperature+0.1),
                    max_tokens=100
                )
                thought = resp.choices[0].message.content.strip()
                if thought and len(thought) > 5:
                    await self.send_line(f"PRIVMSG {self.channel} :{thought}")
                    self._update_conversation('assistant', self.nick, thought)
            except Exception as exc:
                logger.debug(f"Idle chatter error: {exc}")
            prev_user_count = len(user_msgs)

    # ------------------------------------------------------------- line handler
    async def _handle_line(self, line: str):
        if not line:
            return

        # Skip duplicate lines to prevent duplicate responses
        if line in self._seen_messages:
            logger.debug(f"Skipping duplicate line: {line}")
            return
        self._seen_messages.append(line)

        logger.debug(f"Processing line: {line}")

        parts = line.split(" ")
        # Handle PING messages (with or without prefix)
        if parts[0] == "PING" or (parts[0].startswith(":") and len(parts) > 1 and parts[1] == "PING"):
            # Extract token (last parameter)
            token = parts[-1]
            logger.debug("Responding to PING")
            await self.send_line(f"PONG {token}")
            return

        if len(parts) < 2:
            return
        if len(parts) < 2:
            return

        # Extract prefix, command, and parameters
        prefix = parts[0] if parts[0].startswith(":") else None
        cmd_idx = 1 if prefix is not None else 0
        cmd = parts[cmd_idx] if len(parts) > cmd_idx else None
        params = parts[cmd_idx+1:] if len(parts) > cmd_idx+1 else []

        # Handle numeric replies (3-digit codes)
        if cmd.isdigit():
            code = int(cmd)
            # 001: Welcome message - we're now connected
            if code == 1:
                logger.info("Received welcome message, joining channel...")
                await self.send_line(f"JOIN {self.channel}")
            return

        # Handle server commands
        if cmd == "JOIN":
            # Format: :nick!user@host JOIN :#channel
            if not prefix:
                return
                
            # Extract the nick from the prefix
            nick = prefix.split("!", 1)[0][1:]  # Remove leading ':'
            channel = params[-1].lstrip(":") if params else ""
            
            # If it's us joining a channel
            if nick.lower() == self.nick.lower() and channel:
                logger.info(f"Successfully joined {channel}")
                await self.send_line(f"PRIVMSG {channel} :{self.nick} reporting in!")
                
        elif cmd == "PRIVMSG":
            # Format: :nick!user@host PRIVMSG #channel :message
            if len(params) < 2 or not prefix:
                return
                
            target = params[0]
            message = " ".join(params[1:])[1:]  # Remove leading ':'
            
            # Extract the nick from the prefix
            user = prefix.split("!", 1)[0][1:]  # Remove leading ':'
            
            # Don't respond to our own messages
            if user.lower() == self.nick.lower():
                return
                
            logger.info(f"Detected PRIVMSG: user={user}, target={target}, message={message}")
            logger.debug(f"Message from {user} in {target}: {message}")
            await self._maybe_respond(user, target, message)
            
            
            if len(self.conversation_history) > self.max_history:
                self.conversation_history = self.conversation_history[-self.max_history:]
                return

   
   
    def _update_conversation(self, role: str, name: str, content: str):
        """Update conversation history with new message."""
        self.conversation_history.append({
            "role": role,
            "name": name,
            "content": content
        })


    
    async def _maybe_respond(self, user: str, target: str, msg: str):
        """Generate and send a response if applicable, retrying send_line once on connection error."""
        if user.lower() == self.nick.lower():
            return
        self._update_conversation("user", user, msg)
        is_channel = target.startswith("#")
        should_respond = (not is_channel) or (self.nick.lower() in msg.lower()) or self.reply_to_all
        if not should_respond:
            return
        messages = [{"role": "system", "content": self.system_prompt}]
        for m in self.conversation_history:
            messages.append({"role": m["role"], "name": m.get("name"), "content": m["content"]})
        try:
            completion = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=150
            )
            reply = completion.choices[0].message.content.strip()
            self._update_conversation("assistant", self.nick, reply)
            await asyncio.sleep(random.uniform(1, 3))
            reply_target = user if not is_channel else target
            try:
                await self.send_line(f"PRIVMSG {reply_target} :{reply}")
            except ConnectionError:
                logger.warning("Send failed, reconnecting and retrying PRIVMSG send.")
                await self._reconnect()
                await self.send_line(f"PRIVMSG {reply_target} :{reply}")
        except Exception as exc:
            logger.error(f"Error generating response: {exc}")
            fallback = "[Had trouble thinking of a response]"
            try:
                await self.send_line(f"PRIVMSG {target} :{fallback}")
            except ConnectionError:
                logger.warning("Send failed, reconnecting and retrying fallback send.")
                await self._reconnect()
                await self.send_line(f"PRIVMSG {target} :{fallback}")
# ---------------------------------------------------------------------------
async def main(cfg_path: Path):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
    with cfg_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    bot = IRCBot(cfg)
    try:
        await bot.connect()
    except (ConnectionError, ssl.SSLError, OSError) as e:
        logger.error("Bot terminated: %s", e)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Run a YAML-configured IRC AI bot")
    p.add_argument("config", type=Path, help="YAML config file")
    args = p.parse_args()
    asyncio.run(main(args.config))
