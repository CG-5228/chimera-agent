"""A reply over a bot transport arrives whole, or someone is told what did not arrive (plan M5).

Two silent losses, found reading the adapters during the research done inside Chimera Desktop:

- WhatsApp cut every message at 4,096 characters (`text[:_WHATSAPP_LIMIT]`). The rest of a long reply
  was not sent, and nothing said so; the Discord, Telegram and Slack senders already split instead.
- Signal never read the bridge's answer. A send the bridge refused was reported to the agent as
  "sent", and the reply to an inbound message vanished.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from chimera.server import SignalAdapter, WhatsAppSender, WhatsAppWebhook


class _Client:
    """httpx.Client double: records each POST and answers from a script."""

    def __init__(self, answers: list[Any], posts: list[dict[str, Any]]) -> None:
        self._answers = answers
        self._posts = posts

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *_: Any) -> bool:
        return False

    def post(self, url: str, **kwargs: Any) -> Any:
        self._posts.append({"url": url, **kwargs})
        return self._answers.pop(0) if self._answers else _Resp(200, {"messages": [{"id": "w"}]})


class _Resp:
    def __init__(self, status: int, body: dict[str, Any], text: str = "") -> None:
        self.status_code = status
        self._body = body
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._body


def _patch_client(monkeypatch: pytest.MonkeyPatch, answers: list[Any]) -> list[dict[str, Any]]:
    import httpx

    posts: list[dict[str, Any]] = []
    monkeypatch.setattr(httpx, "Client", lambda **_: _Client(answers, posts))
    return posts


# --- WhatsApp -----------------------------------------------------------------------------------


def test_a_long_whatsapp_reply_is_split_and_none_of_it_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posts = _patch_client(monkeypatch, [])
    text = "y" * 4096 * 2 + "tail"  # two full messages and four characters
    out = WhatsAppSender("tok", "123").send("15551234567", text)

    bodies = [p["json"]["text"]["body"] for p in posts]
    assert [len(b) for b in bodies] == [4096, 4096, 4]
    assert "".join(bodies) == text
    assert out == "sent 3 messages to whatsapp 15551234567 (the text was split to fit)"


def test_a_short_whatsapp_reply_is_still_one_message(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = _patch_client(monkeypatch, [])
    assert WhatsAppSender("tok", "123").send("1", "hi") == "sent message to whatsapp 1"
    assert len(posts) == 1


def test_a_whatsapp_failure_mid_reply_says_how_much_arrived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posts = _patch_client(
        monkeypatch,
        [_Resp(200, {"messages": [{"id": "a"}]}), _Resp(400, {"error": {"message": "rate limited"}})],
    )
    out = WhatsAppSender("tok", "123").send("1", "x" * 9000)
    assert out == "error: whatsapp send failed after 1 of 3 parts were sent: rate limited"
    assert len(posts) == 2  # it stopped at the failure rather than sending around a gap


def test_an_undelivered_webhook_reply_is_logged_not_dropped_silently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _Failing:
        platform = "whatsapp"
        access_token = "t"
        api_version = "v20.0"

        def send(self, chat_id: str, text: str) -> str:
            return "error: whatsapp send failed: recipient not in allowed list"

    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "15551234567", "type": "text", "text": {"body": "hi"}}
    ]}}]}]}
    hook = WhatsAppWebhook(_Failing(), "T", lambda _m: "reply")  # type: ignore[arg-type]
    with caplog.at_level(logging.WARNING, logger="chimera.server.whatsapp"):
        # Handled, not raised: raising makes Meta redeliver and the agent answer (and spend) twice.
        assert hook.on_message(payload) == 1
    assert "was not delivered" in caplog.text
    assert "recipient not in allowed list" in caplog.text


# --- Signal -------------------------------------------------------------------------------------


def test_a_signal_send_the_bridge_refused_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, [_Resp(400, {}, text='{"error":"Invalid recipient"}')])
    out = SignalAdapter("http://localhost:8080", "+15550000000").send("+1555", "hello")
    assert out.startswith("error: signal send failed: the signal bridge answered HTTP 400")
    assert "Invalid recipient" in out


def test_a_signal_send_the_bridge_accepted_is_still_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, [_Resp(201, {})])
    out = SignalAdapter("http://localhost:8080", "+15550000000").send("+1555", "hello")
    assert out == "sent message to signal +1555"


def test_one_undelivered_signal_reply_does_not_end_the_listener(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import httpx

    adapter = SignalAdapter("http://localhost:8080", "+15550000000", poll_interval=0)
    envelope = {"envelope": {"source": "+15551234567", "dataMessage": {"message": "hi"}}}
    polls: list[int] = []

    class _Listener(_Client):
        def get(self, url: str, **_: Any) -> Any:
            polls.append(1)
            if len(polls) >= 2:
                adapter.stop()  # the second poll ends the run: the loop survived the first reply
            return _Resp(200, [envelope] if len(polls) == 1 else [])  # type: ignore[arg-type]

        def request(self, *_: Any, **__: Any) -> None:
            return None

    posts: list[dict[str, Any]] = []
    monkeypatch.setattr(httpx, "Client", lambda **_: _Listener([_Resp(500, {}, "down")], posts))
    with caplog.at_level(logging.WARNING, logger="chimera.server.signal"):
        adapter.start(lambda _m: "reply")
    assert len(polls) == 2
    assert "was not delivered" in caplog.text
