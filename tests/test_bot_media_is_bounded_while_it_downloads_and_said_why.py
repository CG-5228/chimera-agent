"""Inbound bot media is bounded while it downloads, and a chat is told why it was not read (plan M6).

Found reading the adapters during the research done inside Chimera Desktop on 2026-10-09/10:

- Telegram and WhatsApp read the whole file into memory and measured it afterwards, so a file of any
  size was held before it could be refused. Discord already checked the size it reports first.
- Every media that was not read — too large, or a download that failed — was answered with "Voice
  and image messages are not enabled for this bot", which is false for a bot that has media on.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from chimera.api.attachments import MAX_BYTES
from chimera.server.gateway import InboundMessage, MessageGateway
from chimera.server.inbound_media import (
    MEDIA_DISABLED_REPLY,
    MEDIA_FAILED_REPLY,
    MEDIA_TOO_LARGE_REPLY,
    MediaTooLarge,
    read_bounded,
    refusal_reply,
)
from chimera.server.telegram_adapter import TelegramAdapter

_CHUNK = 1024 * 1024


class _Stream:
    def __init__(self, chunks: int, declared: int | None, read: list[int]) -> None:
        self._chunks = chunks
        self.headers = {} if declared is None else {"content-length": str(declared)}
        self._read = read

    def __enter__(self) -> _Stream:
        return self

    def __exit__(self, *_: Any) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self) -> Iterator[bytes]:
        for _ in range(self._chunks):
            self._read.append(_CHUNK)
            yield b"x" * _CHUNK


class _Client:
    """httpx.Client double: `stream` serves ``chunks`` megabytes; `get` answers getFile."""

    def __init__(self, chunks: int, declared: int | None = None, file_size: int | None = None) -> None:
        self.read: list[int] = []
        self._chunks = chunks
        self._declared = declared
        self._file_size = file_size
        self.streamed: list[str] = []

    def stream(self, method: str, url: str, **_: Any) -> _Stream:
        self.streamed.append(url)
        return _Stream(self._chunks, self._declared, self.read)

    def get(self, url: str, **_: Any) -> Any:
        info: dict[str, Any] = {"file_path": "voice/file.ogg"}
        if self._file_size is not None:
            info["file_size"] = self._file_size
        return type("R", (), {"json": lambda _self: {"result": info}})()


def test_a_small_file_comes_back_whole() -> None:
    client = _Client(chunks=3)
    assert read_bounded(client, "https://cdn/x") == b"x" * (3 * _CHUNK)


def test_an_undeclared_large_file_stops_at_the_limit_not_at_its_end() -> None:
    client = _Client(chunks=200)  # 200 MB, size not declared
    with pytest.raises(MediaTooLarge):
        read_bounded(client, "https://cdn/x")
    assert sum(client.read) <= MAX_BYTES + _CHUNK  # stopped one chunk past the limit


def test_a_declared_large_file_is_refused_before_a_byte() -> None:
    client = _Client(chunks=200, declared=200 * _CHUNK)
    with pytest.raises(MediaTooLarge):
        read_bounded(client, "https://cdn/x")
    assert client.read == []


def test_telegram_refuses_by_its_declared_size_without_downloading() -> None:
    adapter = TelegramAdapter("123:abc", inbound_media=True)
    client = _Client(chunks=200, file_size=200 * _CHUNK)
    inbound = InboundMessage(
        text="", chat_id="1", platform="telegram", media_kind="audio", media_file_id="f1"
    )
    adapter._attach_media(client, inbound)
    assert client.streamed == []
    assert inbound.media_refusal is True
    assert inbound.media_refusal_reply == MEDIA_TOO_LARGE_REPLY


def test_telegram_bounds_a_file_whose_size_it_did_not_report() -> None:
    adapter = TelegramAdapter("123:abc", inbound_media=True)
    client = _Client(chunks=200)
    inbound = InboundMessage(
        text="", chat_id="1", platform="telegram", media_kind="audio", media_file_id="f1"
    )
    adapter._attach_media(client, inbound)
    assert inbound.media_data is None
    assert sum(client.read) <= MAX_BYTES + _CHUNK
    assert inbound.media_refusal_reply == MEDIA_TOO_LARGE_REPLY


def test_each_refusal_says_its_own_reason() -> None:
    assert refusal_reply(MediaTooLarge("x")) == MEDIA_TOO_LARGE_REPLY
    assert refusal_reply(OSError("reset")) == MEDIA_FAILED_REPLY
    assert "not enabled" not in MEDIA_TOO_LARGE_REPLY + MEDIA_FAILED_REPLY


def test_the_gateway_answers_with_the_reason_and_keeps_the_old_reply_for_media_off() -> None:
    gateway = MessageGateway(lambda: None)  # type: ignore[arg-type, return-value]
    too_big = InboundMessage(
        text="", media_refusal=True, media_refusal_reply=MEDIA_TOO_LARGE_REPLY
    )
    off = InboundMessage(text="", media_refusal=True)
    assert gateway.on_message(too_big) == MEDIA_TOO_LARGE_REPLY
    assert gateway.on_message(off) == MEDIA_DISABLED_REPLY
