"""The file viewer can show a long file whole when the person asks (2026-10-10).

It showed the first 20,000 characters of any file with a "truncated" badge and nothing else: no
offset, no paging, no way to read the rest from the app. The read still stops at the agent's own cap
by default; it now says how long the text is, and the route serves more on request, up to a ceiling
that keeps a huge log from freezing the screen.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from chimera.api.fs_api import MAX_VIEW_CHARS, read_file
from chimera.config import Settings, get_settings
from chimera.interface import ChatSession
from chimera.interface.session import SupportsRun


def test_the_default_read_keeps_the_agents_cap_and_says_the_length(tmp_path: Path) -> None:
    (tmp_path / "big.md").write_text("a" * 54_321, encoding="utf-8")
    out = read_file(tmp_path, "big.md")
    assert len(out["content"]) == 20_000
    assert out["truncated"] is True
    assert out["total_chars"] == 54_321


def test_asked_for_more_it_returns_the_whole_text(tmp_path: Path) -> None:
    (tmp_path / "big.md").write_text("a" * 54_321, encoding="utf-8")
    out = read_file(tmp_path, "big.md", 100_000)
    assert len(out["content"]) == 54_321
    assert out["truncated"] is False


def test_the_route_serves_more_on_request_and_never_past_the_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from chimera.api import build_api_app

    monkeypatch.setenv("CHIMERA_HOME", str(tmp_path / "home"))
    get_settings.cache_clear()
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "log.txt").write_text("b" * (MAX_VIEW_CHARS + 10), encoding="utf-8")
    app = build_api_app(
        lambda: ChatSession(cast(SupportsRun, None)),
        workspace=ws,
        settings=Settings(CHIMERA_HOME=str(tmp_path / "home"), CHIMERA_MEMORY_BACKEND="json"),
    )
    with TestClient(app) as client:
        default = client.get("/api/fs/file", params={"path": "log.txt"}).json()
        asked = client.get(
            "/api/fs/file", params={"path": "log.txt", "max_chars": 10 * MAX_VIEW_CHARS}
        ).json()
    assert len(default["content"]) == 20_000
    assert len(asked["content"]) == MAX_VIEW_CHARS
    assert asked["truncated"] is True
    assert asked["total_chars"] == MAX_VIEW_CHARS + 10
    get_settings.cache_clear()
