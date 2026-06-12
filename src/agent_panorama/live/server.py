"""FastAPI server for live mode: ingest runs, serve the report and dashboard.

Requires the ``live`` extra (``pip install 'agent-panorama[live]'``); this
module imports FastAPI eagerly so the CLI can surface a friendly install hint
when it is missing.
"""

from __future__ import annotations

import json
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

from ..analysis import apply_value_rollups, build_report, session_group_key, session_transcript
from ..config import (
    ReportConfig,
    load_config,
    value_config_from_dict,
    value_config_is_empty,
    value_config_to_dict,
)
from ..export import serialize_report
from ..layers.value.interview import (
    advance_interview,
    context_from_payload,
    step_to_dict,
    suggest_options,
    turns_from_payload,
)
from ..layers.value.ontology import (
    ARCHETYPES,
    PRIMITIVES,
    AgentMapping,
    build_agent_mapping,
    context_hash,
    mapping_from_dict,
    mapping_to_dict,
)
from ..models import AgentRun, Report, ValueJudgment
from ..text import slugify
from .serde import run_from_dict

DEFAULT_PORT = 8321
VALUE_CONFIG_FILE = "value_config.json"
ONTOLOGY_MAP_FILE = "ontology_map.json"


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
    _judgments: dict[str, tuple[int, ValueJudgment]] = field(default_factory=dict)
    _mappings: dict[str, tuple[str, AgentMapping]] = field(default_factory=dict)
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

    def cache_judgment(self, group_id: str, turn_count: int, judgment: ValueJudgment) -> None:
        """Cache a value judgment, keeping only the newest per conversation."""
        with self._lock:
            current = self._judgments.get(group_id)
            if current is None or current[0] <= turn_count:
                self._judgments[group_id] = (turn_count, judgment)

    def get_judgment(self, group_id: str) -> ValueJudgment | None:
        """Return the latest cached judgment for a conversation, if any."""
        with self._lock:
            cached = self._judgments.get(group_id)
            return cached[1] if cached else None

    def clear_judgments(self) -> None:
        """Drop all cached judgments (the value definition changed)."""
        with self._lock:
            self._judgments.clear()

    def cache_mapping(self, agent_key: str, ctx_hash: str, mapping: AgentMapping) -> None:
        """Cache one agent's canonical mapping, keyed by its context hash."""
        with self._lock:
            self._mappings[agent_key] = (ctx_hash, mapping)

    def mapping_hash(self, agent_key: str) -> str | None:
        """Return the context hash the cached mapping was built from, if any."""
        with self._lock:
            cached = self._mappings.get(agent_key)
            return cached[0] if cached else None

    def mapping_entries(self) -> dict[str, tuple[str, AgentMapping]]:
        """Return a copy of all cached (hash, mapping) entries by agent key."""
        with self._lock:
            return dict(self._mappings)

    def clear_mappings(self) -> None:
        """Drop all cached canonical mappings (the value layer was disabled)."""
        with self._lock:
            self._mappings.clear()


def create_app(config: ReportConfig, store: RunStore, data_dir: Path | None = None) -> FastAPI:
    """Build the live-mode FastAPI application.

    Args:
        config: Report configuration applied when building each report.
        store: The run store backing the API.
        data_dir: Directory the value-definition sidecars live in (defaults to
            the current working directory).

    Returns:
        The configured FastAPI app.
    """
    app = FastAPI(title="agent-panorama live")
    _allow_cors(app)
    _add_api_routes(app, config, store, Path(data_dir or "."))
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


def _add_api_routes(app: FastAPI, config: ReportConfig, store: RunStore, data_dir: Path) -> None:
    """Register the ingest, report, value-config, and health endpoints."""

    @app.post("/api/runs")
    def ingest(body: dict) -> dict:
        raw = body.get("run")
        run = run_from_dict(raw if isinstance(raw, dict) else body)
        store.add(run)
        _schedule_session_summary(run, store, config)
        _schedule_value_judgment(run, store, config)
        _schedule_mapping(run, store, config, data_dir)
        return {"ok": True, "run_id": run.run_id}

    @app.get("/api/report")
    def report() -> dict:
        built = build_report(store.snapshot(), config)
        _apply_cached_summaries(built, store)
        _apply_cached_judgments(built, store)
        return serialize_report(built, config)

    @app.get("/api/value-config")
    def get_value_config() -> dict:
        return _value_config_response(config, store)

    @app.post("/api/value-config")
    def post_value_config(body: dict) -> dict:
        new_value = value_config_from_dict(body or {})
        if value_config_is_empty(new_value):
            new_value = None
        config.value = new_value
        _write_value_sidecar(data_dir, new_value)
        threading.Thread(
            target=_apply_value_config_change,
            args=(store, config, data_dir),
            daemon=True,
        ).start()
        return {"ok": True, "enabled": new_value is not None}

    @app.post("/api/value-interview")
    def value_interview(body: dict) -> dict:
        agent_name = str(body.get("agent_name") or "this agent")
        current = context_from_payload(body.get("current"))
        if body.get("action") == "suggest":
            question = body.get("question") or {}
            options = suggest_options(
                agent_name,
                current,
                question.get("field"),
                str(question.get("prompt") or ""),
                config.summarize_model,
            )
            return {"suggestions": options}
        transcript = turns_from_payload(body.get("transcript"))
        step = advance_interview(agent_name, transcript, current, config.summarize_model)
        return step_to_dict(step)

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
    from ..layers.summary import summarize_session

    phrase = summarize_session(session_transcript(turns), config.summarize_model)
    if phrase:
        store.cache_summary(group_id, len(turns), phrase)


def _schedule_value_judgment(run: AgentRun, store: RunStore, config: ReportConfig) -> None:
    """Kick off background value judging for the run's conversation.

    Mirrors the session-summary machinery: a no-op without a ``value:``
    config, never blocks ingest, and the (group, turn-count) cache means a
    conversation is only re-judged when a new turn lands — never per poll.
    Sessionless runs are judged once, keyed by their own ``run_id``.
    """
    if config.value is None:
        return
    group_id = session_group_key(run)
    turns = _session_turns(store, group_id) if group_id else [run]
    thread = threading.Thread(
        target=_judge_into_cache,
        args=(store, config, group_id or run.run_id, turns),
        daemon=True,
    )
    thread.start()


def _judge_into_cache(
    store: RunStore, config: ReportConfig, group_id: str, turns: list[AgentRun]
) -> None:
    """Judge one conversation and cache the result (background thread body)."""
    from ..layers.value import judge_session

    if config.value is None or not turns:
        return
    context = config.value.context_for(slugify(turns[-1].name))
    exchange = judge_session(turns, context, config.value.judge_model)
    if exchange.judgment is not None:
        store.cache_judgment(group_id, len(turns), exchange.judgment)


def _apply_cached_summaries(report: Report, store: RunStore) -> None:
    """Overwrite aggregated feed items' action text with cached LLM phrases."""
    for item in report.feed:
        if item.turn_count > 1:
            phrase = store.get_summary(item.run_id)
            if phrase:
                item.action = phrase


def _apply_cached_judgments(report: Report, store: RunStore) -> None:
    """Attach cached value judgments to feed items and refresh value rollups."""
    applied = False
    for item in report.feed:
        judgment = store.get_judgment(item.run_id)
        if judgment is not None:
            item.value = judgment
            applied = True
    if applied:
        apply_value_rollups(report)


def _schedule_mapping(run: AgentRun, store: RunStore, config: ReportConfig, data_dir: Path) -> None:
    """Ensure the agent's canonical mapping is current, in the background.

    A no-op without a ``value:`` config; otherwise rebuilds the mapping only
    when the agent's value context has changed since it was last mapped, so a
    new agent appearing mid-session gets mapped without re-running the LLM per
    turn.
    """
    if config.value is None:
        return
    thread = threading.Thread(
        target=_ensure_mapping,
        args=(store, config, data_dir, slugify(run.name)),
        daemon=True,
    )
    thread.start()


def _ensure_mapping(store: RunStore, config: ReportConfig, data_dir: Path, agent_key: str) -> None:
    """Build and cache one agent's mapping if missing or stale (thread body)."""
    if config.value is None:
        return
    context = config.value.context_for(agent_key)
    digest = context_hash(context)
    if store.mapping_hash(agent_key) == digest:
        return
    mapping = build_agent_mapping(agent_key, context, config.summarize_model)
    store.cache_mapping(agent_key, digest, mapping)
    _write_mapping_sidecar(data_dir, store)


def _value_config_response(config: ReportConfig, store: RunStore) -> dict:
    """Assemble the GET /api/value-config payload."""
    return {
        "enabled": config.value is not None,
        "config": value_config_to_dict(config.value),
        "agents": _known_agents(store),
        "mappings": {
            key: mapping_to_dict(mapping) for key, (_, mapping) in store.mapping_entries().items()
        },
        "ontology": {"archetypes": ARCHETYPES, "primitives": PRIMITIVES},
    }


def _known_agents(store: RunStore) -> list[dict[str, str]]:
    """Distinct agents seen in the store, so the UI can offer them to define."""
    seen: dict[str, str] = {}
    for run in store.snapshot():
        seen.setdefault(slugify(run.name), run.name)
    return [{"key": key, "name": name} for key, name in sorted(seen.items())]


def _apply_value_config_change(store: RunStore, config: ReportConfig, data_dir: Path) -> None:
    """Re-map and re-judge everything after the value definition changed.

    Runs in one background sweep (never per poll): rebuild canonical mappings,
    drop the now-stale judgment cache, then re-judge stored conversations up to
    ``max_judgments``. With the layer disabled it clears mappings instead.
    """
    if config.value is None:
        store.clear_judgments()
        store.clear_mappings()
        _write_mapping_sidecar(data_dir, store)
        return
    _rebuild_mappings(store, config, data_dir)
    store.clear_judgments()
    _rejudge_all(store, config)


def _rebuild_mappings(store: RunStore, config: ReportConfig, data_dir: Path) -> None:
    """Rebuild mappings for every agent in the store or with a defined context."""
    if config.value is None:
        return
    keys = {slugify(run.name) for run in store.snapshot()} | set(config.value.contexts)
    for agent_key in keys:
        context = config.value.context_for(agent_key)
        mapping = build_agent_mapping(agent_key, context, config.summarize_model)
        store.cache_mapping(agent_key, context_hash(context), mapping)
    _write_mapping_sidecar(data_dir, store)


def _rejudge_all(store: RunStore, config: ReportConfig) -> None:
    """Re-judge stored conversations against the new value definition."""
    if config.value is None:
        return
    conversations = _conversations(store)
    if not config.value.include_single_runs:
        conversations = [(gid, turns) for gid, turns in conversations if len(turns) > 1]
    for group_id, turns in conversations[: config.value.max_judgments]:
        _judge_into_cache(store, config, group_id, turns)


def _conversations(store: RunStore) -> list[tuple[str, list[AgentRun]]]:
    """Group stored runs into conversations, newest conversation first."""
    groups: dict[str, list[AgentRun]] = {}
    for run in store.snapshot():
        groups.setdefault(session_group_key(run) or run.run_id, []).append(run)

    def _start(run: AgentRun) -> float:
        return run.start_time.timestamp() if run.start_time else float("inf")

    for turns in groups.values():
        turns.sort(key=_start)
    return sorted(groups.items(), key=lambda kv: _start(kv[1][-1]), reverse=True)


def _write_value_sidecar(data_dir: Path, value: object) -> None:
    """Persist (or remove) the value-definition sidecar."""
    path = data_dir / VALUE_CONFIG_FILE
    if value is None:
        path.unlink(missing_ok=True)
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = value_config_to_dict(value)  # type: ignore[arg-type]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_mapping_sidecar(data_dir: Path, store: RunStore) -> None:
    """Persist the canonical mappings (with their context hashes) for reuse."""
    entries = store.mapping_entries()
    path = data_dir / ONTOLOGY_MAP_FILE
    if not entries:
        path.unlink(missing_ok=True)
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        key: {"hash": digest, "mapping": mapping_to_dict(mapping)}
        for key, (digest, mapping) in entries.items()
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_value_sidecar(data_dir: Path, config: ReportConfig) -> None:
    """Overlay a persisted value definition onto the config at startup."""
    raw = _read_json(data_dir / VALUE_CONFIG_FILE)
    if isinstance(raw, dict) and raw:
        config.value = value_config_from_dict(raw)


def _load_mapping_sidecar(data_dir: Path, store: RunStore) -> None:
    """Populate the store's mapping cache from the sidecar at startup."""
    raw = _read_json(data_dir / ONTOLOGY_MAP_FILE)
    if not isinstance(raw, dict):
        return
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        mapping = mapping_from_dict(entry.get("mapping") or {})
        store.cache_mapping(str(key), str(entry.get("hash") or ""), mapping)


def _read_json(path: Path) -> object | None:
    """Read and parse a JSON file, returning None when absent or malformed."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


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
    data_dir: str | Path | None = None,
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
        data_dir: Directory for the editable value-definition sidecars
            (defaults to the current working directory). A persisted definition
            there overrides the YAML ``value:`` block at startup.

    Raises:
        OSError: If the port is already in use (with a hint to pick another).
    """
    import uvicorn

    _ensure_port_free(host, port)
    resolved_dir = Path(data_dir or ".").resolve()
    config = load_config(config_path)
    if summarize_model is not None:
        config.summarize_model = summarize_model
    _load_value_sidecar(resolved_dir, config)
    store = RunStore(max_runs=max_runs)
    _load_mapping_sidecar(resolved_dir, store)
    app = create_app(config, store, resolved_dir)
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
