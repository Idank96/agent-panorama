"""Shared text helpers used by analysis and rendering.

Kept dependency-free so both the feed builder and the templates can condense a
result to one readable sentence and derive a stable agent key from a name.
"""

from __future__ import annotations

import re


def condense(text: str) -> str:
    """Reduce a result to its leading sentence, free of tables and symbols.

    Args:
        text: The full result text.

    Returns:
        A single short sentence ending in terminal punctuation, or an empty
        string when ``text`` is empty.
    """
    if not text:
        return ""
    head = text.split(" | ")[0]
    head = re.split(r"(?<=[.!?])\s", head, maxsplit=1)[0]
    head = re.sub(r"^[^0-9A-Za-z]+", "", head).strip().rstrip(":").strip()
    if head and head[-1] not in ".!?":
        head += "."
    return head


def slugify(name: str) -> str:
    """Convert an agent name into a stable, lowercase, dash-separated key.

    Args:
        name: The raw agent/run name.

    Returns:
        A slug suitable as an ``agent_key`` (e.g. ``research-assistant``);
        ``"agent"`` when the name yields no usable characters.
    """
    slug = re.sub(r"[^0-9a-z]+", "-", name.strip().lower()).strip("-")
    return slug or "agent"
