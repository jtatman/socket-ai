"""
Script to start the mock IRC server for testing.
"""

import sys
import os
import logging
from pathlib import Path

# Add the project root to the Python path
sys.path.append(str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mock_server.log')
    ]
)
logger = logging.getLogger(__name__)

def start_mock_server(host='127.0.0.1', port=16667):
    """Start the mock IRC server."""
    try:
        from tests.mock_irc_server import start_mock_server, stop_mock_server
        
        logger.info(f"Starting mock IRC server on {host}:{port}")
        server = start_mock_server(host=host, port=port)
        
        logger.info("Mock server started. Press Ctrl+C to stop.")
        
        # Keep the server running until interrupted
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping mock server...")
            stop_mock_server()
            logger.info("Mock server stopped.")
    
    except ImportError as e:
        logger.error(f"Failed to import mock server: {e}")
        logger.error("Make sure you're running from the project root directory.")
        return 1
    except Exception as e:
        logger.error(f"Error starting mock server: {e}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Start a mock IRC server for testing.')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind the server to')
    parser.add_argument('--port', type=int, default=16667, help='Port to listen on')
    
    args = parser.parse_args()
    
    sys.exit(start_mock_server(host=args.host, port=args.port))
