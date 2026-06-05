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

from ..analysis import build_report
from ..config import ReportConfig, load_config
from ..export import serialize_report
from ..models import AgentRun
from .serde import run_from_dict

DEFAULT_PORT = 8321


@dataclass
class RunStore:
    """Thread-safe in-memory store of completed runs.

    Re-posting a run id replaces the previous version (idempotent ingest);
    when ``max_runs`` is set the oldest runs are trimmed first. Persistence
    (e.g. a JSONL journal) is a deliberate extension point, not yet built.
    """

    max_runs: int | None = None
    _runs: list[AgentRun] = field(default_factory=list)
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
        return {"ok": True, "run_id": run.run_id}

    @app.get("/api/report")
    def report() -> dict:
        return serialize_report(build_report(store.snapshot(), config), config)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "runs": len(store.snapshot())}


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
) -> None:
    """Run the live dashboard server until interrupted.

    Args:
        port: TCP port to listen on.
        host: Interface to bind (localhost by default).
        config_path: Optional YAML report config.
        max_runs: Optional cap on retained runs (oldest trimmed first).
        open_browser: Open the dashboard in the default browser on start.

    Raises:
        OSError: If the port is already in use (with a hint to pick another).
    """
    import uvicorn

    _ensure_port_free(host, port)
    app = create_app(load_config(config_path), RunStore(max_runs=max_runs))
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
