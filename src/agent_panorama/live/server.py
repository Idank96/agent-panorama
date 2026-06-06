"""FastAPI server for live mode: ingest runs, serve the report and dashboard.

Requires the ``live`` extra (``pip install 'agent-panorama[live]'``); this
module imports FastAPI eagerly so the CLI can surface a friendly install hint
when it is missing.
"""

from __future__ import annotations

import socket
import threading
import webbrowser
from contextlib import ExitStack
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..analysis import build_report, session_group_key, session_transcript
from ..config import ReportConfig, load_config
from ..export import serialize_report
from ..models import AgentRun, Report
from .serde import run_from_dict

DEFAULT_PORT = 8321


@dataclass
class RunStore:
    """Thread-safe in-memory store of completed runs and session phrases.

    Re-posting a run id replaces the previous version (idempotent ingest);
    when ``max_runs`` is set the oldest runs are trimmed first. Session
    summaries cache the latest LLM phrase per session group, keyed so a stale
    (older turn-count) phrase is replaced when a new turn lands. Persistence
    (e.g. a JSONL journal) is a deliberate extension point, not yet built.
    """

    max_runs: int | None = None
    _runs: list[AgentRun] = field(default_factory=list)
    _summaries: dict[str, tuple[int, str]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, run: AgentRun) -> None:
        """Add or replace a run, trimming the oldest beyond ``max_runs``."""
        with self._lock:
            self._runs = [r for r in self._runs if r.run_id != run.run_id]
            self._runs.append(run)
            if self.max_runs is not None and len(self._runs) > self.max_runs:
                self._runs = self._runs[-self.max_runs :]

    def snapshot(self) -> list[AgentRun]:
        """Return a copy of the current runs."""
        with self._lock:
            return list(self._runs)

    def cache_summary(self, group_id: str, turn_count: int, phrase: str) -> None:
        """Cache a session phrase, keeping only the newest per group."""
        with self._lock:
            current = self._summaries.get(group_id)
            if current is None or current[0] <= turn_count:
                self._summaries[group_id] = (turn_count, phrase)

    def get_summary(self, group_id: str) -> str | None:
        """Return the latest cached phrase for a session group, if any."""
        with self._lock:
            cached = self._summaries.get(group_id)
            return cached[1] if cached else None


def create_app(config: ReportConfig, store: RunStore) -> FastAPI:
    """Build the live-mode FastAPI application.

    Args:
        config: Report configuration applied when building each report.
        store: The run store backing the API.

    Returns:
        The configured FastAPI app.
    """
    app = FastAPI(title="agent-panorama live")
    _allow_cors(app)
    _add_api_routes(app, config, store)
    _mount_static(app)
    return app


def _allow_cors(app: FastAPI) -> None:
    """Allow cross-origin requests (the Vite dev server runs on another port)."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _add_api_routes(app: FastAPI, config: ReportConfig, store: RunStore) -> None:
    """Register the ingest, report, and health endpoints."""

    @app.post("/api/runs")
    def ingest(body: dict) -> dict:
        raw = body.get("run")
        run = run_from_dict(raw if isinstance(raw, dict) else body)
        store.add(run)
        _schedule_session_summary(run, store, config)
        return {"ok": True, "run_id": run.run_id}

    @app.get("/api/report")
    def report() -> dict:
        built = build_report(store.snapshot(), config)
        _apply_cached_summaries(built, store)
        return serialize_report(built, config)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "runs": len(store.snapshot())}


def _schedule_session_summary(run: AgentRun, store: RunStore, config: ReportConfig) -> None:
    """Kick off background LLM phrasing for the run's session, if it has one.

    Runs in a daemon thread so ingest never waits on a model call; until the
    phrase lands in the cache the feed shows the deterministic session line.
    """
    group_id = session_group_key(run)
    if group_id is None:
        return
    turns = _session_turns(store, group_id)
    thread = threading.Thread(
        target=_summarize_session_into_cache,
        args=(store, config, group_id, turns),
        daemon=True,
    )
    thread.start()


def _session_turns(store: RunStore, group_id: str) -> list[AgentRun]:
    """Collect the session's runs from the store, ordered by start time."""
    turns = [run for run in store.snapshot() if session_group_key(run) == group_id]
    turns.sort(key=lambda r: r.start_time.timestamp() if r.start_time else float("inf"))
    return turns


def _summarize_session_into_cache(
    store: RunStore, config: ReportConfig, group_id: str, turns: list[AgentRun]
) -> None:
    """Phrase one session and cache the result (background thread body)."""
    from ..summarize import summarize_session

    phrase = summarize_session(session_transcript(turns), config.summarize_model)
    if phrase:
        store.cache_summary(group_id, len(turns), phrase)


def _apply_cached_summaries(report: Report, store: RunStore) -> None:
    """Overwrite aggregated feed items' action text with cached LLM phrases."""
    for item in report.feed:
        if item.turn_count > 1:
            phrase = store.get_summary(item.run_id)
            if phrase:
                item.action = phrase


def _mount_static(app: FastAPI) -> None:
    """Serve the bundled dashboard at ``/`` when a build is packaged."""
    static_dir = _static_dir(app)
    if static_dir is not None and (static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="dashboard")
        return

    @app.get("/")
    def placeholder() -> dict:
        return {
            "message": "agent-panorama live API is running, but no dashboard build "
            "is bundled. Use the Vite dev server (frontend/: npm run dev) or build "
            "the frontend (npm run build) and restart.",
            "report": "/api/report",
        }


def _static_dir(app: FastAPI) -> Path | None:
    """Resolve the packaged static directory to a real filesystem path."""
    try:
        static = resources.files("agent_panorama") / "static"
        stack = ExitStack()
        path = stack.enter_context(resources.as_file(static))
        app.router.on_shutdown.append(stack.close)
        return path if path.is_dir() else None
    except (FileNotFoundError, ModuleNotFoundError):
        return None


def serve(
    port: int = DEFAULT_PORT,
    host: str = "127.0.0.1",
    config_path: str | Path | None = None,
    max_runs: int | None = None,
    open_browser: bool = False,
    summarize_model: str | None = None,
) -> None:
    """Run the live dashboard server until interrupted.

    Args:
        port: TCP port to listen on.
        host: Interface to bind (localhost by default).
        config_path: Optional YAML report config.
        max_runs: Optional cap on retained runs (oldest trimmed first).
        open_browser: Open the dashboard in the default browser on start.
        summarize_model: Optional LangChain model id for session phrasing,
            overriding the config's ``summarize_model``.

    Raises:
        OSError: If the port is already in use (with a hint to pick another).
    """
    import uvicorn

    _ensure_port_free(host, port)
    config = load_config(config_path)
    if summarize_model is not None:
        config.summarize_model = summarize_model
    app = create_app(config, RunStore(max_runs=max_runs))
    if open_browser:
        webbrowser.open(f"http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def _ensure_port_free(host: str, port: int) -> None:
    """Fail fast with a clear message when the port is already taken."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError as error:
            raise OSError(
                f"Port {port} on {host} is already in use (another dashboard or app?). "
                f"Stop it or pick another port: agent-panorama serve --port {port + 1}"
            ) from error
