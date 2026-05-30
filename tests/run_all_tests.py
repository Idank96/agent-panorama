"""Run the full agent-panorama test suite.

Usage:
    python tests/run_all_tests.py
    uv run python tests/run_all_tests.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent


def main() -> int:
    """Run every test file in the tests directory and return the exit code."""
    return pytest.main([str(_TESTS_DIR), "-v"])


if __name__ == "__main__":
    sys.exit(main())
