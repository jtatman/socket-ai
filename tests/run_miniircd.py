"""
Wrapper script to run miniircd with test configuration.
"""
import os
import sys
import signal
import subprocess
import time
from pathlib import Path

# Configuration
HOST = '127.0.0.1'
PORT = 16667
LOG_FILE = 'miniircd_test.log'

# Get the path to miniircd.py
SCRIPT_DIR = Path(__file__).parent.absolute()
MINIIRCD_PATH = SCRIPT_DIR / 'miniircd.py'

# Check if miniircd.py exists
if not MINIIRCD_PATH.exists():
    print(f"Error: {MINIIRCD_PATH} not found")
    sys.exit(1)

def start_miniircd():
    """Start the miniircd server with test configuration."""
    # Build the command
    cmd = [
        sys.executable,
        str(MINIIRCD_PATH),
        '--listen', HOST,
        '--ports', str(PORT),
        '--log-file', str(SCRIPT_DIR / LOG_FILE),
        '--verbose'  # Show output in console
    ]
    
    # Add --setuid root if needed
    if hasattr(os, 'getuid') and os.getuid() == 0:
        cmd.extend(['--setuid', 'root'])
    
    print(f"Starting miniircd: {' '.join(cmd)}")
    
    # Start the process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Wait for server to start
    time.sleep(1)
    if process.poll() is not None:
        print("Failed to start miniircd:")
        print(process.stdout.read() if process.stdout else "No output")
        sys.exit(1)
    
    return process

def stop_miniircd(process):
    """Stop the miniircd server."""
    if process and process.poll() is None:
        print("Stopping miniircd...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        print("miniircd stopped")

def main():
    """Main entry point."""
    process = None
    try:
        process = start_miniircd()
        print(f"miniircd server running on {HOST}:{PORT}")
        print("Press Ctrl+C to stop the server")
        
        # Keep the script running until interrupted
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        stop_miniircd(process)

if __name__ == "__main__":
    main()
