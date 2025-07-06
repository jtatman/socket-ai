#!/usr/bin/env python3
"""
Script to check Python imports and write output to a file.
"""
import os
import sys
import traceback
from pathlib import Path

def write_output(*args, **kwargs):
    """Write output to both console and file."""
    with open('import_check.log', 'a', encoding='utf-8') as f:
        print(*args, **kwargs, file=f)
    print(*args, **kwargs)

def main():
    """Main entry point."""
    # Clear the log file
    with open('import_check.log', 'w', encoding='utf-8') as f:
        f.write('')
    
    write_output("=" * 80)
    write_output(f"Python executable: {sys.executable}")
    write_output(f"Working directory: {os.getcwd()}")
    write_output(f"Python version: {sys.version}")
    
    # Add project root to path
    project_root = Path(__file__).parent.resolve()
    write_output(f"Project root: {project_root}")
    
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    write_output("\nPython path:")
    for i, path in enumerate(sys.path):
        write_output(f"  {i}: {path}")
    
    # Test imports
    write_output("\nTesting imports...")
    
    # Test 1: Import utils
    write_output("\n1. Testing import utils...")
    try:
        import utils
        write_output(f"  Success! utils module path: {utils.__file__}")
        
        # Test 1.1: Import config from utils
        write_output("\n1.1 Testing from utils import config...")
        try:
            from utils import config
            write_output(f"  Success! config module path: {config.__file__}")
        except ImportError as e:
            write_output(f"  Failed to import config from utils: {e}")
            write_output(traceback.format_exc())
    except ImportError as e:
        write_output(f"  Failed to import utils: {e}")
        write_output(traceback.format_exc())
    
    # Test 2: Import launch_bot
    write_output("\n2. Testing from scripts.launch_bot import main...")
    try:
        from scripts.launch_bot import main as launch_bot_main
        write_output("  Success! launch_bot imported successfully.")
    except ImportError as e:
        write_output(f"  Failed to import launch_bot: {e}")
        write_output(traceback.format_exc())
    
    write_output("\n" + "=" * 80)
    write_output("\nCheck 'import_check.log' for complete output.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
