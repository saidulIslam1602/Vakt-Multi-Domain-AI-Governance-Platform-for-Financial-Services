"""Pytest configuration for shared-lib unit tests."""
import pathlib
import sys

# Ensure the shared-lib src is on the path when running tests directly
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
