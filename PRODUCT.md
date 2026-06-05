# agent-panorama — What It Does Today

`agent-panorama` answers one question for people who run LLM agents: **"what are my
agents actually doing — in language a human can read?"** It takes raw agent traces and
turns them into outcome-level reports and a live dashboard, with zero infrastructure.

It works in two modes that share the same engine.

## Mode 1 — Trace exports → readable report

One command turns Langfuse or LangSmith JSON exports into a report a non-engineer can read:

```bash
agent-panorama generate --input traces/*.json --output ./report
```

- **Inputs:** a file, a glob, a directory, or any mix (repeat `--input`) of Langfuse
  trace exports or LangSmith run trees. All real-world export shapes are handled —
  single trace, trace + sibling observations, lists, `{"data": [...]}` API pages,
  double-JSON-encoded payloads.
- **Outputs:** Markdown, self-contained HTML, and/or JSON (`--format md|html|json|both`).
- **Filters:** `--session`, `--since`, `--until` to scope what goes in the report.
- **Detail dial:** `--detail minimal|standard|richer` controls narrative depth per step.

## Mode 2 — Live dashboard (no Langfuse, no LangSmith, no tracing infra)

Add one line to any LangChain / LangGraph app and watch a fleet dashboard update live:

```python
from agent_panorama.live import PanoramaCallbackHandler

agent.invoke(inputs, config={"callbacks": [PanoramaCallbackHandler()]})
```

```bash
pip install 'agent-panorama[live]'
agent-panorama serve --open        # dashboard at http://localhost:8321
```

- Completed runs appear in the dashboard within ~3 seconds.
- The instrumented app needs only the **base install** — the handler ships runs over
  stdlib HTTP and never crashes your agent (delivery failures warn once, then stay quiet).
- The server is in-memory and local: no Docker, no database, no signup, no API keys.
- Idempotent on `run_id`; optional `--max-runs` trimming.

## What the analysis layer derives (both modes)

This is more than format conversion — every run is enriched with signals that are not
in the raw trace:

| Signal | What it tells you |
| --- | --- |
| **Outcome** | success / failure / escalated, per run |
| **Retries & fallbacks** | tools that failed then recovered, fallback paths taken |
| **Anomalies** | excessive retries, high latency, tool-call volume, errors — threshold-based, human-readable notes |
| **Plain-language ask & result** | the first human message and final AI answer, unwrapped from nested LangGraph JSON |
| **Decision log** | cross-run feed of notable tool decisions with summarized arguments |
| **Per-agent rollups** | success / escalation / failure / retry rates, token and cost totals per agent |
| **Fleet feed** | one newest-first card per run: agent, action, outcome, tokens, cost, anomalies |
| **Cost estimation** (opt-in) | USD per run from a `model_prices` table in YAML config; tokens stay the default metric |
| **LLM phrasing** (opt-in) | `--summarize` rewrites step results via a cheap model (e.g. Gemini Flash Lite) for the cleanest narrative |

Everything except `--summarize` is deterministic — no LLM calls, no data leaves your machine.

## The dashboard

A React fleet view (bundled into the wheel, served at `/`):

- Live feed of agent activity with outcome badges and anomaly flags
- Per-agent rollup cards (success rate, escalations, tokens, cost)
- Decision log across the fleet
- Works against the live server, a generated `report.json`, or bundled demo data

## Who it's for

1. **Teams already on Langfuse / LangSmith** whose managers, PMs, or clients can't read
   span trees — agent-panorama is the translation layer to a stakeholder-ready report.
2. **Teams with zero observability** running LangChain/LangGraph agents — one line of
   code and a `pip install` gets them a live fleet dashboard with no infra to stand up.

## Install

```bash
pip install agent-panorama          # reports + callback handler (click, jinja2, pyyaml)
pip install 'agent-panorama[live]'  # + the live dashboard server (fastapi, uvicorn)
```

## What it deliberately does not do (yet)

- Pull traces directly from the Langfuse/LangSmith APIs (you export, it reads files)
- Persist live runs across server restarts (in-memory store)
- Semantic root-cause analysis ("*why* did run #14 fail") — outcomes and anomalies are
  rule-based, not LLM-judged

---

> **One line in your agent. A panorama of your fleet.**
