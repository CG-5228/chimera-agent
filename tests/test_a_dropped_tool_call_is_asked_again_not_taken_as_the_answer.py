"""A step whose only tool call was dropped is not the turn's answer: the model is asked again (M19).

Observed 2026-10-09/10 through the desktop bridge. Two research turns ended early, one after five
steps and one search, one after its first search; both receipts said `dropped_tool_calls: 1`. The
provider layer drops a call whose arguments do not parse, usually one cut at the output limit, and
that is right. But the step then had no tool calls, so the loop took what was left, the text written
before the call ("I will now write the report"), as the final answer. The agent said it would
continue and did not, and the model never learned its call had not run.
"""

from __future__ import annotations

from typing import Any

from chimera.core import Agent, AgentConfig
from chimera.providers import CompletionResult, ToolCall
from chimera.tools import ToolRegistry
from chimera.tools.builtin import EchoTool


class _Script:
    """Answers from a list of results, keeping every prompt it was sent."""

    def __init__(self, results: list[CompletionResult]) -> None:
        self._results = list(results)
        self.prompts: list[list[Any]] = []

    def complete(self, messages: list[Any], *, tools: Any = None, **kwargs: Any) -> CompletionResult:
        self.prompts.append([dict(m) if isinstance(m, dict) else m for m in messages])
        return self._results.pop(0)


def _dropped(text: str = "I will now write the report.", *, cut: bool = True) -> CompletionResult:
    return CompletionResult(
        content=text, model="fake", dropped_tool_calls=1, truncated=cut,
        finish_reason="length" if cut else "tool_calls",
    )


def _call(n: int) -> CompletionResult:
    return CompletionResult(
        content="", model="fake",
        tool_calls=[ToolCall(id=f"c{n}", name="echo", arguments={"text": f"part {n}"})],
    )


def _agent(backend: _Script) -> Agent:
    registry = ToolRegistry()
    registry.register(EchoTool())
    return Agent(backend, registry, AgentConfig(max_steps=8))


def test_the_turn_goes_on_and_the_retried_call_runs() -> None:
    backend = _Script([_dropped(), _call(1), CompletionResult(content="done", model="fake")])
    notices: list[tuple[str, dict[str, Any]]] = []
    result = _agent(backend).run(
        "write the report", on_notice=lambda code, _text, data: notices.append((code, data))
    )

    assert result.answer == "done"
    assert result.tool_names == ["echo"]
    # What the model was told: nothing ran, why, and how to make the call fit.
    told = str(backend.prompts[1][-1]["content"])
    assert "could not be read because the reply hit its length limit, so nothing ran" in told
    assert "split it into smaller calls" in told
    assert notices and notices[0][0] == "dropped_tool_call"


def test_a_drop_without_a_cut_does_not_blame_the_length_limit() -> None:
    backend = _Script([_dropped(cut=False), CompletionResult(content="done", model="fake")])
    _agent(backend).run("task")
    told = str(backend.prompts[1][-1]["content"])
    assert "could not be read, so nothing ran" in told
    assert "length limit" not in told


def test_it_asks_at_most_twice_per_run() -> None:
    # A model that keeps producing calls that cannot be read is not helped by a third ask; the
    # third drop ends the turn as before, with the text it has.
    backend = _Script([_dropped("one"), _dropped("two"), _dropped("three")])
    result = _agent(backend).run("task")
    assert result.answer == "three"
    assert len(backend.prompts) == 3
    assert result.steplog.dropped_tool_calls == 3


def test_a_step_that_kept_a_call_is_unchanged() -> None:
    # Some calls dropped and one kept: the kept call runs as it always did, and nothing is nudged.
    partial = CompletionResult(
        content="", model="fake", dropped_tool_calls=1,
        tool_calls=[ToolCall(id="k", name="echo", arguments={"text": "kept"})],
    )
    backend = _Script([partial, CompletionResult(content="done", model="fake")])
    result = _agent(backend).run("task")
    assert result.answer == "done"
    assert all("could not be read" not in str(m.get("content")) for m in backend.prompts[1])
