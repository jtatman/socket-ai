"""Mock IRC server for testing IRC client functionality."""
import asyncio
import logging
import socket
import threading
from typing import Dict, List, Set, Optional

logger = logging.getLogger(__name__)

class MockIRCServer:
    """A simple mock IRC server for testing."""
    
    def __init__(self, host: str = '127.0.0.1', port: int = 16667):  # Changed from 6667 to avoid conflicts with real IRC servers
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        # Store client state: {writer: {'nick': str, 'user': str, 'registered': bool, 'hostname': str}}
        self.clients: Dict[asyncio.StreamWriter, dict] = {}
        self.channels: Dict[str, Set[asyncio.StreamWriter]] = {}
        self._stop_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._write_lock = asyncio.Lock()  # Lock for thread-safe writes
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle a new client connection."""
        client_addr = writer.get_extra_info('peername')
        client_id = f"client-{id(writer)}"
        
        # Initialize client state
        self.clients[writer] = {
            'nick': 'unknown',
            'user': None,
            'registered': False,
            'hostname': client_addr[0],
            'id': client_id
        }
        
        logger.info(f"New connection from {client_addr} (ID: {client_id})")
        
        try:
            # Main client loop
            while not self._stop_event.is_set() and not writer.is_closing():
                try:
                    # Read a line from the client with a timeout
                    data = await asyncio.wait_for(reader.readline(), timeout=30.0)
                    if not data:
                        logger.info(f"Client {client_id} disconnected")
                        break
                        
                    line = data.decode(errors='ignore').strip()
                    if not line:
                        continue
                        
                    logger.debug(f"Received from {client_id}: {line}")
                    
                    # Process the command
                    await self.process_command(line, writer, client_id)
                    
                except asyncio.TimeoutError:
                    logger.info(f"Connection timeout for client {client_id}")
                    break
                except ConnectionResetError:
                    logger.info(f"Connection reset by client {client_id}")
                    break
                except Exception as e:
                    logger.error(f"Error handling client {client_id}: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Unexpected error with client {client_id}: {e}")
        finally:
            await self.cleanup_client(writer)
    
    async def _send_welcome_messages(self, writer: asyncio.StreamWriter) -> None:
        """Send welcome messages to a newly registered client."""
        if writer not in self.clients:
            return
            
        client = self.clients[writer]
        if not client['registered']:
            return
            
        nick = client['nick']
        
        # Send welcome messages
        welcome_messages = [
            f":test.irc.server 001 {nick} :Welcome to the Internet Relay Network {nick}",
            f":test.irc.server 002 {nick} :Your host is test.irc.server, running version mock-1.0",
            f":test.irc.server 003 {nick} :This server was created {datetime.datetime.now().strftime('%a %b %d %Y')}",
            f":test.irc.server 004 {nick} test.irc.server mock-1.0 i o itkl mnpstrxcfhvz bklovq",
            f":test.irc.server 375 {nick} :- test.irc.server Message of the Day -",
            f":test.irc.server 372 {nick} :- Welcome to the test IRC server",
            f":test.irc.server 376 {nick} :End of /MOTD command"
        ]
        
        for msg in welcome_messages:
            await self.send_response(writer, msg)
    
    async def process_command(self, line: str, writer: asyncio.StreamWriter, client_id: str) -> None:
        """Process an IRC command."""
        if not line.strip() or writer.is_closing():
            return
            
        parts = line.split()
        if not parts:
            return
            
        cmd = parts[0].upper()
        params = parts[1:]
        
        # Get client state
        client = self.clients.get(writer)
        if not client:
            logger.warning(f"Received command from unknown client: {cmd}")
            return
            
        current_nick = client['nick']
        logger.debug(f"Processing command from {client_id} (nick: {current_nick}): {cmd} {params}")
        
        try:
            if cmd == "NICK":
                if not params:
                    await self.send_response(writer, f":test.irc.server 431 {current_nick} :No nickname given")
                    return
                    
                new_nick = params[0]
                old_nick = client['nick']
                
                # Update client state
                client['nick'] = new_nick
                logger.info(f"Client {client_id} changed nick from {old_nick} to {new_nick}")
                
                # If client was already registered, send NICK change notification
                if client['registered']:
                    await self.send_response(writer, f":{old_nick} NICK {new_nick}")
                # Otherwise, check if we can complete registration
                elif client['user'] is not None:
                    await self._complete_registration(writer)
                
            elif cmd == "USER":
                if len(params) < 4:
                    await self.send_response(writer, f":test.irc.server 461 {current_nick} USER :Not enough parameters")
                    return
                    
                username, hostname, servername, realname = params[0:4]
                logger.info(f"Client {client_id} identified as {username}@{hostname} : {realname}")
                
                # Update client state
                client.update({
                    'user': username,
                    'hostname': hostname,
                    'realname': realname
                })
                
                # If we already have a nick, complete registration
                if client['nick'] != 'unknown':
                    await self._complete_registration(writer)
                
            elif cmd == "JOIN":
                if not client['registered']:
                    await self.send_response(writer, f":test.irc.server 451 {current_nick} :You have not registered")
                    return
                    
                if not params:
                    await self.send_response(writer, f":test.irc.server 461 {current_nick} JOIN :Not enough parameters")
                    return
                    
                channel = params[0].lower()
                if not channel.startswith('#'):
                    channel = '#' + channel
                    
                # Create channel if it doesn't exist
                if channel not in self.channels:
                    self.channels[channel] = set()
                    
                # Add client to channel
                self.channels[channel].add(writer)
                logger.info(f"Client {client_id} ({current_nick}) joined {channel}")
                
                # Send join notification to the client
                await self.send_response(writer, f":{current_nick}!{client['user']}@{client['hostname']} JOIN {channel}")
                
                # Send channel topic (empty for now)
                await self.send_response(writer, f":test.irc.server 332 {current_nick} {channel} :No topic is set")
                
                # Send names list (just the joining user for now)
                await self.send_response(writer, f":test.irc.server 353 {current_nick} = {channel} :{current_nick}")
                await self.send_response(writer, f":test.irc.server 366 {current_nick} {channel} :End of /NAMES list")
                    
            elif cmd == "PING":
                # Respond to PING with PONG
                if params:
                    await self.send_response(writer, f"PONG {params[0]}")
                else:
                    await self.send_response(writer, f"PONG :{self.host}")
                    
            elif cmd == "PRIVMSG":
                if not client['registered']:
                    await self.send_response(writer, f":test.irc.server 451 {current_nick} :You have not registered")
                    return
                    
                if len(params) < 2:
                    await self.send_response(writer, f":test.irc.server 411 {current_nick} :No recipient given (PRIVMSG)")
                    return
                    
                targets = params[0].split(',')
                message = ' '.join(params[1:]).lstrip(':')
                
                for target in targets:
                    logger.info(f"Message from {current_nick} to {target}: {message}")
                    
                    if target.startswith('#'):
                        # Channel message
                        if target in self.channels:
                            for client_writer in self.channels[target]:
                                if client_writer != writer:  # Don't echo back to sender
                                    await self.send_response(
                                        client_writer, 
                                        f":{current_nick}!{client['user']}@{client['hostname']} PRIVMSG {target} :{message}"
                                    )
                    else:
                        # Private message (in mock server, just echo back to sender)
                        await self.send_response(
                            writer,
                            f":{current_nick}!{client['user']}@{client['hostname']} PRIVMSG {target} :{message}"
                        )
                        
            elif cmd == "QUIT":
                reason = params[0] if params else "Client quit"
                logger.info(f"Client {client_id} ({current_nick}) quit: {reason}")
                await self.cleanup_client(writer)
                
            elif cmd == "PART":
                if not params:
                    await self.send_response(writer, f":test.irc.server 461 {current_nick} PART :Not enough parameters")
                    return
                    
                channels = params[0].split(',')
                for channel in channels:
                    if channel in self.channels and writer in self.channels[channel]:
                        self.channels[channel].remove(writer)
                        await self.send_response(writer, f":{current_nick}!{client['user']}@{client['hostname']} PART {channel}")
                        
            else:
                logger.debug(f"Unhandled command: {cmd} {params}")
                
        except Exception as e:
            logger.error(f"Error processing command '{cmd} {params}' from {client_id}: {e}")
    
    async def cleanup_client(self, writer: asyncio.StreamWriter) -> None:
        """Clean up a client connection."""
        if writer not in self.clients:
            return
            
        client = self.clients[writer]
        client_id = client['id']
        nick = client['nick']
        
        logger.info(f"Cleaning up client {client_id} ({nick})")
        
        # Notify channels that user is leaving
        for channel, clients in list(self.channels.items()):
            if writer in clients:
                # Send PART message to other clients in the channel
                for other_writer in list(clients):
                    if other_writer != writer and not other_writer.is_closing():
                        try:
                            await self.send_response(
                                other_writer,
                                f":{nick}!{client['user']}@{client['hostname']} PART {channel} :Client disconnected"
                            )
                        except Exception as e:
                            logger.debug(f"Error notifying channel {channel} about PART: {e}")
                
                # Remove from channel
                clients.discard(writer)
                if not clients:  # If channel is empty, remove it
                    del self.channels[channel]
        
        # Remove from clients dict
        if writer in self.clients:
            del self.clients[writer]
        
        # Close the writer
        if not writer.is_closing():
            try:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Error closing writer: {e}")
                try:
                    if hasattr(writer, 'transport') and writer.transport:
                        writer.transport.abort()
                except Exception as e:
                    logger.debug(f"Error aborting transport: {e}")
            finally:
                # Ensure we don't try to use this writer again
                if writer in self.clients:
                    del self.clients[writer]
    
    async def _complete_registration(self, writer: asyncio.StreamWriter) -> None:
        """Complete client registration after both NICK and USER have been received."""
        if writer not in self.clients or self.clients[writer]['registered']:
            return
            
        client = self.clients[writer]
        if client['nick'] == 'unknown' or client['user'] is None:
            return
            
        # Mark client as registered
        client['registered'] = True
        logger.info(f"Client {client['id']} registered as {client['nick']}")
        
        # Send welcome messages
        await self._send_welcome_messages(writer)
    
    async def send_response(self, writer: asyncio.StreamWriter, response: str) -> None:
        """Send a response to a client."""
        if writer.is_closing():
            return
            
        try:
            # Use a lock to prevent concurrent writes to the same writer
            async with self._write_lock:
                writer.write(f"{response}\r\n".encode())
                await writer.drain()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            logger.debug(f"Connection lost while sending response to client")
            await self.cleanup_client(writer)
        except Exception as e:
            logger.error(f"Error sending response to client: {e}")
    
    async def start_async(self) -> None:
        """Start the mock server asynchronously."""
        self.server = await asyncio.start_server(
            self.handle_client,  # Fixed: Use the correct method name
            host=self.host,
            port=self.port,
            reuse_address=True
        )
        self._server_task = asyncio.create_task(self._run_server())
        logger.info(f"Mock IRC server running on {self.host}:{self.port}")
        
    async def _run_server(self) -> None:
        """Run the server until it's stopped."""
        try:
            async with self.server:
                await self.server.serve_forever()
        except asyncio.CancelledError:
            logger.info("Server task cancelled")
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            await self.stop_async()
            
    async def stop_async(self) -> None:
        """Stop the server and clean up resources."""
        if hasattr(self, '_server_task') and not self._server_task.done():
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
                
        if hasattr(self, 'server') and self.server:
            self.server.close()
            await self.server.wait_closed()
            
        # Clean up all client connections
        for writer in list(self.clients.keys()):
            await self.cleanup_client(writer)
        
        async with self.server:
            await self.server.serve_forever()
    
    def start(self) -> None:
        """Start the mock server in a background thread."""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_server,
            daemon=True
        )
        self._thread.start()
    
    def _run_server(self) -> None:
        """Run the server in the background thread."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self.start_async())
    
    def stop(self) -> None:
        """Stop the mock server and clean up all resources."""
        logger.info("Stopping mock IRC server...")
        self._stop_event.set()
        
        # Close all client connections
        for writer in list(self.clients.keys()):
            try:
                writer.close()
                if self._loop and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(writer.close)
            except Exception as e:
                logger.debug(f"Error closing client writer: {e}")
        
        # Close the server
        if self.server:
            try:
                if self._loop and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(self.server.close)
                    # Schedule the event loop to stop after a short delay
                    self._loop.call_later(0.1, self._loop.stop)
            except Exception as e:
                logger.debug(f"Error closing server: {e}")
        
        # Clean up the event loop
        if self._loop and not self._loop.is_closed():
            try:
                # Cancel all tasks
                pending = asyncio.all_tasks(loop=self._loop)
                for task in pending:
                    task.cancel()
                # Give tasks a chance to clean up
                if pending:
                    self._loop.run_until_complete(
                        asyncio.wait(pending, timeout=1.0, return_when=asyncio.ALL_COMPLETED)
                    )
                # Stop the loop
                if self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception as e:
                logger.debug(f"Error during loop cleanup: {e}")
        
        # Join the server thread
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():
                logger.warning("Server thread did not shut down cleanly")
        
        # Clear all data structures
        self.clients.clear()
        self.channels.clear()
        logger.info("Mock IRC server stopped")


# Singleton instance for easy access in tests
_mock_server: Optional[MockIRCServer] = None

def start_mock_server(host: str = '127.0.0.1', port: int = 16667) -> MockIRCServer:
    """Start a mock IRC server for testing."""
    global _mock_server
    if _mock_server is None:
        _mock_server = MockIRCServer(host, port)
        _mock_server.start()
    return _mock_server

def stop_mock_server() -> None:
    """Stop the mock IRC server if running and clean up resources."""
    global _mock_server
    if _mock_server is not None:
        try:
            # Make a local reference and clear the global immediately
            server = _mock_server
            _mock_server = None
            
            # Stop the server
            server.stop()
            
            # Ensure all resources are released
            if hasattr(server, '_thread') and server._thread is not None:
                if server._thread.is_alive():
                    server._thread.join(timeout=2.0)
                    if server._thread.is_alive():
                        logger.warning("Server thread did not shut down cleanly")
            
            # Clear any remaining references
            if hasattr(server, 'clients'):
                server.clients.clear()
            if hasattr(server, 'channels'):
                server.channels.clear()
                
        except Exception as e:
            logger.error(f"Error during server shutdown: {e}")
            raise
        finally:
            # Ensure we don't leave a dangling reference
            _mock_server = None


if __name__ == "__main__":
    # Run the mock server directly for testing
    logging.basicConfig(level=logging.DEBUG)
    server = start_mock_server()
    try:
        while True:
            input("Press Enter to stop the server...")
            break
    except KeyboardInterrupt:
        pass
    finally:
        stop_mock_server()
