"""LangChain callback handler that streams completed runs to the live server.

One line in an existing LangChain/LangGraph app::

    agent.invoke(inputs, config={"callbacks": [PanoramaCallbackHandler()]})

The handler accumulates each root invocation's tool and model calls in memory
and POSTs one complete run (the live wire format) when the root chain ends.
LangChain itself is only needed at runtime — the import is soft so the module
loads on a base install.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..models import AgentRun, LLMCall, ToolCall
from ..parsers.common import (
    extract_tokens,
    fallback_steps,
    summarize_outcome,
    summarize_request,
    to_text,
)
from . import transport
from .serde import WIRE_VERSION, run_to_dict

try:
    from langchain_core.callbacks import BaseCallbackHandler as _BaseHandler
except ImportError:
    _BaseHandler = object  # type: ignore[assignment, misc]

DEFAULT_ENDPOINT = "http://localhost:8321"


@dataclass
class _PendingCall:
    """Start-time bookkeeping for an in-flight tool or model call."""

    started_monotonic: float
    started_at: datetime
    name: str = ""
    model: str = ""
    arguments: dict = field(default_factory=dict)

    @property
    def latency_ms(self) -> float:
        """Elapsed wall-clock time since the call started, in milliseconds."""
        return (time.monotonic() - self.started_monotonic) * 1000.0


class PanoramaCallbackHandler(_BaseHandler):
    """Streams each completed agent run to a local agent-panorama server.

    Safe by design for production agents: delivery uses a short-timeout
    stdlib POST that never raises, so a missing dashboard cannot crash or
    slow the instrumented app. Thread-safe for concurrent runs sharing one
    handler instance.
    """

    def __init__(self, *, endpoint: str | None = None, timeout: float = 2.0) -> None:
        """Initialize the handler.

        Args:
            endpoint: Base URL of the live server. Defaults to the
                ``AGENT_PANORAMA_ENDPOINT`` env var, then ``http://localhost:8321``.
            timeout: Socket timeout for each delivery POST, in seconds.
        """
        base = endpoint or os.environ.get("AGENT_PANORAMA_ENDPOINT") or DEFAULT_ENDPOINT
        self._ingest_url = base.rstrip("/") + "/api/runs"
        self._timeout = timeout
        self._lock = threading.Lock()
        self._runs: dict[str, AgentRun] = {}
        self._root_of: dict[str, str] = {}
        self._pending: dict[str, _PendingCall] = {}

    def on_chain_start(
        self, serialized: Any, inputs: Any, *, run_id: Any, parent_run_id: Any = None, **kwargs: Any
    ) -> None:
        """Open a new run on the root invocation; track lineage for children."""
        root = self._register(run_id, parent_run_id)
        if parent_run_id is not None:
            return
        session_id, user_id = _identity(kwargs)
        run = AgentRun(
            run_id=str(run_id),
            name=_chain_name(serialized, kwargs),
            session_id=session_id,
            user_id=user_id,
            input_text=summarize_request(inputs),
            start_time=_now(),
        )
        with self._lock:
            self._runs[root] = run

    def on_chain_end(self, outputs: Any, *, run_id: Any, **kwargs: Any) -> None:
        """Finalize and deliver the run when the root chain completes."""
        run = self._pop_root(run_id)
        if run is None:
            return
        run.output_text = summarize_outcome(outputs)
        run.end_time = _now()
        self._deliver(run)

    def on_chain_error(self, error: BaseException, *, run_id: Any, **kwargs: Any) -> None:
        """Finalize and deliver the run when the root chain fails."""
        run = self._pop_root(run_id)
        if run is None:
            return
        run.error_messages.append(str(error))
        run.end_time = _now()
        self._deliver(run)

    def on_llm_start(
        self,
        serialized: Any,
        prompts: Any,
        *,
        run_id: Any,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Stash start time and model name for a completion-style call."""
        self._start_model_call(serialized, run_id, parent_run_id, kwargs)

    def on_chat_model_start(
        self,
        serialized: Any,
        messages: Any,
        *,
        run_id: Any,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """Stash start time and model name for a chat-style call."""
        self._start_model_call(serialized, run_id, parent_run_id, kwargs)

    def on_llm_end(self, response: Any, *, run_id: Any, **kwargs: Any) -> None:
        """Record a finished model call with token usage and latency."""
        pending = self._pending.pop(str(run_id), None)
        input_tokens, output_tokens = _token_counts(response)
        self._append_llm_call(
            run_id,
            LLMCall(
                name=pending.name if pending else "",
                model=pending.model if pending else "",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                timestamp=pending.started_at if pending else _now(),
                latency_ms=pending.latency_ms if pending else None,
            ),
        )

    def on_llm_error(self, error: BaseException, *, run_id: Any, **kwargs: Any) -> None:
        """Record a failed model call."""
        pending = self._pending.pop(str(run_id), None)
        self._append_llm_call(
            run_id,
            LLMCall(
                name=pending.name if pending else "",
                model=pending.model if pending else "",
                timestamp=pending.started_at if pending else _now(),
                latency_ms=pending.latency_ms if pending else None,
                status="error",
                error=str(error),
            ),
        )

    def on_tool_start(
        self,
        serialized: Any,
        input_str: Any,
        *,
        run_id: Any,
        parent_run_id: Any = None,
        inputs: Any = None,
        **kwargs: Any,
    ) -> None:
        """Stash start time, tool name, and arguments for a tool call."""
        self._register(run_id, parent_run_id)
        arguments = inputs if isinstance(inputs, dict) else {"input": to_text(input_str)}
        with self._lock:
            self._pending[str(run_id)] = _PendingCall(
                started_monotonic=time.monotonic(),
                started_at=_now(),
                name=_tool_name(serialized, kwargs),
                arguments=arguments,
            )

    def on_tool_end(self, output: Any, *, run_id: Any, **kwargs: Any) -> None:
        """Record a finished tool call with its output and latency."""
        pending = self._pending.pop(str(run_id), None)
        self._append_tool_call(
            run_id,
            ToolCall(
                name=pending.name if pending else "",
                arguments=pending.arguments if pending else {},
                output=to_text(output),
                timestamp=pending.started_at if pending else _now(),
                latency_ms=pending.latency_ms if pending else None,
            ),
        )

    def on_tool_error(self, error: BaseException, *, run_id: Any, **kwargs: Any) -> None:
        """Record a failed tool call."""
        pending = self._pending.pop(str(run_id), None)
        self._append_tool_call(
            run_id,
            ToolCall(
                name=pending.name if pending else "",
                arguments=pending.arguments if pending else {},
                timestamp=pending.started_at if pending else _now(),
                latency_ms=pending.latency_ms if pending else None,
                status="error",
                error=str(error),
            ),
        )

    def _register(self, run_id: Any, parent_run_id: Any) -> str:
        """Map a callback run id to its root run id, recording lineage."""
        child, parent = str(run_id), None if parent_run_id is None else str(parent_run_id)
        with self._lock:
            root = child if parent is None else self._root_of.get(parent, parent)
            self._root_of[child] = root
            return root

    def _start_model_call(
        self, serialized: Any, run_id: Any, parent_run_id: Any, kwargs: dict
    ) -> None:
        """Shared start bookkeeping for llm and chat-model calls."""
        self._register(run_id, parent_run_id)
        with self._lock:
            self._pending[str(run_id)] = _PendingCall(
                started_monotonic=time.monotonic(),
                started_at=_now(),
                name=_chain_name(serialized, kwargs),
                model=_model_name(serialized, kwargs),
            )

    def _append_llm_call(self, run_id: Any, call: LLMCall) -> None:
        """Attach a model call to its root run, ignoring orphans."""
        with self._lock:
            run = self._run_for(run_id)
            if run is not None:
                run.llm_calls.append(call)

    def _append_tool_call(self, run_id: Any, call: ToolCall) -> None:
        """Attach a tool call to its root run, ignoring orphans."""
        with self._lock:
            run = self._run_for(run_id)
            if run is not None:
                run.tool_calls.append(call)

    def _run_for(self, run_id: Any) -> AgentRun | None:
        """Look up the in-flight run owning a callback run id (lock held)."""
        root = self._root_of.get(str(run_id))
        return self._runs.get(root) if root is not None else None

    def _pop_root(self, run_id: Any) -> AgentRun | None:
        """Remove and return the run if this id is a root, else None."""
        key = str(run_id)
        with self._lock:
            run = self._runs.pop(key, None)
            if run is not None:
                self._root_of = {c: r for c, r in self._root_of.items() if r != key}
            return run

    def _deliver(self, run: AgentRun) -> None:
        """Synthesize narrative steps and post the completed run."""
        run.steps = fallback_steps(run)
        payload = {"version": WIRE_VERSION, "run": run_to_dict(run)}
        transport.post_run(self._ingest_url, payload, timeout=self._timeout)


def _identity(kwargs: dict) -> tuple[str | None, str | None]:
    """Extract session and user ids from callback metadata.

    LangGraph propagates ``thread_id`` into callback metadata; apps can also
    pass explicit ``session_id``/``user_id`` via the invoke config metadata.
    """
    metadata = kwargs.get("metadata")
    if not isinstance(metadata, dict):
        return None, None
    session = metadata.get("session_id") or metadata.get("thread_id")
    user = metadata.get("user_id") or metadata.get("actor")
    return (str(session) if session else None, str(user) if user else None)


def _chain_name(serialized: Any, kwargs: dict) -> str:
    """Best-effort human name for a chain/model from callback metadata."""
    name = kwargs.get("name")
    if isinstance(name, str) and name:
        return name
    if isinstance(serialized, dict):
        for candidate in (serialized.get("name"), _last_id_part(serialized.get("id"))):
            if isinstance(candidate, str) and candidate:
                return candidate
    return "agent"


def _tool_name(serialized: Any, kwargs: dict) -> str:
    """Best-effort tool name from callback metadata."""
    name = _chain_name(serialized, kwargs)
    return name if name != "agent" else "tool"


def _model_name(serialized: Any, kwargs: dict) -> str:
    """Best-effort model identifier from callback metadata."""
    metadata = kwargs.get("metadata")
    if isinstance(metadata, dict):
        model = metadata.get("ls_model_name")
        if isinstance(model, str) and model:
            return model
    if isinstance(serialized, dict):
        params = serialized.get("kwargs")
        if isinstance(params, dict):
            for key in ("model", "model_name"):
                value = params.get(key)
                if isinstance(value, str) and value:
                    return value
    return ""


def _last_id_part(value: Any) -> str:
    """Return the final segment of a serialized LangChain id list."""
    if isinstance(value, list) and value:
        return str(value[-1])
    return ""


def _token_counts(response: Any) -> tuple[int, int]:
    """Extract (input, output) token counts from an LLMResult-like object."""
    llm_output = getattr(response, "llm_output", None)
    if isinstance(llm_output, dict):
        counts = extract_tokens(llm_output.get("token_usage"))
        if counts != (0, 0):
            return counts
    return extract_tokens(_first_usage_metadata(response))


def _first_usage_metadata(response: Any) -> dict | None:
    """Pull usage_metadata from the first generation's message, if present."""
    generations = getattr(response, "generations", None)
    if not generations or not generations[0]:
        return None
    message = getattr(generations[0][0], "message", None)
    usage = getattr(message, "usage_metadata", None)
    return usage if isinstance(usage, dict) else None


def _now() -> datetime:
    """Current UTC time."""
    return datetime.now(timezone.utc)
