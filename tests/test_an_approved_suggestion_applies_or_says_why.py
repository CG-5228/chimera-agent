"""The owner's yes on a settings suggestion either writes it or says why it did not.

Observed on 2026-10-09/10 (Chimera Desktop 0.64.5, Windows): the owner approved a suggestion to
change ``CHIMERA_DEFAULT_MODEL``, the card stayed in the queue, the setting did not change, and only
a second yes applied it. The history file shows one line per card, so the first yes ended nothing.

`setting_suggestions.resolve` named every refusal it expected — ``stale``, ``invalid``, ``expired``,
``changed`` — and caught only ``ValueError`` around the write. Anything else the write raised (an
``OSError`` from ``.env`` held open by another reader, a temporary file the scanner had not let go
of) escaped the route as a 500. The card's file was untouched, so it stayed listed; the screen's
answer handler had no ``catch``, so it said nothing; and the next poll drew the same card again. To
the owner that is exactly "I approved it and it is still pending".

Held here: such a failure answers ``failed`` with the reason, writes nothing, and leaves the card
waiting so the owner's next yes is a real retry — not a write the owner never saw happen.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from chimera.api import build_api_app
from chimera.config import get_settings
from chimera.governance import setting_suggestions
from chimera.governance.pending import history, pending
from chimera.interface import ChatSession
from chimera.interface.session import SupportsRun

URL = "http://127.0.0.1:65011"
KEY = "CHIMERA_DEFAULT_MODEL"
BEFORE = "openrouter/vendor/before"
AFTER = "openrouter/vendor/after"


def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CHIMERA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHIMERA_SERVER_TOKEN", "")
    monkeypatch.setenv("CHIMERA_DESKTOP_BRIDGE", "true")
    monkeypatch.setenv("CHIMERA_DESKTOP_BRIDGE_FULL", "true")
    monkeypatch.setenv(KEY, BEFORE)
    get_settings.cache_clear()
    app = build_api_app(lambda: ChatSession(cast(SupportsRun, None)))
    app.state.desktop_bridge.attach(URL)
    return app


def _suggest(client: TestClient, app: Any) -> str:
    headers = {"Authorization": f"Bearer {app.state.desktop_bridge.token}"}
    made = client.post(
        "/api/bridge/call",
        json={"route": "settings.edit", "body": {KEY: AFTER}},
        headers=headers,
    )
    assert made.status_code == 200 and made.json()["status"] == 202, made.text
    return str(made.json()["data"]["suggestion"])


def _yes(client: TestClient, tmp_path: Path, request_id: str) -> Any:
    s = setting_suggestions.read(tmp_path / "home", request_id)
    assert s is not None
    return client.post(
        f"/api/approvals/{request_id}",
        json={"approved": True, "digest": setting_suggestions.digest(s)},
    )


def _env_file(tmp_path: Path) -> str:
    env = tmp_path / ".env"
    return env.read_text(encoding="utf-8") if env.exists() else ""


def test_a_write_that_fails_says_so_and_the_card_waits_for_another_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from chimera.api import config_api

    app = _app(tmp_path, monkeypatch)
    real_write = config_api._write_env_var
    attempts: list[str] = []

    def locked_once(path: Path, key: str, value: str) -> None:
        attempts.append(key)
        if len(attempts) == 1:
            # What Windows answers while another process holds the file open without sharing it.
            raise PermissionError(13, "The process cannot access the file", str(path))
        real_write(path, key, value)

    monkeypatch.setattr(config_api, "_write_env_var", locked_once)
    with TestClient(app, raise_server_exceptions=False) as client:
        request_id = _suggest(client, app)
        first = _yes(client, tmp_path, request_id)
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["ok"] is True and body["outcome"] == "failed"
        # The reason, so the screen has something to say — and never the value.
        assert "PermissionError" in body["detail"] and AFTER not in body["detail"]
        assert f"{KEY}={AFTER}" not in _env_file(tmp_path)
        assert os.environ[KEY] == BEFORE
        # Still waiting, and nothing in the history claims it was answered.
        assert [q.id for q in pending(tmp_path / "home")] == [request_id]
        assert not any(row.get("id") == request_id for row in history(tmp_path / "home"))

        second = _yes(client, tmp_path, request_id)
    assert second.json() == {"ok": True, "outcome": "applied", "detail": KEY}
    assert os.environ[KEY] == AFTER
    assert pending(tmp_path / "home") == []
    get_settings.cache_clear()


def test_a_reading_of_the_current_value_that_fails_says_so_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The comparison against the value the card showed reads the live settings; a read that raises
    is the same unseen 500 one step earlier."""
    home = tmp_path / "home"
    request_id = setting_suggestions.suggest(
        home, [setting_suggestions.Change(KEY, BEFORE, AFTER)], suggested_by="desktop_bridge"
    )
    s = setting_suggestions.read(home, request_id)
    assert s is not None

    def unreadable(key: str) -> str:
        raise OSError(5, "Access is denied")

    written: list[dict[str, str]] = []
    outcome, detail = setting_suggestions.resolve(
        home,
        request_id,
        True,
        via="app",
        current_of=unreadable,
        check=lambda updates: None,
        apply=written.append,
        allowed=lambda key: True,
        shown=setting_suggestions.digest(s),
    )
    assert outcome == "failed" and "OSError" in detail
    assert written == []
    assert setting_suggestions.is_suggestion(home, request_id)


# The history recorded every approved card as `approved`, including the ones that wrote nothing
# because the setting had moved (`stale`) or was no longer suggestable (`invalid`): it could not
# tell "approved and applied" from "approved and not applied" (noted in #852). `outcome` keeps the
# shared vocabulary; `result` says what the yes led to.
def test_the_history_says_an_approved_suggestion_was_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        request_id = _suggest(client, app)
        assert _yes(client, tmp_path, request_id).status_code == 200
    row = [r for r in history(tmp_path / "home") if r["id"] == request_id][-1]
    assert row["outcome"] == "approved" and row["result"] == "applied"


def test_the_history_says_an_approved_suggestion_that_went_stale_wrote_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        request_id = _suggest(client, app)
        # Someone changed the setting after the card was raised: the yes was given to a change
        # from a value that is no longer there.
        monkeypatch.setenv(KEY, "openrouter/vendor/someone-else")
        get_settings.cache_clear()
        _yes(client, tmp_path, request_id)
    row = [r for r in history(tmp_path / "home") if r["id"] == request_id][-1]
    assert row["outcome"] == "approved" and row["result"] == "stale"


def test_a_refused_suggestion_carries_no_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        request_id = _suggest(client, app)
        s = setting_suggestions.read(tmp_path / "home", request_id)
        assert s is not None
        client.post(
            f"/api/approvals/{request_id}",
            json={"approved": False, "digest": setting_suggestions.digest(s)},
        )
    row = [r for r in history(tmp_path / "home") if r["id"] == request_id][-1]
    assert row["outcome"] == "refused" and "result" not in row
