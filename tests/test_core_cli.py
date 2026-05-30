"""End-to-end tests for generate_report and the CLI."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402

import pytest  # noqa: E402
from click.testing import CliRunner  # noqa: E402

from agent_panorama import generate_report  # noqa: E402
from agent_panorama import summarize as summarize_mod  # noqa: E402
from agent_panorama.cli import cli  # noqa: E402

_LANGFUSE = _bootstrap.EXAMPLES / "langfuse_traces.json"
_LANGSMITH = _bootstrap.EXAMPLES / "langsmith_runs.json"


def test_generate_report_writes_files(tmp_path: Path) -> None:
    report = generate_report(_LANGFUSE, output_dir=tmp_path, formats=["md", "html"])
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "report.html").exists()
    assert report.total_runs == 3


def test_generate_report_langsmith(tmp_path: Path) -> None:
    report = generate_report(
        _LANGSMITH, output_dir=tmp_path, formats=["md"], input_type="langsmith"
    )
    assert report.total_runs == 1
    assert "recipe-assistant" in (tmp_path / "report.md").read_text("utf-8")


def test_cli_generate(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "--input",
            str(_LANGFUSE),
            "--output",
            str(tmp_path),
            "--format",
            "both",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Agent Activity Report generated" in result.output
    assert (tmp_path / "report.html").exists()


def test_summarize_writes_llm_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Avoid a real model call: stub the exchange builder.
    def fake_exchange(text: str, model: str):
        return summarize_mod.SummaryExchange(
            model=model,
            system_prompt=summarize_mod._SYSTEM_PROMPT,
            input_text=text[:50],
            output="Did the thing.",
        )

    monkeypatch.setattr(summarize_mod, "build_exchange", fake_exchange)
    generate_report(
        _LANGFUSE, output_dir=tmp_path, formats=["md"], detail="minimal", summarize=True
    )
    log = tmp_path / "llm_calls.log"
    assert log.exists()
    text = log.read_text("utf-8")
    assert "SYSTEM PROMPT" in text
    assert "INPUT SENT" in text
    assert "Did the thing." in text


def test_cli_rejects_missing_input(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["generate", "--input", str(tmp_path / "nope.json"), "--output", str(tmp_path)]
    )
    assert result.exit_code != 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
