<p align="center">
  <img src="https://raw.githubusercontent.com/Idank96/agent-panorama/main/assets/logo.png" alt="agent-panorama" width="320">
</p>

<h1 align="center">agent-panorama</h1>

<p align="center">
  <a href="https://github.com/Idank96/agent-panorama/actions/workflows/ci.yml"><img src="https://github.com/Idank96/agent-panorama/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

Turn raw LLM agent traces into a **human-readable Agent Activity Report** that a
non-engineer can actually read. Point it at a Langfuse (or LangSmith) trace
export and get clean Markdown + a self-contained HTML report that explains, in
business language, what your agents did, what they decided, and anything that
looks off.

## Why

Traces are great for engineers and terrible for everyone else. `agent-panorama`
translates tool calls, retries, token usage, and errors into plain English. It
also pulls the real user request and final answer out of LangGraph/LangChain
`messages` payloads, so the report reads like a story, not a JSON dump:

- `get_weather({"city": "Paris"})` → **"Looked up the weather"**
- 3 failed model calls → **"High retry count: 3 failed attempts before completing."**
- `human_handoff(...)` → run outcome **human-escalated**

> Cost/USD estimation is intentionally out of scope for now — the report reports
> token usage, not dollars.

## Install

```bash
pip install agent-panorama
# or, for local development:
uv pip install -e ".[dev]"
```

Requires Python 3.10+. Dependencies are intentionally minimal: `click`,
`jinja2`, `pyyaml`.

## CLI usage

```bash
agent-panorama generate --input traces.json --output ./report --format html
```

Options:

| Option | Description |
| --- | --- |
| `--input` | Path to the Langfuse/LangSmith JSON export (required). |
| `--output` | Output directory (default `./report`). |
| `--format` | `md`, `html`, or `both` (default `both`). |
| `--input-type` | `langfuse` or `langsmith` (default `langfuse`). |
| `--config` | Optional YAML config (tool naming, thresholds). |
| `--detail` | Step narrative detail: `minimal`, `standard` (default), or `richer`. |
| `--summarize` | Phrase each `minimal` result via a cheap LLM (opt-in, off by default). See below. |
| `--summarize-model` | LLM id for `--summarize` (default `google_genai:gemini-2.5-flash-lite`). |

Try it on the bundled example:

```bash
agent-panorama generate --input examples/langfuse_traces.json --output ./report
```

## Library usage

```python
from agent_panorama import generate_report

report = generate_report(
    "traces.json",
    output_dir="./report",
    formats=["md", "html"],
    input_type="langfuse",
    config="config.yaml",  # optional
)

print(report.total_runs, report.total_tokens)
```

`generate_report` returns the in-memory `Report`, so you can also inspect runs,
the decision log, and anomalies programmatically without touching disk (use
`build_report_from_file` if you want the report without writing files).

## What's in a report

- **Summary** — time range, total runs, total steps, total tokens.
- **Per-agent section** — what it was asked to do, what it did step by step (graph
  nodes / tool calls in plain English, at the chosen `--detail` level), final
  outcome, and a confidence signal (retries / fallback).
- **Decision log** — a sortable table of every consequential action: timestamp,
  agent, action, parameters summarized in plain English, outcome.
- **Anomalies** — high retry counts, slow runs, high activity, errors, fallbacks.

## Configuration

All configuration is optional. See [`config.example.yaml`](config.example.yaml)
for the full set. Highlights:

```yaml
tool_descriptions:
  get_weather: "Looked up the weather"

consequential_tools: [send_email, human_handoff]
escalation_tools: [human_handoff, handoff_to_agent]

anomaly_thresholds:
  max_retries: 2
  max_latency_seconds: 30
  max_tool_calls: 15
```

## Plain-language result summaries (optional LLM)

By default the report uses **no LLM** — it just reformats trace data. But in
`--detail minimal`, a long final answer (e.g. a big Markdown table) is condensed
with a simple heuristic, which keeps the agent's own wording ("Here are all the
cutting stations in the plant"). If you'd rather get a crisp past-tense action
line ("**Showed** all the cutting stations in the plant."), enable the opt-in
`--summarize` flag, which rewrites just the result via a cheap model.

It is intentionally tiny: a ~40-token fixed system prompt, **at most ~250 input
tokens** (the result is hard-capped at 1,000 characters), and a ~25-token reply
— roughly **300 tokens total per run**. On a free-tier model this costs nothing;
on the cheapest paid model it's a fraction of a cent.

### Setup

1. Install a provider extra (pick the one matching your model):

   ```bash
   pip install "agent-panorama[gemini]"     # Google Gemini (recommended, free tier)
   pip install "agent-panorama[openai]"     # OpenAI
   pip install "agent-panorama[anthropic]"  # Anthropic
   ```

2. Get your own API key from the provider and either `export` it or put it in a
   `.env` file in the working directory (auto-loaded; real env vars win):

   ```bash
   export GOOGLE_API_KEY=...      # Gemini
   # or OPENAI_API_KEY / ANTHROPIC_API_KEY
   # …or a .env file:  GOOGLE_API_KEY=...
   ```

3. Run with `--summarize`:

   ```bash
   agent-panorama generate --input traces.json --output ./report \
     --detail minimal --summarize
   # pick a different model:
   agent-panorama generate --input traces.json --output ./report \
     --detail minimal --summarize --summarize-model openai:gpt-5-nano
   ```

If the provider package or key is missing, summarization is skipped gracefully
(you just get the heuristic line) — it never breaks report generation.

Every call is logged to **`<output>/llm_calls.log`** — the exact system prompt,
the input sent (with its character count), and the output (or error) for each
run — so you can audit precisely what went to the model.

### Recommended models (cheapest first)

For this tiny one-shot call any of these is more than capable, so free-tier
access and price dominate. **Only Gemini Flash / Flash-Lite have a genuine
no-credit-card free tier**; OpenAI/Anthropic require a positive balance.

| Model (`--summarize-model`) | Price /1M (in → out) | Free tier | Provider extra | API key env var |
| --- | --- | --- | --- | --- |
| `google_genai:gemini-2.5-flash-lite` *(default)* | $0.10 → $0.40 | ✅ free, no card (~1,500 req/day) | `gemini` | `GOOGLE_API_KEY` |
| `google_genai:gemini-2.5-flash` | $0.30 → $2.50 | ✅ free tier (lower quota) | `gemini` | `GOOGLE_API_KEY` |
| `openai:gpt-5-nano` | $0.05 → $0.40 | ⚠️ no free tier (prepaid) | `openai` | `OPENAI_API_KEY` |
| `openai:gpt-4.1-nano` | $0.10 → $0.40 | ⚠️ no free tier | `openai` | `OPENAI_API_KEY` |
| `openai:gpt-4o-mini` | $0.15 → $0.60 | ⚠️ no free tier | `openai` | `OPENAI_API_KEY` |
| `anthropic:claude-haiku-4-5` | $1.00 → $5.00 | ⚠️ trial credits only | `anthropic` | `ANTHROPIC_API_KEY` |

**Pick `google_genai:gemini-2.5-flash-lite`** (the default) to run this for free.
`gpt-5-nano` has the lowest paid input price if you already use OpenAI.
_Prices verified May 2026 against providers' official pricing pages; check them for current rates._

## Supported inputs

- **Langfuse** trace exports — a single trace dict, the single-trace
  `{"trace": {...}, "observations": [...]}` shape, a list of traces, or the
  `{"data": [...]}` list-API shape. Tool calls are read from `TOOL`
  observations (falling back to tool spans), and from `toolCalls` / OpenAI-style
  `tool_calls` declared on generations.
- **LangSmith** run exports — a flat list (or `{"runs": [...]}`) of run nodes;
  each root run is flattened into one agent run.

Token usage is read from the trace (`inputUsage`/`outputUsage` or
`usage`/`usage_metadata`). Dollar-cost estimation is intentionally out of scope.

## Roadmap

`agent-panorama` starts as a report generator and is growing into an **oversight
layer for fleets of agents** — a single pane of glass for everything your agents
did, decided, and got wrong. More than logs, across more than one agent.

**✅ v0.1 — Read one run clearly _(today)_**
- Langfuse + LangSmith trace ingestion
- Plain-language per-agent summaries, decision log, anomalies
- Markdown + self-contained HTML output; CLI and library API

**🔜 v0.2 — See the whole fleet (the panorama view)**
- A unified **cross-agent activity feed** — one scannable timeline of what every
  agent did, in plain English:

  ```text
  Agent Activity — May 28, 14:30–15:00

  research-assistant    → searched the web, summarized 3 papers            ✓ success
  scheduling-assistant  → checked the calendar, handed the task to a human ⤴ escalated
  weather-assistant     → looked up the weather (retried once), emailed it ✓ success
  billing-agent         → issued 2 refunds, flagged 1 for review           ⚠ anomaly
  ```
- Aggregate many traces into one report (by session, time window, or file glob)
- Per-agent rollups: runs, actions, success / escalation / retry rates
- Cross-agent decision log spanning every agent in the window

**📈 v0.3 — Trends & regressions**
- Track rates over time, not just a point-in-time snapshot
- Flag regressions (escalations or retries spiking vs. a baseline)
- Period-over-period comparison ("this week vs. last")

**🔌 v0.4 — More sources & deeper detail**
- OpenTelemetry / OpenInference and raw OpenAI-style logs
- Optionally fetch full input/output from the Langfuse API to enrich
  decision-log parameters
- Pluggable parser interface for custom trace formats

**🎯 The vision — Continuous oversight**
- A live dashboard: the activity feed above, always-on, filterable by agent /
  outcome / time
- Scheduled/continuous reports instead of one-off runs
- Accountability views a non-engineer can sign off on (what happened, what needs
  a human)
- Alerting on anomalies across the fleet

> Have a use case or a trace format you want supported? Open an issue.

## Development

```bash
uv pip install -e ".[dev]"
python tests/run_all_tests.py     # run the full suite
ruff check . && ruff format --check .
```

## License

MIT — see [LICENSE](LICENSE).
