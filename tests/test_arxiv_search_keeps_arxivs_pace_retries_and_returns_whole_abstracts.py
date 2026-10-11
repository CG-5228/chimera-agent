"""`arxiv_search` keeps arXiv's pace, retries a rate limit, and returns whole abstracts (plan M16).

Observed 2026-10-09 while running a research task inside Chimera Desktop:

- five conversations searched at once, five requests left at once, and every one came back HTTP 429:
  13 research areas, zero papers. The tool made one HTTP call with no wait, no retry and no pace
  shared between conversations, and arXiv asks for one request every three seconds;
- abstracts were cut at 300 characters, before most of them state a result, and several reports
  written from them said "no number in the abstract" about numbers that were there.
"""

from __future__ import annotations

from typing import Any

import pytest

import chimera.tools.research as research
from chimera.tools.research import ArxivSearchTool

_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2609.00001v1</id>
    <published>2026-09-01T00:00:00Z</published>
    <title>A paper</title>
    <summary>{summary}</summary>
    <author><name>A. Author</name></author>
  </entry>
</feed>"""


class _Resp:
    def __init__(self, status: int, text: str = "", retry_after: str = "") -> None:
        self.status_code = status
        self.text = text
        self.headers = {"retry-after": retry_after} if retry_after else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("bad", request=None, response=None)  # type: ignore[arg-type]


class _Clock:
    """Stands in for `time` in the module: sleeping advances the clock, nothing really waits."""

    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(round(seconds, 2))
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(research, "time", fake)
    monkeypatch.setattr(research, "_arxiv_last", 0.0)
    return fake


def _serve(monkeypatch: pytest.MonkeyPatch, answers: list[_Resp], clock: _Clock) -> list[float]:
    import httpx

    sent_at: list[float] = []

    def get(*_a: Any, **_k: Any) -> _Resp:
        sent_at.append(clock.now)
        return answers.pop(0)

    monkeypatch.setattr(httpx, "get", get)
    return sent_at


def test_requests_are_spaced_three_seconds_apart_across_calls(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    ok = _FEED.format(summary="x")
    sent_at = _serve(monkeypatch, [_Resp(200, ok), _Resp(200, ok), _Resp(200, ok)], clock)
    tool = ArxivSearchTool()
    for query in ("a", "b", "c"):
        tool.run(query=query)
    gaps = [later - earlier for earlier, later in zip(sent_at, sent_at[1:], strict=False)]
    assert gaps == [3.0, 3.0]


def test_a_rate_limit_is_retried_and_the_answer_arrives(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    _serve(monkeypatch, [_Resp(429), _Resp(200, _FEED.format(summary="found it"))], clock)
    out = ArxivSearchTool().run(query="q")
    assert "found it" in out
    assert not out.startswith("error:")


def test_retry_after_is_honoured_up_to_a_ceiling(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    _serve(
        monkeypatch,
        [_Resp(429, retry_after="7"), _Resp(503, retry_after="600"), _Resp(200, _FEED.format(summary="ok"))],
        clock,
    )
    ArxivSearchTool().run(query="q")
    assert 7.0 in clock.slept
    assert 30.0 in clock.slept  # 600 s asked, 30 s waited: past that the search fails instead


def test_a_rate_limit_that_lasts_says_so_and_what_to_do(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    _serve(monkeypatch, [_Resp(429), _Resp(429), _Resp(429)], clock)
    out = ArxivSearchTool().run(query="q")
    assert out.startswith("error: arxiv search failed: HTTP 429 after 3 tries")
    assert "one request every 3 seconds" in out


def test_the_abstract_comes_back_whole(monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> None:
    abstract = "We measure a thing. " * 40 + "It improves accuracy by 12.5 points."
    _serve(monkeypatch, [_Resp(200, _FEED.format(summary=abstract))], clock)
    out = ArxivSearchTool().run(query="q")
    assert "12.5 points" in out
    assert "A paper (2026)" in out


def test_a_very_long_abstract_is_cut_and_says_so(
    monkeypatch: pytest.MonkeyPatch, clock: _Clock
) -> None:
    _serve(monkeypatch, [_Resp(200, _FEED.format(summary="y" * 5000))], clock)
    out = ArxivSearchTool().run(query="q")
    assert "[abstract cut at 2000 of 5000 chars]" in out
