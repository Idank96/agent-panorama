"""Path bootstrap so each test file is runnable directly (``python tests/x.py``)."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
