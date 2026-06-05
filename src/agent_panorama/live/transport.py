"""Fire-and-forget HTTP transport from the callback handler to the server.

Uses only the stdlib so instrumented apps need no extra dependencies, and
never raises: a missing or crashed dashboard must not break the agent it is
observing. Delivery failures log a single warning and then go quiet.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_warned = False
_warned_lock = threading.Lock()


def post_run(url: str, payload: dict, timeout: float = 2.0) -> bool:
    """POST a wire-format run payload to the live server.

    Args:
        url: The full ingest endpoint URL (e.g. ``http://localhost:8321/api/runs``).
        payload: The JSON-safe body to send.
        timeout: Socket timeout in seconds.

    Returns:
        True when the server accepted the run, False on any failure.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        _warn_once(url)
        return False


def _warn_once(url: str) -> None:
    """Log a single delivery warning for the lifetime of the process."""
    global _warned
    with _warned_lock:
        if _warned:
            return
        _warned = True
    logger.warning(
        "agent-panorama: could not reach the live dashboard at %s; "
        "runs will be dropped (is `agent-panorama serve` running?)",
        url,
    )
