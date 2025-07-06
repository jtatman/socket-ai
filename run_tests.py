"""Script to run tests and verify test discovery."""

import sys
import os
import pytest

def main():
    """Run tests and print debug information."""
    print("=== Running test discovery ===")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    
    # List all test files
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    print(f"\nTest files in {test_dir}:")
    for root, _, files in os.walk(test_dir):
        for file in files:
            if file.startswith('test_') and file.endswith('.py'):
                print(f"- {os.path.join(root, file)}")
    
    # Run pytest programmatically
    print("\nRunning pytest...")
    return pytest.main(['-v', '--tb=short', '--log-cli-level=DEBUG'])

if __name__ == "__main__":
    sys.exit(main())
