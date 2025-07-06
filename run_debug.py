#!/usr/bin/env python3
"""Simple debug runner to test test discovery and execution."""

import os
import sys
import unittest

def discover_and_run_tests():
    """Discover and run tests, printing debug information."""
    print("=== DEBUG TEST RUNNER ===")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    
    # Add the current directory to the Python path
    sys.path.insert(0, os.getcwd())
    
    # Try to import the test module directly
    print("\n=== ATTEMPTING TO IMPORT TEST MODULE ===")
    try:
        from tests import debug_test
        print("Successfully imported debug_test")
        print(f"Module path: {debug_test.__file__}")
        
        # Run the test directly
        print("\n=== RUNNING TEST DIRECTLY ===")
        debug_test.test_debug()
        
        # Try to run with unittest
        print("\n=== RUNNING WITH UNITTEST ===")
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName('tests.debug_test')
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        print("\n=== TEST RESULTS ===")
        print(f"Tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    discover_and_run_tests()
