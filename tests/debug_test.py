#!/usr/bin/env python3
"""Debug test file to verify pytest is working."""

import sys
import os

def test_debug():
    """Test that prints debug information."""
    print("=== DEBUG TEST START ===")
    print(f"Python version: {sys.version}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    print("=== DEBUG TEST END ===")
    assert True
