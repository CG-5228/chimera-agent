"""After compaction the model is told how many tool calls it made, counted by the loop (plan M2).

Observed 2026-10-09/10 while running a research task through the desktop bridge: a run compacted
twice said it had made 17 searches and its receipt held 34; another said 6 and held 38. Compaction
had removed the calls, and the structural note left behind names the tools in the dropped span but
not how many times each ran, so nothing in front of the model could correct its estimate. The
receipt was right; the answer the person read was not.
"""

from __future__ import annotations

from typing import Any

from chimera.core import Agent, AgentConfig
from chimera.core.context_budget import RunState, compact
from chimera.providers import CompletionResult, ToolCall
from chimera.tools import ToolRegistry
from chimera.tools.builtin import EchoTool

#: 128k fallback window x 0.6 budget x 0.8 trigger = 61,440 tokens: above it, the loop compacts.
_OVER = 70_000
_UNDER = 1_000


class _Recording:
    """Calls ``echo`` once per scripted size, then answers; keeps every prompt it was sent."""

    def __init__(self, sizes: list[int]) -> None:
        self._sizes = list(sizes)
        self.prompts: list[list[Any]] = []

    def complete(self, messages: list[Any], *, tools: Any = None, **kwargs: Any) -> CompletionResult:
        self.prompts.append([dict(m) if isinstance(m, dict) else m for m in messages])
        size = self._sizes.pop(0) if self._sizes else _UNDER
        if self._sizes:
            # A different argument each time: identical repeated calls trip the loop detector.
            n = len(self.prompts)
            call = ToolCall(id=f"c{n}", name="echo", arguments={"text": f"x{n}"})
            return CompletionResult(content="", model="fake", prompt_tokens=size, tool_calls=[call])
        return CompletionResult(content="done", model="fake", prompt_tokens=size)


def _agent(backend: _Recording) -> Agent:
    registry = ToolRegistry()
    registry.register(EchoTool())
    return Agent(backend, registry, AgentConfig(max_steps=12, context_budget=0.6, keep_recent=2))


def _restored(prompt: list[Any]) -> str:
    return "\n".join(
        str(m.get("content", ""))
        for m in prompt
        if isinstance(m, dict) and str(m.get("content", "")).startswith("[context restored")
    )


def test_the_prompt_after_compaction_carries_the_real_count() -> None:
    # Five small steps, each one echo call, then a step whose prompt crosses the trigger.
    backend = _Recording([_UNDER] * 5 + [_OVER, _UNDER, _UNDER])
    result = _agent(backend).run("search the literature")

    assert result.steplog.compactions == 1
    # The call that crossed the trigger is the 6th model call; the loop compacts after it and before
    # running its tool call, so the next prompt is the first one built from the compacted history.
    after = _restored(backend.prompts[6])
    assert "counted by the harness (5 in all" in after
    assert "- echo: 5" in after
    # And the receipt agrees with what the model was told, plus the calls made after it.
    assert result.tool_names.count("echo") == 7


def test_a_second_compaction_restores_the_newer_count_not_the_first() -> None:
    backend = _Recording([_UNDER, _OVER, _UNDER, _UNDER, _OVER, _UNDER])
    result = _agent(backend).run("search the literature")

    assert result.steplog.compactions == 2
    first = _restored(backend.prompts[2])
    second = _restored(backend.prompts[5])
    assert "- echo: 1" in first
    assert "- echo: 4" in second
    assert "- echo: 1\n" not in second + "\n"


def test_no_tool_call_means_no_count_line() -> None:
    # A compaction before any call has nothing to count; an empty "0 in all" block would be noise.
    state = RunState(task="t")
    messages = [{"role": "system", "content": "s"}] + [
        {"role": "user", "content": f"m{i}"} for i in range(8)
    ]
    out, changed = compact(messages, keep_recent=2, state=state)
    assert changed
    assert "counted by the harness" not in _restored(out)


def test_the_count_is_ordered_by_calls_then_name() -> None:
    message = RunState(tool_calls={"read_file": 3, "arxiv_search": 38, "grep": 3}).as_message()
    assert message is not None
    content = str(message["content"])
    assert "(44 in all;" in content
    assert content.index("arxiv_search: 38") < content.index("grep: 3") < content.index("read_file: 3")
