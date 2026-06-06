# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`agent-panorama` turns Langfuse / LangSmith agent-trace exports into a human-readable
**Agent Activity Report** (Markdown + self-contained HTML) aimed at non-engineers. It
is a published, pip-installable library + CLI (PyPI: `agent-panorama`).

## Commands

Uses **uv** exclusively. Distribution name is `agent-panorama`; import package is
`agent_panorama` (src layout).

```bash
uv sync --extra dev                      # set up env with dev deps
uv run python tests/run_all_tests.py     # full test suite
uv run pytest tests/test_parsers.py -v   # one test file
uv run pytest tests/test_parsers.py::test_langfuse_run_tree_flattens  # one test
uv run ruff check src tests              # lint
uv run ruff format --check src tests     # format check
uv run agent-panorama generate --input examples/langfuse_traces.json --output ./report
uv build                                 # sdist + wheel into dist/
```

CI (`.github/workflows/ci.yml`) runs ruff + the suite on Python 3.10/3.11/3.12.
Validate those three commands locally before pushing — the first CI run should be green.

The `frontend/` dashboard is a separate npm project (run commands from `frontend/`):

```bash
npm install        # one-time
npm run dev        # Vite dev server; proxies /api to a local `agent-panorama serve`
npm run test       # vitest run (the loadFeed.test.ts suite)
npm run build      # tsc -b && vite build → ../src/agent_panorama/static/ (bundled into wheels)
npm run sync:feed  # cp ../report/report.json public/feed.json (refresh the data it renders)
```

CI runs a `frontend` job (`npm ci && npm run test && npm run build`) alongside the
Python matrix, but still run both locally before pushing.

## Architecture: a three-stage pipeline over a normalized model

The whole system is **parse → analyze → render**, with `models.py` as the contract that
decouples the stages. Understanding `models.AgentRun` first makes everything else click.

1. **Parse** (`parsers/`) — each vendor parser normalizes a raw export into a list of
   `AgentRun`. `parsers/__init__.py` holds the `PARSERS` registry and a dispatch
   `parse(payload, input_type)`. Parsers are purely structural: they extract tool calls,
   model calls, tokens, timings, and errors — they do **not** interpret outcomes.
2. **Analyze** (`analysis.py`) — `build_report(runs, config)` enriches each run with the
   *business* signals (outcome: success/failure/escalated, retry count, fallback,
   anomalies) and assembles the cross-run decision log. This is the only stage that knows
   about `ReportConfig`.
3. **Render** (`render.py` + `templates/`) — Jinja2 renders the `Report` to Markdown or
   HTML. `core.generate_report(...)` is the top-level orchestrator (parse → build → write
   files) and the main public API; `cli.py` is a thin click wrapper over it.

Separation of concerns is deliberate: parsers know vendor formats, analysis knows
business meaning, templates know presentation. Keep that boundary when extending.

## v0.2 — the fleet view (many traces, one report)

v0.2 aggregates *many* traces into one fleet-level report and exposes it as JSON for a
dashboard:

- **Multi-input loading** (`core.load_runs`): accepts a single path, a glob, a directory,
  or a list of any of those; expands + dedupes, parses each via `parsers.parse`, then
  filters by `session` (run id match) and a `[since, until]` time window over
  `start_time`. `build_report_from_inputs` / `generate_report(inputs=...)` wrap it
  (the old single-path `generate_report` call still works).
- **Cross-agent feed + rollups** (`analysis._build_feed`, `_build_rollups`): `Report.feed`
  is one newest-first `FeedItem` per run (agent, action text, outcome, tokens, cost, facts,
  anomalies); `Report.rollups` is one `AgentRollup` per agent (`agent_key` = `slugify(name)`)
  with success/escalation/failure/retry rates and token/cost totals. Both live in
  `models.py` alongside the existing `DecisionLogEntry`.
- **JSON export** (`export.serialize_report` → `feed.json`/`report.json`): the stable
  contract the React dashboard in `frontend/` consumes — `generated_at`, `time_range`,
  `totals` (runs/steps/tokens/cost), `feed`, `rollups`, `decision_log`. Written when the
  `"json"` format is requested.
- **Shared text helpers** (`text.py`): `condense` (leading-sentence reducer, used by both
  the feed and `render`) and `slugify` (the `agent_key`). Factored out of `render` to keep
  feed and rendering DRY.
- **`frontend/`** (top-level, outside the PyPI package): a Vite + React + TypeScript
  dashboard that reads `feed.json` (falls back to bundled demo data). Backend and frontend
  are two clean dirs; the package is unaffected.

## v0.3 — live mode (`src/agent_panorama/live/`)

Live mode streams **completed** runs from a running LangChain/LangGraph app to a local
server that serves the dashboard, updating within one poll tick (~3 s). The split is by
dependency weight, deliberately:

- **`live/handler.py`** — `PanoramaCallbackHandler`, the one-line integration
  (`config={"callbacks": [PanoramaCallbackHandler()]}`). Works from a **base install**:
  the `langchain_core` base class is a soft import, delivery uses stdlib `urllib`
  (`live/transport.py`, never raises, warns once), so the instrumented app never needs
  the server deps. Accumulates per-root-run state keyed by root `run_id` (thread-safe,
  `_root_of` maps child → root), builds an `AgentRun` from the callback hooks, synthesizes
  steps via `parsers.common.fallback_steps`, and POSTs once on root chain end/error. All
  hooks take `**kwargs` and read optionals via `.get` to survive LangChain version drift.
- **`live/serde.py`** — the versioned wire format (`{"version": 1, "run": {...}}`),
  `run_to_dict`/`run_from_dict`. Tolerant inbound: malformed fields degrade, unknown
  outcomes become `UNKNOWN`. The server re-derives outcome/anomalies/cost via analysis,
  so handler-side values are informational.
- **`live/server.py`** — FastAPI app behind the `live` extra
  (`pip install 'agent-panorama[live]'`; fastapi/uvicorn in `dev` too so tests run in CI).
  `POST /api/runs` (plain dict body, no pydantic — house style), `GET /api/report`
  (recomputes `build_report` + `serialize_report` per request; fine for polling),
  `GET /healthz`, and the bundled dashboard at `/`. `RunStore` is in-memory, idempotent
  on `run_id`, with optional `--max-runs` trimming (persistence is a noted extension
  point). The CLI `serve` command catches the ImportError and prints the install hint.
- **Frontend polling** — `loadFeed(now)` tries `/api/report` → `feed.json` → demo data;
  `App.tsx` polls every 3 s, resetting selection/decisions only on first load. Vite dev
  proxies `/api` → `localhost:8321`.
- **Static bundling (the subtle bit)** — `npm run build` outputs to
  `src/agent_panorama/static/` (gitignored except `.gitkeep`, which the build script
  re-touches because `emptyOutDir` wipes it). `[tool.hatch.build] artifacts` keeps the
  gitignored build output in wheels/sdists — don't replace it with `force-include`,
  which collides with the tracked `.gitkeep`. **Build the frontend before `uv build`**
  when cutting a release; verify with `unzip -l dist/*.whl | grep static/index.html`.

## Session aggregation (v0.3.x): the feed's unit is (session, actor)

A multi-turn conversation is ONE feed entry, not N. The pieces:

- **Identity**: `AgentRun.session_id`/`user_id`. Langfuse parser reads top-level
  `sessionId`/`userId` (metadata fallback); LangSmith parser reads `extra.metadata`
  (`thread_id`/`session_id`/`user_id`) and **deliberately ignores top-level `session_id`**
  (that's the tracer project id). The live handler reads invoke-config `metadata`
  (`thread_id` arrives automatically from LangGraph). `--session` filtering now matches the
  real field first.
- **Grouping** (`analysis`): `session_group_key(run)` → `"session:{agent_key}:{session}:{actor}"`
  — also the aggregated item's `run_id`, deliberately stable across rebuilds (frontend
  selection/decisions key on it). `_build_feed` partitions sessionless runs (one item each,
  unchanged) from session groups (`_to_group_item`): worst-of outcome, latest-turn timestamp,
  summed tokens/retries/cost, `Interactions: N · x ok · y failed` fact, `turn_count`/`run_ids`.
  Rollup rates stay per-run; `AgentRollup.sessions` counts distinct conversations.
- **LLM phrasing is enrichment, not analysis**: `build_report` stays pure with a deterministic
  session line; `layers.summary.build_session_exchange` (session prompt via `_invoke_with`)
  phrases the transcript from `analysis.session_transcript`. Batch: `core.apply_session_summaries`
  runs after `rebuild_feed` (which would otherwise clobber it) and logs to `llm_calls.log`.
  Live: ingest spawns a daemon thread, caches per `(group_id, turn_count)` in `RunStore`,
  `/api/report` applies the cache — never blocks ingest, never re-summarizes per poll.
  Failures (no provider extra / key) degrade to the deterministic line; phrasing needs a
  provider extra (e.g. `[gemini]` + GOOGLE_API_KEY in `.env`).

## v0.4 — two layers over one substrate (`layers/`)

The product is two **lenses** over the same normalized conversations, and `layers/`
makes that the code structure (mirroring how `parsers/` holds input formats). The layer
contract (`layers/__init__.py`): a layer enriches feed items of a *finished* report in
place, never feeds back into analysis, never raises, and degrades to the deterministic
baseline. `build_report` stays pure.

- **`layers/summary.py`** — the summarization layer ("what happened"), moved from
  `summarize.py`; `agent_panorama.summarize` remains a back-compat re-export shim.
- **`layers/value/`** — the value layer ("was it worth it"), absorbed from the standalone
  `value-layer` prototype (never published; the old folder is archived). An LLM judge
  (`judge.py:judge_session`) scores each conversation against the customer's own
  `ValueContext` (`context.py`: domain, user_goal, success_criteria, custom_dimensions)
  and returns a plain `ValueJudgment` (in `models.py`). Pydantic appears ONLY in
  `layers/value/_schema.py` (the structured-output contract), imported lazily at judge
  call time — it arrives transitively with any provider extra, so the base install never
  needs it. Same `init_chat_model` path as the summary layer ⇒ the existing provider
  extras power both; there is no separate `[value]` extra.
- **Opt-in by config presence**: a `value:` YAML block enables judging (mirrors
  `model_prices` enabling cost). `ValueLayerConfig.context_for(agent_key)` resolves
  per-agent contexts merged field-wise over `default` — a fleet rarely has one goal.
- **Batch**: `core.apply_value_judgments` runs right after `apply_session_summaries` —
  newest feed items first, `max_judgments` hard cap (default 50, the cost guard),
  sessions always / single runs unless `include_single_runs: false`, audited to
  `llm_calls.log`. Then `analysis.apply_value_rollups` folds `judged`/`avg_value_score`/
  `valuable_rate`/`cost_per_valuable_usd` into rollups (valuable = overall score ≥ 6,
  `analysis.VALUABLE_SCORE_THRESHOLD`).
- **Live**: mirrors the summary machinery exactly — ingest spawns a daemon thread,
  `RunStore` caches one judgment per conversation keyed by turn count (re-judged only
  when a new turn lands, never per poll; sessionless runs keyed by `run_id`),
  `/api/report` applies the cache.
- **JSON contract additions are purely additive**: `feed[].value`, rollup value fields,
  `totals.value` — all `null` when the layer is off; the frontend hides the Value view
  entirely then (`showValue` in `App.tsx`). The Value view sorts conversations
  lowest-value first and leads with **cost per valuable conversation** (needs
  `model_prices` too).

## The hard part: real-world Langfuse parsing

`parsers/langfuse.py` and `parsers/common.py` carry the non-obvious knowledge, learned
from real exports (synthetic samples guessed the schema wrong). Before changing parsing,
read these and preserve the handling for:

- **Export shapes:** single trace dict, the single-trace `{"trace": {...},
  "observations": [...]}` shape (observations are a *sibling*, not nested), a list, and
  the `{"data": [...]}` list-API shape. See `_extract_traces` / `_normalize_trace`.
- **Observation types:** `GENERATION` → model call; `TOOL` → authoritative tool call;
  `SPAN`/`EVENT` → treated as a tool only when the trace has no `TOOL` observations (so
  nested spans under a tool aren't double-counted). `AGENT`/`CHAIN` are orchestration.
- **Tool-call de-duplication:** a tool can be both *declared* on a generation
  (`toolCalls` / OpenAI-style `tool_calls`) and *executed* as a span/TOOL; `_merge_tool_calls`
  keeps the execution and drops the duplicate declaration.
- **Tokens:** prefer flat `inputUsage`/`outputUsage`, fall back to `usage`/`usageDetails`.
- **Double-encoded payloads:** trace `input`/`output` are often a JSON string of a JSON
  string. `common._maybe_json` unwraps repeatedly; `summarize_request`/`summarize_outcome`
  pull the first human message (the ask) and last AI message (the result) out of
  LangGraph/LangChain `messages` so the report reads in plain language, not raw JSON.

`parsers/langsmith.py` flattens a LangSmith run tree (root run + descendants by
`parent_run_id`) into one `AgentRun` per root.

To add a new input format: write `parse(payload) -> list[AgentRun]` and register it in
`parsers/__init__.py:PARSERS`. Nothing downstream changes.

## Conventions and constraints specific to this repo

- **Dollar-cost estimation is opt-in (as of v0.2).** Tokens remain the primary metric and
  the zero-config default (no prices ⇒ `cost_usd` stays `None` everywhere). Cost is enabled
  only by supplying a `model_prices` table in the YAML config (`{ "<model-substring>":
  {input, output} }`, USD per 1M tokens, longest substring match wins). `config.price_for`
  resolves it; `analysis._estimate_cost` sums it per run. This deliberately reverses the
  earlier "USD out of scope" rule — never hardcode volatile prices in code.
- **Example data must stay obviously generic** (`web_search`, `get_weather`, `send_email`,
  `research-assistant`). Never use names that could read as a real company's internal
  tooling — the published repo's history was already scrubbed once for this. Real trace
  inputs belong only in the gitignored `traces/`, never committed.
- **HTML autoescaping is intentional and load-bearing:** `render._autoescape` enables
  escaping only for the `.html.j2` template (not Markdown). The template filename ends in
  `.j2`, so the naive `select_autoescape(["html"])` would silently disable it — don't
  "simplify" this back.
- **Tests run without an install** via the src-layout bootstrap: `conftest.py` and
  `_bootstrap.py` put `src/` on `sys.path`, each test file is independently runnable, and
  `pyproject.toml` gives `tests/*` a ruff ignore for `E402`/`I001` (path setup precedes
  imports by design).
- Internal models are **dataclasses**, not pydantic, to keep dependencies minimal
  (`click`, `jinja2`, `pyyaml` only).

## Release flow (PyPI Trusted Publishing)

Publishing is automated via `.github/workflows/publish.yml` (OIDC, no tokens) on GitHub
Release. To cut a release: **build the frontend** (`cd frontend && npm ci && npm run build`,
so the dashboard ships inside the wheel) → bump `version` in `pyproject.toml` → `uv lock` →
commit/push → `gh release create vX.Y.Z`. Two gotchas: a published version's PyPI
description is **immutable** (fixing the README requires a version bump), and README images
must use absolute `raw.githubusercontent.com` URLs to render on PyPI.
