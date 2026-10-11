"""Helpers for opt-in media received from chat platforms."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from chimera.api.attachments import MAX_BYTES, transcribe
from chimera.governance.ledger_tool import fence
from chimera.governance.sanitize import sanitize_untrusted

MEDIA_DISABLED_REPLY = "Voice and image messages are not enabled for this bot."
#: For media the bot accepts but would not read. Each failure used to answer with
#: MEDIA_DISABLED_REPLY, which told a person whose bot HAS media on that it was off (plan M6).
MEDIA_TOO_LARGE_REPLY = (
    "That file is larger than the 20 MB this bot accepts, so it was not read. "
    "Send a smaller one, or a link to it."
)
MEDIA_FAILED_REPLY = (
    "That voice note or image could not be downloaded, so it was not read. Try sending it again."
)


class MediaTooLarge(ValueError):
    """An inbound file over :data:`MAX_BYTES`, stopped before or during the download."""


def read_bounded(client: Any, url: str, *, headers: dict[str, str] | None = None) -> bytes:
    """Download ``url`` through ``client`` (httpx), stopping as soon as it passes :data:`MAX_BYTES`.

    Telegram and WhatsApp read the whole body first and measured it afterwards, so a file of any
    size was held in memory before it could be refused (plan M6). A declared length over the limit
    is refused before the first byte; an undeclared or understated one at the first chunk past it.
    """
    with client.stream("GET", url, headers=headers) as response:
        response.raise_for_status()
        declared = str(response.headers.get("content-length") or "")
        if declared.isdigit() and int(declared) > MAX_BYTES:
            raise MediaTooLarge(f"declared {declared} bytes")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > MAX_BYTES:
                raise MediaTooLarge(f"passed {MAX_BYTES} bytes")
            chunks.append(chunk)
    return b"".join(chunks)


def refusal_reply(exc: BaseException) -> str:
    """What a chat is told when its media was not read."""
    return MEDIA_TOO_LARGE_REPLY if isinstance(exc, MediaTooLarge) else MEDIA_FAILED_REPLY


def store_image(data: bytes, name: str) -> Path:
    """Store a bounded image in a temporary file for the provider's existing vision path."""
    if len(data) > MAX_BYTES:
        raise MediaTooLarge("inbound image exceeds the 20 MB limit")
    suffix = Path(name).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        suffix = ".png"
    with tempfile.NamedTemporaryFile(prefix="chimera-inbound-", suffix=suffix, delete=False) as handle:
        handle.write(data)
        return Path(handle.name)


def transcribe_audio(data: bytes, name: str) -> str:
    """Transcribe via the existing configured local/hosted tool and fence its untrusted result."""
    if len(data) > MAX_BYTES:
        raise MediaTooLarge("inbound audio exceeds the 20 MB limit")
    suffix = Path(name).suffix.lower()
    if suffix not in {".wav", ".webm", ".ogg", ".mp3", ".m4a", ".flac"}:
        suffix = ".ogg"
    with tempfile.NamedTemporaryFile(prefix="chimera-inbound-", suffix=suffix, delete=False) as handle:
        handle.write(data)
        path = Path(handle.name)
    try:
        text = transcribe(path).strip()
        if text.startswith("error:"):
            raise RuntimeError(text)
        return fence(sanitize_untrusted(text))
    finally:
        path.unlink(missing_ok=True)
