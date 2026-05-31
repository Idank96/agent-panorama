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
npm run dev        # Vite dev server (reads public/feed.json)
npm run test       # vitest run (the loadFeed.test.ts suite)
npm run build      # tsc -b && vite build
npm run sync:feed  # cp ../report/report.json public/feed.json (refresh the data it renders)
```

**CI does not cover `frontend/`** — ruff/pytest gate only the Python package, so frontend
type-checks and `npm run test` must be run by hand before touching the dashboard.

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
Release. To cut a release: bump `version` in `pyproject.toml` → `uv lock` → commit/push →
`gh release create vX.Y.Z`. Two gotchas: a published version's PyPI description is
**immutable** (fixing the README requires a version bump), and README images must use
absolute `raw.githubusercontent.com` URLs to render on PyPI.
