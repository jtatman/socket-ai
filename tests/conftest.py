"""
Pytest configuration and fixtures for IRC bot testing.
"""
import os
import socket
import sys
import time
import logging
import socket
import subprocess
from pathlib import Path
from typing import Generator, List, Optional, Set
import pytest

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Ensure logs directory exists
LOGS_DIR = PROJECT_ROOT / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / 'test_irc.log')
    ]
)
logger = logging.getLogger(__name__)

# Constants
TEST_HOST = '127.0.0.1'
TEST_PORT = 16667  # Non-standard port to avoid conflicts
CHANNEL = "#test-channel"
PROJECT_ROOT = Path(__file__).parent.parent
ENV_DIR = PROJECT_ROOT / "environments" / "cantina"
BOTS = sorted([p.stem for p in ENV_DIR.glob("*.yml") if p.is_file()])

class SocketManager:
    """Manages socket connections for testing."""
    
    def __init__(self):
        self.sockets = []
    
    def create_socket(self) -> socket.socket:
        """Create a new socket and add it to the managed list."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        self.sockets.append(sock)
        return sock
    
    def close_all(self):
        """Close all managed sockets."""
        for sock in self.sockets:
            try:
                sock.close()
            except:
                pass
        self.sockets = []

def log_output(pipe, logger, level=logging.INFO):
    """Log output from a subprocess pipe."""
    try:
        for line in iter(pipe.readline, ''):
            if line:
                logger.log(level, f"[BOT] {line.strip()}")
    except ValueError:
        pass  # Pipe closed

class BotManager:
    """Manages bot processes for testing."""
    
    def __init__(self):
        self.processes = []
        self.logger = logging.getLogger("BotManager")
        
    def start_bot(self, bot_name: str):
        """Start a bot process and log its output."""
        # Create a temporary config file for testing
        import tempfile
        import shutil
        import yaml
        
        # Load the original config
        config_path = PROJECT_ROOT / "environments" / "cantina" / f"{bot_name}.yml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Update config for test environment
        config.update({
            'host': '127.0.0.1',
            'port': 16667,
            'test_mode': True,
            'channels': ['#test-channel']
        })
        
        # Create a temporary config file
        self.temp_dir = tempfile.mkdtemp(prefix='irc_bot_test_')
        temp_config_path = Path(self.temp_dir) / f"{bot_name}.yml"
        with open(temp_config_path, 'w') as f:
            yaml.dump(config, f)
        
        # Use the temporary config
        cmd = [
            sys.executable,  # Use the same Python interpreter
            str(PROJECT_ROOT / "scripts" / "launch_bot.py"),
            "--env", self.temp_dir,
            "--bot", bot_name,
            "--test-mode"
        ]
        
        # Ensure logs directory exists
        log_dir = PROJECT_ROOT / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        # Create log files for this bot
        log_file = log_dir / f"{bot_name}.log"
        
        self.logger.info(f"Starting bot: {bot_name} (logging to {log_file})")
        
        with open(log_file, 'w') as f:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Start threads to log stdout and stderr
            import threading
            stdout_thread = threading.Thread(
                target=log_output,
                args=(proc.stdout, self.logger, logging.INFO)
            )
            stderr_thread = threading.Thread(
                target=log_output,
                args=(proc.stderr, self.logger, logging.ERROR)
            )
            
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()
            
            self.processes.append({
                'process': proc,
                'stdout_thread': stdout_thread,
                'stderr_thread': stderr_thread,
                'log_file': log_file
            })
            
            return proc
    
    def stop_all(self):
        """Stop all bot processes and clean up resources."""
        for proc_info in self.processes:
            try:
                proc = proc_info['process']
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                
                # Ensure threads are cleaned up
                if 'stdout_thread' in proc_info:
                    proc_info['stdout_thread'].join(timeout=1)
                if 'stderr_thread' in proc_info:
                    proc_info['stderr_thread'].join(timeout=1)
                    
                # Clean up temporary config directory if it exists
                if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                    import shutil
                    try:
                        shutil.rmtree(self.temp_dir, ignore_errors=True)
                    except Exception as e:
                        self.logger.warning(f"Error cleaning up temp directory: {e}")
                    
            except Exception as e:
                self.logger.error(f"Error stopping bot process: {e}")
                
        self.processes = []
        self.processes = []

@pytest.fixture(scope="session")
def socket_manager() -> Generator[SocketManager, None, None]:
    """Provide a socket manager for tests."""
    manager = SocketManager()
    try:
        yield manager
    finally:
        manager.close_all()

@pytest.fixture(scope="session")
def bot_manager() -> Generator[BotManager, None, None]:
    """Provide a bot manager for tests."""
    manager = BotManager()
    try:
        yield manager
    finally:
        manager.stop_all()

def irc_send(sock: socket.socket, msg: str) -> socket.socket:
    """Send an IRC message with error handling."""
    try:
        if not msg.endswith('\r\n'):
            msg += '\r\n'
        sock.sendall(msg.encode('utf-8'))
        return sock
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        raise
