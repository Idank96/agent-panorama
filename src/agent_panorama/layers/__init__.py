"""Enrichment layers that run on top of the assembled report.

A layer enriches feed items of a finished :class:`~agent_panorama.models.Report`
in place — it never feeds back into analysis. ``build_report`` stays pure and
deterministic; layers are strictly opt-in, never raise, and degrade to the
deterministic baseline on any failure (missing provider, no API key, model
error).

Current layers:

- :mod:`agent_panorama.layers.summary` — the summarization layer: phrases what
  happened (one action sentence per run or session).
"""
