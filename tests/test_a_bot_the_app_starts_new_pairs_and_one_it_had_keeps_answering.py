"""A bot the desktop app starts for the first time pairs with its owner; one it already had keeps
answering as it did (plan M7).

Found 2026-10-10. `chimera serve` closed new bots behind a one-time pairing code, but the app's
Messaging card starts its bots through `MessagingManager`, which asked `is_new_install` with no
snapshot of the data folder. By the time the app starts a bot that folder is never empty, so every
bot the app started was classified as an upgrade and ran open, answering anyone with the owner's
tools and spend. And had it paired, the code went only to a console nobody reads.

Now the app records, once, which bots were configured before this record existed: those keep their
posture, and a bot configured afterwards starts by pairing, with its code on the card. The desktop
bridge never receives the code: whoever sends it first becomes the bot's owner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from chimera.config import Settings, get_settings
from chimera.server.allowlist import app_bot_is_new, remember_existing_bots
from chimera.server.manager import MessagingManager


def _settings(home: Path, **tokens: str) -> Settings:
    return Settings(CHIMERA_HOME=str(home), **tokens)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_allowlist_in_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # An allowlist variable written anywhere counts as the owner's decision; none here.
    monkeypatch.chdir(tmp_path)
    for name in (
        "CHIMERA_DISCORD_ALLOWED_USERS",
        "CHIMERA_TELEGRAM_ALLOWED_USERS",
        "CHIMERA_SLACK_ALLOWED_USERS",
        "CHIMERA_SIGNAL_ALLOWED_USERS",
        "CHIMERA_WHATSAPP_ALLOWED_NUMBERS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_a_bot_configured_before_the_record_keeps_answering_as_it_did(tmp_path: Path) -> None:
    settings = _settings(tmp_path, CHIMERA_TELEGRAM_BOT_TOKEN="t")
    (tmp_path / "memory.db").write_text("x", encoding="utf-8")  # an install in use
    remember_existing_bots(settings)
    assert app_bot_is_new(settings, "telegram") is False


def test_a_bot_configured_after_the_record_is_new(tmp_path: Path) -> None:
    remember_existing_bots(_settings(tmp_path))  # first app start: no bot configured yet
    later = _settings(tmp_path, CHIMERA_TELEGRAM_BOT_TOKEN="t")
    # Not rewritten by a later start, or the bot configured in between would read as existing.
    remember_existing_bots(later)
    assert json.loads((tmp_path / "app-bots-known.json").read_text(encoding="utf-8")) == {
        "existing": []
    }
    assert app_bot_is_new(later, "telegram") is True


def test_an_allowlist_variable_written_even_empty_is_the_owners_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remember_existing_bots(_settings(tmp_path))
    monkeypatch.setenv("CHIMERA_TELEGRAM_ALLOWED_USERS", "")
    assert app_bot_is_new(_settings(tmp_path, CHIMERA_TELEGRAM_BOT_TOKEN="t"), "telegram") is False


def test_an_unreadable_record_keeps_the_old_behaviour(tmp_path: Path) -> None:
    # No record at all: unknown keeps a bot someone may rely on answering, rather than silencing it.
    assert app_bot_is_new(_settings(tmp_path, CHIMERA_TELEGRAM_BOT_TOKEN="t"), "telegram") is False


def _manager(settings: Settings) -> MessagingManager:
    return MessagingManager(
        settings=settings,
        backend=cast(Any, object()),
        model=None,
        max_steps=4,
        workspace=settings.home,
    )


def test_a_new_bot_the_app_starts_pairs_and_its_card_gets_the_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "memory.db").write_text("x", encoding="utf-8")  # never empty when the app runs
    remember_existing_bots(_settings(tmp_path))
    settings = _settings(tmp_path, CHIMERA_TELEGRAM_BOT_TOKEN="t")
    mgr = _manager(settings)
    adapter = mgr._default_adapter("telegram")
    assert adapter.pairing_flow is not None
    monkeypatch.setattr(mgr, "is_running", lambda platform: platform == "telegram")

    row = mgr.status()["telegram"]
    assert row["pairing_code"] == adapter.pairing_flow.code
    assert row["pairing"] is True and row["open"] is False

    # Claimed: the first person who sends it becomes the one the bot answers, and the code is gone.
    assert adapter.pairing_flow.authorize("owner-1", adapter.pairing_flow.code) is False
    after = mgr.status()["telegram"]
    assert after["pairing_code"] is None and after["pairing"] is False and after["open"] is False


def test_an_existing_open_bot_says_it_is_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, CHIMERA_TELEGRAM_BOT_TOKEN="t")
    remember_existing_bots(settings)
    mgr = _manager(settings)
    adapter = mgr._default_adapter("telegram")
    assert adapter.pairing_flow is None
    monkeypatch.setattr(mgr, "is_running", lambda platform: platform == "telegram")
    assert mgr.status()["telegram"]["open"] is True


def test_the_bridge_learns_a_pairing_is_pending_but_not_the_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from chimera.api import build_api_app
    from chimera.interface import ChatSession
    from chimera.interface.session import SupportsRun

    class _Manager:
        def status(self) -> dict[str, Any]:
            return {
                "telegram": {
                    "configured": True, "running": True, "error": None,
                    "pairing_code": "K7Q2ZP4M", "pairing": True, "open": False,
                }
            }

    monkeypatch.setenv("CHIMERA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHIMERA_DESKTOP_BRIDGE", "true")
    monkeypatch.setenv("CHIMERA_DESKTOP_BRIDGE_FULL", "false")
    get_settings.cache_clear()
    app = build_api_app(
        lambda: ChatSession(cast(SupportsRun, None)), messaging_manager=cast(Any, _Manager())
    )
    app.state.desktop_bridge.attach("http://127.0.0.1:65014")
    headers = {"Authorization": f"Bearer {app.state.desktop_bridge.token}"}
    with TestClient(app) as client:
        out = client.post(
            "/api/bridge/call", json={"route": "app.messaging"}, headers=headers
        ).json()
    row = out["data"]["telegram"]
    assert row["pairing"] is True
    assert row["pairing_code"] is None
    assert "K7Q2ZP4M" not in json.dumps(out)
    get_settings.cache_clear()
