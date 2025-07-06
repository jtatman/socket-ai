#!/usr/bin/env python3
"""
Simple script to test Python imports.
"""
import os
import sys
import traceback
from pathlib import Path

def main():
    """Main entry point."""
    print("=" * 80)
    print(f"Python executable: {sys.executable}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Python version: {sys.version}")
    
    # Add project root to path
    project_root = Path(__file__).parent.resolve()
    print(f"Project root: {project_root}")
    
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    print("\nPython path:")
    for i, path in enumerate(sys.path):
        print(f"  {i}: {path}")
    
    # Test imports
    print("\nTesting imports...")
    
    # Test 1: Import utils
    print("\n1. Testing import utils...")
    try:
        import utils
        print(f"  Success! utils module path: {utils.__file__}")
        
        # Test 1.1: Import config from utils
        print("\n1.1 Testing from utils import config...")
        try:
            from utils import config
            print(f"  Success! config module path: {config.__file__}")
        except ImportError as e:
            print(f"  Failed to import config from utils: {e}")
            print(traceback.format_exc())
    except ImportError as e:
        print(f"  Failed to import utils: {e}")
        print(traceback.format_exc())
    
    # Test 2: Import launch_bot
    print("\n2. Testing from scripts.launch_bot import main...")
    try:
        from scripts.launch_bot import main as launch_bot_main
        print("  Success! launch_bot imported successfully.")
    except ImportError as e:
        print(f"  Failed to import launch_bot: {e}")
        print(traceback.format_exc())
    
    print("\n" + "=" * 80)
    return 0

if __name__ == "__main__":
    sys.exit(main())
