#!/usr/bin/env python3
"""Enhanced test runner with detailed debug information."""

import os
import sys
import importlib.util
import pkgutil
import pytest

def print_section(title):
    """Print a section header."""
    print(f"\n{'=' * 40}")
    print(f"{title.upper()}")
    print(f"{'=' * 40}")

def print_env_info():
    """Print environment information."""
    print_section("environment information")
    print(f"Python: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    print(f"Pytest version: {pytest.__version__}")

def print_test_discovery():
    """Print information about test discovery."""
    print_section("test discovery")
    
    # Try to import the tests package
    tests_dir = os.path.join(os.getcwd(), 'tests')
    if os.path.exists(tests_dir):
        print(f"Tests directory exists: {tests_dir}")
        
        # List test files
        print("\nTest files:")
        for root, _, files in os.walk(tests_dir):
            for file in files:
                if file.startswith('test_') and file.endswith('.py'):
                    print(f"- {os.path.join(root, file)}")
    else:
        print(f"Tests directory not found: {tests_dir}")

def run_pytest():
    """Run pytest with debug information."""
    print_section("running pytest")
    
    # Run pytest programmatically
    args = [
        '-v',
        '--tb=short',
        '--log-cli-level=DEBUG',
        '--collect-only',  # Only collect tests, don't run them
    ]
    
    print(f"Running: pytest {' '.join(args)}")
    return pytest.main(args)

def main():
    """Main function."""
    try:
        print_env_info()
        print_test_discovery()
        
        # Run pytest with collection only
        print("\n" + "=" * 40)
        print("TEST COLLECTION")
        print("=" * 40)
        result = run_pytest()
        
        if result == 0:
            print("\nTest collection successful!")
        else:
            print(f"\nTest collection failed with exit code: {result}")
        
        return result
        
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
