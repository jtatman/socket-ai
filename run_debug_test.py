"""
Debug script for testing IRC bot connection issues.

This script helps diagnose import and connection issues with the IRC bot.
"""
import os
import sys
import time
import logging
import socket
import subprocess
import traceback
from pathlib import Path

def setup_logging():
    """Set up logging with both console and file handlers."""
    try:
        # Ensure logs directory exists
        log_dir = Path(__file__).parent / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        # Create a unique log file for this run
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f'debug_test_{timestamp}.log'
        
        # Configure logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(str(log_file), encoding='utf-8')
            ]
        )
        
        logger = logging.getLogger(__name__)
        logger.info("=" * 80)
        logger.info(f"Starting debug session at {time.ctime()}")
        logger.info(f"Log file: {log_file.absolute()}")
        logger.info(f"Python executable: {sys.executable}")
        logger.info(f"Working directory: {os.getcwd()}")
        
        # Log environment variables that might affect imports
        logger.info("Environment variables:")
        for var in ['PYTHONPATH', 'PATH', 'VIRTUAL_ENV']:
            logger.info(f"  {var}: {os.environ.get(var, 'Not set')}")
            
        return logger
        
    except Exception as e:
        print(f"CRITICAL: Failed to set up logging: {e}")
        print(traceback.format_exc())
        sys.exit(1)

def check_python_path(project_root):
    """Check and update Python path."""
    logger = logging.getLogger(__name__)
    
    try:
        # Add project root to Python path if not already there
        project_root = Path(project_root).resolve()
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        # Also add parent directory in case we need to import from root
        parent_dir = project_root.parent
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))
        
        logger.info("Python path:")
        for i, path in enumerate(sys.path):
            logger.info(f"  {i}: {path}")
        
        # Try to import utils
        try:
            import utils
            logger.info("Successfully imported utils module")
            logger.info(f"utils module path: {utils.__file__}")
            
            # Verify we can access the config module
            from utils import config
            logger.info("Successfully imported utils.config")
            logger.info(f"config module path: {config.__file__}")
            
            return True
            
        except ImportError as e:
            logger.error(f"Failed to import utils: {e}")
            logger.error(traceback.format_exc())
            
            # Try to find the utils module manually
            logger.info("Searching for utils module...")
            for root, dirs, files in os.walk(str(project_root)):
                if 'utils' in dirs:
                    logger.info(f"Found utils directory at: {os.path.join(root, 'utils')}")
                if 'utils.py' in files:
                    logger.info(f"Found utils.py at: {os.path.join(root, 'utils.py')}")
            
            return False
            
    except Exception as e:
        logger.error(f"Error in check_python_path: {e}")
        logger.error(traceback.format_exc())
        return False

def main():
    """Main entry point for the debug script."""
    try:
        # Set up logging
        logger = setup_logging()
        
        # Get project root (this file's parent directory)
        project_root = Path(__file__).parent.resolve()
        logger.info(f"Project root: {project_root}")
        
        # Check Python path and imports
        if not check_python_path(project_root):
            logger.error("Failed to set up Python path correctly")
            return 1
        
        # If we get here, basic imports should work
        logger.info("Basic imports successful!")
        
        # Try to import launch_bot
        try:
            from scripts.launch_bot import main as launch_bot_main
            logger.info("Successfully imported launch_bot")
            
            # Log the launch_bot module location
            import inspect
            logger.info(f"launch_bot module path: {inspect.getfile(launch_bot_main.__module__)}")
            
        except ImportError as e:
            logger.error(f"Failed to import launch_bot: {e}")
            logger.error(traceback.format_exc())
            
            # Try to find the scripts directory
            scripts_dir = project_root / 'scripts'
            logger.info(f"Contents of {scripts_dir}:")
            if scripts_dir.exists():
                for f in scripts_dir.iterdir():
                    logger.info(f"  - {f.name}")
            else:
                logger.error(f"Scripts directory not found: {scripts_dir}")
            
            return 1
        
        logger.info("All imports successful!")
        return 0
        
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
        logger.error(traceback.format_exc())
        return 1
    finally:
        logger.info("Debug session completed at %s", time.ctime())
        logger.info("=" * 80)

if __name__ == "__main__":
    sys.exit(main())

def check_mock_server():
    """Check if the mock server is running and accepting connections."""
    logger.info("Checking mock server connection...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect(('127.0.0.1', 16667))
            logger.info("Successfully connected to mock server")
            return True
    except Exception as e:
        logger.error(f"Failed to connect to mock server: {e}")
        return False

def run_test():
    """Run the test with detailed logging."""
    logger.info("Starting debug test...")
    
    # Check if mock server is running
    if not check_mock_server():
        logger.error("Mock server is not running. Please start it first.")
        return False
    
    # Find bot configurations
    project_root = Path(__file__).parent
    env_dir = project_root / "environments" / "cantina"
    bots = sorted([p.stem for p in env_dir.glob("*.yml") if p.is_file()])
    
    if not bots:
        logger.error("No bot configurations found")
        return False
    
    bot_name = bots[0]
    logger.info(f"Testing with bot: {bot_name}")
    
    # Run the bot directly
    cmd = [
        sys.executable,
        str(project_root / "scripts" / "launch_bot.py"),
        "--env", "cantina",
        "--bot", bot_name,
        "--test-mode"
    ]
    
    logger.info(f"Running command: {' '.join(cmd)}")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(project_root)
        )
        
        logger.info(f"Started bot process with PID: {process.pid}")
        
        # Monitor the process for a while
        timeout = 15  # seconds
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check if process is still running
            if process.poll() is not None:
                logger.error(f"Bot process exited with code {process.returncode}")
                stdout, stderr = process.communicate()
                logger.info(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return False
            
            # Log output
            stdout_line = process.stdout.readline()
            if stdout_line:
                logger.info(f"BOT: {stdout_line.strip()}")
            
            stderr_line = process.stderr.readline()
            if stderr_line:
                logger.error(f"BOT ERROR: {stderr_line.strip()}")
            
            time.sleep(0.1)
        
        # Process is still running, terminate it
        logger.info("Test completed, terminating bot process...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Bot process did not terminate gracefully, killing...")
            process.kill()
        
        return True
        
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        return False

if __name__ == "__main__":
    run_test()
