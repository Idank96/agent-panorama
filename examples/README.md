# Examples

Live-mode demos, organized by complexity. Each posts synthetic runs to a
running dashboard — start it first, then run any demo:

```bash
agent-panorama serve --open          # terminal 1
python examples/<tier>/<demo>.py     # terminal 2
```

## `one_step/` — one turn, one trace

| Demo | Shape |
|---|---|
| `single_tool_call.py` | One request → one tool call → one answer |
| `single_message_chat.py` | A chat with one message (carries a session, so later turns would update the same card) |
| `langchain_agent.py` | The real thing: a LangChain agent + `PanoramaCallbackHandler` answering one question with one tool (needs `langchain` + a provider key) |

## `two_step/` — two of something

| Demo | Shape |
|---|---|
| `two_message_chat.py` | Two messages in the same chat → ONE card that updates ("Interactions: 2") |
| `two_tool_trace.py` | One agent run executing two tools (≈ two LangGraph nodes) → one trace, one card, two steps |

## `multi_step/` — conversations, pipelines, agent hierarchies

| Demo | Shape |
|---|---|
| `study_tutor_session.py` | A 4-turn RAG tutoring session (one student, one card): cited retrievals, a fallback chain, a recursion-limit failure, a no-tool follow-up |
| `factory_fleet.py` | Orchestrator → sub-agent → tools: routing LLM, long-polling scheduler tool (slow-run anomaly), composite health check, human-approval escalation |
| `candidate_pipeline.py` | A scheduled review pipeline: big analyzer LLM calls, an escalation ladder (reminder → human handoff), retries, and a hard failure |

## Top level

- `live_demo.py` — the quickstart smoke: three unrelated one-shot runs (success / success / failure).
- `langfuse_traces.json` — sample Langfuse export used by `generate` and the test suite.

All data is synthetic and deliberately generic.
