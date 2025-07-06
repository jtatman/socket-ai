"""Launch a full team of IRC bots defined in an environment folder.

Usage:
    python scripts/launch_team.py environments/star_wars

This will scan for all *.yml files in that folder and spawn one child
process per bot using `python -m bots.irc_bot <config>`.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional


class BotLauncher:
    def __init__(self):
        self.procs = []
        self.original_sigint = signal.getsignal(signal.SIGINT)
        self.original_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle termination signals by cleaning up child processes."""
        print(f"\nReceived signal {signal.Signals(signum).name}, shutting down bots...")
        self.cleanup()
        # Restore original signal handlers and re-raise for proper exit
        signal.signal(signal.SIGINT, self.original_sigint)
        signal.signal(signal.SIGTERM, self.original_sigterm)
        os.kill(os.getpid(), signum)

    def launch_bot(self, config_path: Path) -> Optional[subprocess.Popen]:
        """Launch a single bot process."""
        try:
            print(f"[launch] Starting {config_path.name}...")
            # Use Popen with start_new_session=True to create a new process group
            # This allows us to properly clean up all child processes
            proc = subprocess.Popen(
                [sys.executable, "-m", "bots.irc_bot", str(config_path)],
                start_new_session=True
            )
            self.procs.append(proc)
            print(f"[launch] {config_path.name} started (PID: {proc.pid})")
            # Small delay between bot starts to avoid connection flooding
            time.sleep(0.5)
            return proc
        except Exception as e:
            print(f"[error] Failed to start {config_path.name}: {e}", file=sys.stderr)
            return None

    def cleanup(self):
        """Clean up all bot processes."""
        if not self.procs:
            return

        print("\nCleaning up bot processes...")
        
        # First try to terminate gracefully
        for proc in self.procs:
            if proc.poll() is None:  # Process is still running
                try:
                    print(f"  Terminating bot (PID: {proc.pid})...")
                    proc.terminate()
                except Exception as e:
                    print(f"  Error terminating process {proc.pid}: {e}")
        
        # Give processes a chance to terminate gracefully
        time.sleep(2)
        
        # Force kill any remaining processes
        for proc in self.procs:
            if proc.poll() is None:  # Still running
                try:
                    print(f"  Force killing bot (PID: {proc.pid})...")
                    proc.kill()
                except Exception as e:
                    print(f"  Error killing process {proc.pid}: {e}")
        
        # Wait for all processes to terminate
        for proc in self.procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"  Warning: Process {proc.pid} did not terminate in time")
        
        print("Cleanup complete.")
        self.procs.clear()

def launch_team(env_dirs: List[Path]) -> None:
    # Validate directories
    for env_dir in env_dirs:
        if not env_dir.is_dir():
            sys.exit(f"Environment path {env_dir} is not a directory")

    # Find all config files
    configs: List[Path] = []
    for env_dir in env_dirs:
        configs.extend(sorted(env_dir.glob("*.yml")))
    
    if not configs:
        sys.exit("No *.yml configs found in provided environment directories")

    launcher = BotLauncher()
    
    try:
        # Launch all bots
        for cfg in configs:
            launcher.launch_bot(cfg)
        
        print("\nAll bots launched. Press Ctrl+C to terminate all bots.")
        print("Waiting for bots to complete (they should run forever)...")
        
        # Keep the main process alive until interrupted
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, shutting down...")
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
    finally:
        launcher.cleanup()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Launch a team of IRC bots from a folder")
    ap.add_argument("env", type=Path, nargs="+", help="One or more environment directories containing *.yml bot configs")
    args = ap.parse_args()
    launch_team(args.env)
