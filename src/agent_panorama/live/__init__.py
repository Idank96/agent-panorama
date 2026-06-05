"""Live mode: stream agent runs from a running app to a local dashboard.

The pieces are intentionally decoupled by dependency weight:

- :class:`PanoramaCallbackHandler` (``handler.py``) and the wire format
  (``serde.py``) need only the base install — the handler posts completed runs
  over stdlib HTTP, so the instrumented app never needs server dependencies.
- The server (``server.py``) requires the ``live`` extra
  (``pip install 'agent-panorama[live]'``) and is imported lazily.
"""

from __future__ import annotations

from .handler import PanoramaCallbackHandler
from .serde import WIRE_VERSION, run_from_dict, run_to_dict

__all__ = [
    "WIRE_VERSION",
    "PanoramaCallbackHandler",
    "create_app",
    "run_from_dict",
    "run_to_dict",
    "serve",
]


def __getattr__(name: str) -> object:
    """Lazily expose the server API so a missing 'live' extra fails late."""
    if name in ("create_app", "serve"):
        from . import server

        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
