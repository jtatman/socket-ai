"""Test the mock IRC server with detailed logging and proper test fixtures."""

import os
import select
import socket
import time
import logging
import sys
import traceback
import pytest
from pathlib import Path

# Add the project root to the Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the mock server
from mock_irc_server import start_mock_server, stop_mock_server

# Test configuration
TEST_HOST = '127.0.0.1'
TEST_PORT = 16667  # Changed from 6667 to avoid conflicts with real IRC servers

# Configure logging
log_dir = Path(__file__).parent / 'logs'
log_dir.mkdir(exist_ok=True)
log_file = log_dir / 'test_mock_server.log'

# Configure root logger for the module
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# Clear any existing handlers
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Create a formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# Add file handler
file_handler = logging.FileHandler(log_file, mode='w')
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)
logger.info("Test module initialized")

@pytest.fixture(scope="module")
def mock_server():
    """Fixture to start and stop the mock IRC server for all tests."""
    logger.info("\n" + "="*80)
    logger.info("Starting mock IRC server...")
    server = start_mock_server(host=TEST_HOST, port=TEST_PORT)
    logger.info(f"Mock server started on {TEST_HOST}:{TEST_PORT}")
    
    yield server
    
    logger.info("Stopping mock IRC server...")
    stop_mock_server()
    logger.info("Mock server stopped")
    logger.info("="*80 + "\n")

def test_mock_server_basic(mock_server):
    """Test basic connection to the mock server with detailed logging.
    
    This test verifies that we can connect to the mock IRC server,
    send NICK and USER commands, and receive a welcome message.
    """
    logger.info("\n" + "-"*80)
    logger.info("Starting test_mock_server_basic")
    
    sock = None
    try:
        # Create a new socket
        logger.info("Creating socket...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)  # Increased timeout to 10 seconds
        
        # Connect to the mock server
        logger.info(f"Connecting to {TEST_HOST}:{TEST_PORT}...")
        try:
            sock.connect((TEST_HOST, TEST_PORT))
            logger.info("Successfully connected to mock server")
        except ConnectionRefusedError as e:
            logger.error(f"Failed to connect to mock server: {e}")
            logger.error("Make sure the mock server is running and accessible")
            raise
        
        # Send NICK command
        nick_cmd = b'NICK testuser\r\n'
        logger.info(f"Sending NICK command: {nick_cmd!r}")
        try:
            sock.sendall(nick_cmd)
            logger.info("Successfully sent NICK command")
        except Exception as e:
            logger.error(f"Failed to send NICK command: {e}")
            raise
        
        # Send USER command
        user_cmd = b'USER testuser 0 * :Test User\r\n'
        logger.info(f"Sending USER command: {user_cmd!r}")
        try:
            sock.sendall(user_cmd)
            logger.info("Successfully sent USER command")
        except Exception as e:
            logger.error(f"Failed to send USER command: {e}")
            raise
        
        # Read and log all responses
        logger.info("Reading server responses...")
        response = b''
        start_time = time.time()
        welcome_received = False
        
        while (time.time() - start_time) < 10:  # 10 second timeout
            try:
                # Check if there's data available to read
                ready_to_read, _, _ = select.select([sock], [], [], 5.0)
                if not ready_to_read:
                    logger.warning("No data received within 5 seconds")
                    break
                    
                data = sock.recv(4096)
                if not data:
                    logger.warning("Received empty data from server")
                    break
                    
                response += data
                logger.info(f"Received: {data!r}")
                
                # Check for welcome message (001 is the numeric for welcome message)
                if b'001' in response or b'Welcome' in response:
                    logger.info("Received welcome message from server")
                    welcome_received = True
                    break
                    
            except socket.timeout:
                logger.warning("Socket timeout while waiting for response")
                break
            except Exception as e:
                logger.error(f"Error receiving data: {e}")
                logger.error(traceback.format_exc())
                break
                
        # Log the complete response for debugging
        logger.info(f"Complete server response: {response!r}")
        
        # Verify we got the welcome message
        assert welcome_received, f"Did not receive welcome message. Response: {response!r}"
        
        logger.info("Test completed successfully!")
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
        logger.error(traceback.format_exc())
        raise
        
    finally:
        # Clean up the socket
        if sock:
            try:
                # Try to send QUIT command before closing
                try:
                    sock.sendall(b'QUIT :Test complete\r\n')
                    logger.info("Sent QUIT command to server")
                except Exception as e:
                    logger.warning(f"Could not send QUIT command: {e}")
                
                # Shutdown and close the socket
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError as e:
                    logger.warning(f"Could not shutdown socket gracefully: {e}")
                
                sock.close()
                logger.info("Closed socket connection")
                
            except Exception as e:
                logger.error(f"Error during socket cleanup: {e}")
        
        logger.info("-"*80 + "\n")

if __name__ == "__main__":
    # Run the test directly
    test_mock_server_basic()
    print("Test completed successfully!")
