#!/usr/bin/env python3
"""Run the seamproof test suite (stdlib unittest)."""
import sys
import unittest
from pathlib import Path

if __name__ == "__main__":
    suite = unittest.TestLoader().discover(
        start_dir=str(Path(__file__).parent / "tests"),
        top_level_dir=str(Path(__file__).parent),
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
