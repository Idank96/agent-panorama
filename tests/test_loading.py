"""Tests for multi-input loading and session / time-window filtering."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402

import pytest  # noqa: E402

from agent_panorama.core import load_runs  # noqa: E402

_LANGFUSE = _bootstrap.EXAMPLES / "langfuse_traces.json"


def _write_trace(path: Path, run_id: str, name: str, timestamp: str) -> None:
    trace = {"id": run_id, "name": name, "timestamp": timestamp, "observations": []}
    path.write_text(json.dumps([trace]), encoding="utf-8")


def test_single_file_loads_all_runs() -> None:
    runs = load_runs(_LANGFUSE)
    assert len(runs) == 3


def test_glob_and_dir_expand_and_dedupe(tmp_path: Path) -> None:
    _write_trace(tmp_path / "a.json", "ra-1", "agent-a", "2026-05-20T09:00:00Z")
    _write_trace(tmp_path / "b.json", "rb-1", "agent-b", "2026-05-21T09:00:00Z")
    via_glob = load_runs(str(tmp_path / "*.json"))
    via_dir = load_runs(tmp_path)
    via_list = load_runs([str(tmp_path / "a.json"), str(tmp_path), str(tmp_path / "*.json")])
    assert len(via_glob) == 2
    assert len(via_dir) == 2
    assert len(via_list) == 2


def test_zero_matches_raises() -> None:
    with pytest.raises(ValueError):
        load_runs("nonexistent/*.json")


def test_session_filter(tmp_path: Path) -> None:
    _write_trace(tmp_path / "a.json", "session-abc", "agent-a", "2026-05-20T09:00:00Z")
    _write_trace(tmp_path / "b.json", "other-xyz", "agent-b", "2026-05-21T09:00:00Z")
    runs = load_runs(tmp_path, session="session-abc")
    assert len(runs) == 1
    assert runs[0].run_id == "session-abc"


def test_time_window_filter(tmp_path: Path) -> None:
    _write_trace(tmp_path / "a.json", "r1", "agent-a", "2026-05-19T09:00:00Z")
    _write_trace(tmp_path / "b.json", "r2", "agent-b", "2026-05-25T09:00:00Z")
    runs = load_runs(tmp_path, since="2026-05-20", until="2026-05-31")
    assert [r.run_id for r in runs] == ["r2"]


def test_time_window_accepts_datetime(tmp_path: Path) -> None:
    _write_trace(tmp_path / "a.json", "r1", "agent-a", "2026-05-19T09:00:00Z")
    lower = datetime(2026, 5, 20, tzinfo=timezone.utc)
    runs = load_runs(tmp_path, since=lower)
    assert runs == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
