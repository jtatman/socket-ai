"""
Standalone script to test the mock IRC server.
Run this to verify the server is working independently of pytest.
"""

import socket
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_server.log')
    ]
)
logger = logging.getLogger(__name__)

def test_connection(host='127.0.0.1', port=16667):
    """Test connection to the IRC server with detailed logging."""
    logger.info("Starting IRC connection test...")
    
    try:
        # Create socket
        logger.info("Creating socket...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)  # 5 second timeout
        
        # Connect to server
        logger.info(f"Connecting to {host}:{port}...")
        sock.connect((host, port))
        logger.info("Connected to server")
        
        # Send NICK command
        nick_cmd = b'NICK testuser\r\n'
        logger.info(f"Sending NICK command: {nick_cmd!r}")
        sock.send(nick_cmd)
        
        # Send USER command
        user_cmd = b'USER testuser 0 * :Test User\r\n'
        logger.info(f"Sending USER command: {user_cmd!r}")
        sock.send(user_cmd)
        
        # Read responses
        logger.info("Reading server responses...")
        response = b''
        start_time = time.time()
        
        while (time.time() - start_time) < 5:  # 5 second timeout
            try:
                data = sock.recv(4096)
                if data:
                    logger.info(f"Received: {data!r}")
                    response += data
                    if b'Welcome' in response or b'001' in response:
                        logger.info("Found welcome message in response")
                        break
            except socket.timeout:
                logger.warning("Socket timeout while waiting for response")
                break
            except Exception as e:
                logger.error(f"Error reading from socket: {e}")
                break
        
        # Log the complete response for debugging
        logger.info(f"Complete response: {response!r}")
        
        # Verify we got a welcome message
        if b'Welcome' in response or b'001' in response:
            logger.info("✓ Success: Received welcome message")
            return True
        else:
            logger.error("✗ Error: Did not receive welcome message")
            return False
            
    except ConnectionRefusedError:
        logger.error("✗ Error: Connection refused. Is the mock server running?")
        return False
    except Exception as e:
        logger.error(f"✗ Error during test: {e}", exc_info=True)
        return False
    finally:
        # Clean up
        if 'sock' in locals() and sock is not None:
            try:
                logger.info("Sending QUIT command...")
                sock.send(b'QUIT :Test complete\r\n')
            except Exception as e:
                logger.error(f"Error sending QUIT: {e}")
            try:
                sock.close()
                logger.info("Socket closed")
            except Exception as e:
                logger.error(f"Error closing socket: {e}")

if __name__ == "__main__":
    import sys
    
    # Get host and port from command line or use defaults
    host = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 16667
    
    logger.info(f"Testing connection to {host}:{port}")
    success = test_connection(host, port)
    
    if success:
        logger.info("Test completed successfully!")
        sys.exit(0)
    else:
        logger.error("Test failed!")
        sys.exit(1)
