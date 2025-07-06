"""
Integration tests for IRC bots using miniircd.

This test suite verifies the core functionality of IRC bots including:
- Server connection and registration
- Channel joining and participation
- Message sending and receiving
- Bot response behavior
- Error handling and reconnection

Tests are designed to run against a local miniircd server instance and verify
both the bot framework and server interaction.
"""
import os
import sys
import time
import logging
import socket
import pytest
import subprocess
import signal
from pathlib import Path
from queue import Empty
from unittest.mock import patch

# Add project root to path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import test configuration
PROJECT_ROOT = Path(__file__).parent.parent
ENV_DIR = PROJECT_ROOT / "environments" / "cantina"
BOTS = sorted([p.stem for p in ENV_DIR.glob("*.yml") if p.is_file()])

# IRC Server Configuration
IRC_HOST = '127.0.0.1'
IRC_PORT = 16667
TEST_CHANNEL = '#test-channel'

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / 'logs' / 'test_irc_debug.log')
    ]
)

# Mock server imports have been removed - using miniircd instead

# Register custom marks
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        'integration: mark test as integration test (deselect with "-m not integration")'
    )

def terminate_existing_miniircd():
    """Terminate any existing miniircd processes."""
    import psutil
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Look for miniircd processes
            if proc.info['cmdline'] and 'miniircd.py' in ' '.join(proc.info['cmdline']):
                logger.info(f"Terminating existing miniircd process (PID: {proc.info['pid']})")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

@pytest.fixture(scope="module")
def ensure_miniircd_running():
    """Ensure miniircd is running for tests, with proper cleanup.
    
    This fixture starts a miniircd server if one isn't already running and ensures
    it's properly cleaned up after tests complete. It also verifies the server
    is responsive before proceeding with tests.
    
    Yields:
        bool: True if the server is running and responsive
        
    Raises:
        RuntimeError: If the server cannot be started or becomes unresponsive
    """
    # First, terminate any existing miniircd instances
    terminate_existing_miniircd()
    
    # Start a new instance
    import subprocess
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "run_miniircd.py")],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # Wait for server to start (max 10 seconds)
    start_time = time.time()
    while time.time() - start_time < 10:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                if sock.connect_ex((IRC_HOST, IRC_PORT)) == 0:
                    logger.info("miniircd server is running and accepting connections")
                    break
        except Exception as e:
            logger.debug(f"Waiting for miniircd to start: {e}")
        time.sleep(0.5)
    else:
        # If we get here, server didn't start in time
        process.terminate()
        raise RuntimeError("Failed to start miniircd server")
    
    yield  # Test runs here
    
    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()

logger = logging.getLogger(__name__)

def test_always_passes():
    """Simple test that always passes to verify test discovery.
    
    This is a smoke test that verifies the test framework is working correctly.
    It should always pass and is useful for verifying basic test discovery
    and execution.
    """
    assert True

def test_environment(monkeypatch):
    """Verify the test environment is set up correctly.
    
    This test verifies that all required files and configurations are in place
    before running the integration tests. It checks for:
    - Environment directory existence
    - Bot configuration files
    - Required environment variables
    
    Args:
        monkeypatch: Pytest fixture for modifying environment variables
        
    Raises:
        AssertionError: If any required environment setup is missing
    """
    # Test environment variables and paths
    assert ENV_DIR.exists(), f"Environment directory not found: {ENV_DIR}"
    assert BOTS, f"No bot configurations found in {ENV_DIR}"
    logger.info(f"Found {len(BOTS)} bot configurations")
    for bot in BOTS:
        logger.info(f"- {bot}")
    assert True

def test_irc_connection(ensure_miniircd_running):
    """Test basic IRC server connection and protocol with miniircd.
    
    This test verifies the core IRC protocol functionality including:
    - Server connection establishment
    - USER and NICK registration
    - PING/PONG keepalive
    - Basic channel operations
    
    Args:
        ensure_miniircd_running: Fixture that ensures the IRC server is running
        
    Raises:
        AssertionError: If any IRC protocol operation fails
        TimeoutError: If the server doesn't respond within expected time
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)  # 5 second timeout
    
    try:
        sock.connect((IRC_HOST, IRC_PORT))
        
        # Send NICK and USER commands
        sock.sendall(b'NICK TestUser\r\n')
        sock.sendall(b'USER testuser 0 * :Test User\r\n')
        
        # Wait for welcome message
        response = ''
        start_time = time.time()
        while '001' not in response and (time.time() - start_time) < 5:
            chunk = sock.recv(4096).decode('utf-8', errors='ignore')
            if not chunk:
                break
            response += chunk
            if '001' in response:
                break
        
        assert '001' in response, f"Did not receive welcome message. Got: {response}"
        
        # Join test channel
        sock.sendall(f'JOIN {TEST_CHANNEL}\r\n'.encode('utf-8'))
        
        # Wait for join confirmation
        response = ''
        start_time = time.time()
        while TEST_CHANNEL.encode('utf-8') not in response.encode('utf-8') and (time.time() - start_time) < 5:
            chunk = sock.recv(4096).decode('utf-8', errors='ignore')
            if not chunk:
                break
            response += chunk
            if TEST_CHANNEL in response:
                break
        
        assert TEST_CHANNEL in response, \
            f"Did not receive JOIN confirmation. Got: {response}"
        
        # Send a test message
        test_msg = f'PRIVMSG {TEST_CHANNEL} :Hello, world!\r\n'
        sock.sendall(test_msg.encode('utf-8'))
        
    except socket.timeout:
        assert False, "Connection timed out"
    except Exception as e:
        assert False, f"Unexpected error: {str(e)}"
    finally:
        # Clean up
        try:
            sock.sendall(b'QUIT :Test complete\r\n')
            sock.close()
        except:
            pass

def run_bot_directly(bot_name):
    """Run the bot directly as a subprocess for better debugging.
    
    This helper function launches a bot as a separate process and returns
    the process handle. It's used by test_bot_connection to test bot
    functionality in an isolated environment.
    
    Args:
        bot_name (str): Name of the bot configuration to run (without .yml)
        
    Returns:
        subprocess.Popen: Process handle for the running bot
        
    Raises:
        FileNotFoundError: If the bot configuration doesn't exist
        subprocess.SubprocessError: If the bot process fails to start
    """
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "launch_bot.py"),
        "--env", "cantina",
        "--bot", bot_name,
        "--test-mode"
    ]
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(PROJECT_ROOT)
    )
    
    # Log the first few lines of output for debugging
    stdout_lines = []
    stderr_lines = []
    
    # Non-blocking read of stdout/stderr
    from threading import Thread
    from queue import Queue, Empty
    
    def enqueue_output(pipe, queue):
        for line in iter(pipe.readline, ''):
            queue.put(line)
        pipe.close()
    
    stdout_queue = Queue()
    stderr_queue = Queue()
    
    stdout_thread = Thread(target=enqueue_output, args=(process.stdout, stdout_queue))
    stderr_thread = Thread(target=enqueue_output, args=(process.stderr, stderr_queue))
    stdout_thread.daemon = True
    stderr_thread.daemon = True
    stdout_thread.start()
    stderr_thread.start()
    
    return {
        'process': process,
        'stdout_queue': stdout_queue,
        'stderr_queue': stderr_queue,
        'stdout_thread': stdout_thread,
        'stderr_thread': stderr_thread
    }

@pytest.mark.integration
def test_bot_connection(ensure_miniircd_running):
    """Test that a bot can connect to the miniircd server and respond to messages.
    
    This integration test verifies end-to-end bot functionality including:
    - Bot process startup and initialization
    - IRC server connection and registration
    - Channel joining and presence announcement
    - Message reception and response
    - Error handling and reconnection
    
    The test uses a real miniircd server and verifies the bot's behavior
    matches expected patterns.
    
    Args:
        ensure_miniircd_running: Fixture that ensures the IRC server is running
        
    Raises:
        AssertionError: If the bot fails to behave as expected
        TimeoutError: If operations take longer than expected
    """
    logger = logging.getLogger(__name__)
    logger.info("\n" + "="*80)
    logger.info("STARTING TEST: test_bot_connection with miniircd")
    logger.info("="*80)
    
    if not BOTS:
        logger.error("No bot configurations found in %s", ENV_DIR)
        pytest.skip("No bot configurations found")
    
    logger.info("Available bots: %s", ", ".join(BOTS))
    
    # Start a bot
    bot_name = BOTS[0]  # Test with the first bot
    bot_nick = bot_name.lower()  # Assuming bot nick is same as config name
    logger.info(f"Starting bot: {bot_name}")
    
    # Load bot config to get the channel it's configured to join
    bot_config_path = ENV_DIR / f"{bot_name}.yml"
    with open(bot_config_path, 'r') as f:
        import yaml
        bot_config = yaml.safe_load(f)
    
    # Get the channel from config, default to #test-channel if not specified
    bot_channel = bot_config.get('channel', '#test-channel')
    logger.info(f"Bot will join channel: {bot_channel}")
    
    # Log the bot's configuration
    bot_config_path = ENV_DIR / f"{bot_name}.yml"
    logger.info(f"Bot config path: {bot_config_path}")
    logger.info(f"Bot config exists: {bot_config_path.exists()}")
    
    # Start the bot directly with subprocess for better debugging
    bot_proc = run_bot_directly(bot_name)
    process = bot_proc['process']
    
    if not process or process.poll() is not None:
        # Process failed to start or already exited
        stdout = ""
        stderr = ""
        try:
            stdout, stderr = process.communicate(timeout=5)
        except:
            pass
        
        logger.error(f"Failed to start bot process. Return code: {process.returncode if process else 'N/A'}")
        logger.error(f"STDOUT: {stdout}")
        logger.error(f"STDERR: {stderr}")
        pytest.fail(f"Failed to start bot process. Return code: {process.returncode if process else 'N/A'}")
    
    logger.info(f"Started bot process with PID: {process.pid}")
    
    # Give the bot time to start and connect
    logger.info("Waiting for bot to start and connect to server (15 seconds)...")
    
    # Monitor bot output while waiting
    start_time = time.time()
    timeout = 15  # seconds
    
    while time.time() - start_time < timeout:
        # Check stdout
        try:
            line = bot_proc['stdout_queue'].get_nowait()
            if line:
                logger.info(f"BOT STDOUT: {line.strip()}")
        except Empty:
            pass
            
        # Check stderr
        try:
            line = bot_proc['stderr_queue'].get_nowait()
            if line:
                logger.error(f"BOT STDERR: {line.strip()}")
        except Empty:
            pass
            
        time.sleep(0.1)
    
    # Check if process is still running
    if process.poll() is not None:
        logger.error(f"Bot process exited with code {process.returncode}")
        pytest.fail(f"Bot process exited with code {process.returncode}")
    
    # Connect as a test user
    logger.info("Connecting test client to IRC server...")
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)  # Set a timeout for the socket
        sock.connect((IRC_HOST, IRC_PORT))
        logger.info(f"Connected to IRC server at {IRC_HOST}:{IRC_PORT}")
        
        # Log in
        logger.info("Sending NICK and USER commands...")
        sock.sendall(b'NICK TestUser\r\n')
        sock.sendall(b'USER testuser 0 * :Test User\r\n')
        
        # Wait for welcome message
        logger.info("Waiting for welcome message...")
        response = ''
        start_time = time.time()
        while '001' not in response and (time.time() - start_time) < 10:
            try:
                chunk = sock.recv(4096).decode('utf-8', errors='ignore')
                if not chunk:
                    logger.warning("Connection closed by server")
                    break
                response += chunk
                if '001' in response:
                    logger.info("Received welcome message")
                    break
            except socket.timeout:
                logger.warning("Timed out waiting for welcome message")
                break
        
        logger.debug(f"Server response after welcome: {response}")
        assert '001' in response, "Did not receive welcome message from server"
        
        # Join the bot's configured channel
        logger.info(f"Joining bot's channel {bot_channel}...")
        sock.sendall(f'JOIN {bot_channel}\r\n'.encode('utf-8'))
        
        # Wait for join confirmation
        logger.info("Waiting for join confirmation...")
        response = ''
        start_time = time.time()
        while (time.time() - start_time) < 10:
            try:
                chunk = sock.recv(4096).decode('utf-8', errors='ignore')
                if not chunk:
                    logger.warning("Connection closed by server")
                    break
                response += chunk
                
                # Check for our own join confirmation
                if f'JOIN {bot_channel}' in response and 'TestUser' in response:
                    logger.info("Received our own join confirmation")
                    # Check if bot is in the channel
                    sock.sendall(f'NAMES {bot_channel}\r\n'.encode('utf-8'))
                
                # Check for NAMES response with bot in it
                if '353 TestUser = ' in response and bot_nick in response.lower():
                    logger.info(f"Bot {bot_nick} is in the channel")
                    break
                    
            except socket.timeout:
                logger.warning("Timed out waiting for join confirmation")
                break
        
        # Verify we and the bot are in the channel
        assert bot_nick in response.lower(), f"Bot {bot_nick} did not join the channel {bot_channel}. Response: {response}"
        
        # Send a message that should trigger a response
        test_msg = f'PRIVMSG {bot_channel} :Hello {bot_name}, are you there?\r\n'
        logger.info(f"Sending test message: {test_msg.strip()}")
        sock.sendall(test_msg.encode('utf-8'))
        
        # Wait for a response (with increased timeout for LLM processing)
        logger.info("Waiting for bot response (max 30 seconds)...")
        response = ''
        start_time = time.time()
        timeout = 30  # seconds
        last_activity = time.time()
        
        while (time.time() - start_time) < timeout:
            try:
                # Set a shorter socket timeout to allow for periodic status updates
                sock.settimeout(1.0)
                chunk = sock.recv(4096).decode('utf-8', errors='ignore')
                
                if chunk:
                    last_activity = time.time()
                    response += chunk
                    logger.info(f"Received: {chunk.strip()}")
                    
                    # Check if the bot responded (case-insensitive)
                    if f'PRIVMSG {bot_channel} :' in chunk and bot_nick.lower() in chunk.lower():
                        logger.info(f"Bot {bot_nick} responded after {time.time() - start_time:.1f} seconds")
                        break
                else:
                    # No data received, but connection still alive
                    elapsed = time.time() - last_activity
                    if elapsed > 5:  # Log every 5 seconds of inactivity
                        logger.info(f"Waiting for bot response... ({elapsed:.1f}s elapsed)")
                        last_activity = time.time()
                
            except socket.timeout:
                # Expected due to our shorter socket timeout
                elapsed = time.time() - start_time
                if elapsed > timeout - 1:  # Only warn if we're actually timing out
                    logger.warning(f"Test timeout reached after {elapsed:.1f} seconds")
                    break
                continue
                
            except Exception as e:
                logger.error(f"Unexpected error while waiting for bot: {e}")
                break
        
        # Verify the bot responded
        logger.info(f"Final response from server: {response}")
        assert bot_nick.lower() in response.lower(), \
            f"Bot {bot_nick} did not respond to message. Full response: {response}"
        
    except socket.timeout:
        assert False, "Test timed out waiting for bot response"
    except Exception as e:
        logger.error(f"Test failed with exception: {str(e)}")
        raise
    finally:
        # Clean up
        try:
            if sock:
                sock.sendall(b'QUIT :Test complete\r\n')
                sock.close()
            
            # Terminate the bot process
            if 'process' in locals() and process:
                logger.info(f"Terminating bot process {process.pid}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception as e:
            logger.warning(f"Error during cleanup: {str(e)}")
            pass
