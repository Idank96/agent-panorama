"""Minimal LangChain agent instrumented with the live dashboard.

The whole integration is one line: add ``PanoramaCallbackHandler()`` to the
callbacks of any LangChain/LangGraph invocation.

Requirements (the instrumented app only needs base agent-panorama; the model
provider is for this demo's agent itself):

    pip install agent-panorama langchain langchain-openai
    export OPENAI_API_KEY=...

Usage (two terminals):

    # terminal 1 — the dashboard (needs the 'live' extra)
    agent-panorama serve --open

    # terminal 2
    python examples/live_langchain_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_panorama.live import PanoramaCallbackHandler

try:
    from langchain.agents import create_agent
    from langchain.chat_models import init_chat_model
    from langchain_core.tools import tool
except ImportError:
    raise SystemExit("This demo needs LangChain: pip install langchain langchain-openai") from None


@tool
def get_weather(city: str) -> str:
    """Return the (pretend) current weather for a city."""
    return f"Sunny and 24°C in {city}."


def main() -> None:
    """Run a tiny tool-using agent with the live dashboard attached."""
    model = init_chat_model("gpt-4o-mini", model_provider="openai")
    agent = create_agent(model, tools=[get_weather])
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "What's the weather in Paris?"}]},
        config={"callbacks": [PanoramaCallbackHandler()]},
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
