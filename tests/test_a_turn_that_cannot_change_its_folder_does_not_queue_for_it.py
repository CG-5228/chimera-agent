"""A coding turn that cannot change its folder does not wait for the folder lock, nor hold it (M20).

Observed 2026-10-09/10 while running a research task through the desktop bridge: conversations that
only read files queued one behind another in the same folder, because every turn took the folder's
lock. The lock exists so that a snapshot, a verification and an undo describe one turn's edits; a
turn given no write and no exec tool makes none.

Decided from the tools the turn was actually given, and "can change" whenever that cannot be shown:
an external agent, an agent whose tools cannot be listed, the deferred proxies, an MCP tool.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from chimera.api.code_api import turn_can_change_the_folder
from chimera.config import Settings, get_settings
from chimera.core.agent import AgentResult
from chimera.interface import ChatSession
from chimera.tools import ToolRegistry
from chimera.tools.base import Tool

TIMEOUT = 10.0


class _Named(Tool):
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, name: str, *, open_arguments: bool = False) -> None:
        self.name = name
        self.description = name
        self.open_arguments = open_arguments

    def run(self, **kwargs: Any) -> str:
        return "ok"


class _Agent:
    def __init__(self, tools: ToolRegistry | None) -> None:
        if tools is not None:
            self.tools = tools


def _registry(*tools: Tool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def test_only_a_turn_shown_to_be_unable_to_change_the_folder_skips_the_lock() -> None:
    reads = _registry(_Named("read_file"), _Named("grep"), _Named("list_dir"))
    assert turn_can_change_the_folder(_Agent(reads), None) is False

    assert turn_can_change_the_folder(_Agent(_registry(_Named("write_file"))), None) is True
    assert turn_can_change_the_folder(_Agent(_registry(_Named("run_shell"))), None) is True
    assert turn_can_change_the_folder(_Agent(_registry(_Named("tool_call"))), None) is True
    assert turn_can_change_the_folder(
        _Agent(_registry(_Named("fs_server_write", open_arguments=True))), None
    ) is True
    assert turn_can_change_the_folder(_Agent(None), None) is True  # tools that cannot be listed
    assert turn_can_change_the_folder(_Agent(reads), "codex") is True  # an external agent edits


# ----------------------------------------------------------------------------- the route


class _Turn:
    """Records which turns entered, keeps the registry it was given, and can be held open."""

    hold = threading.Event()
    held = threading.Event()
    entered: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if len(args) > 1 and isinstance(args[1], ToolRegistry):
            self.tools = args[1]

    def run(self, task: str, should_stop: Any = None, **_kw: Any) -> AgentResult:
        type(self).entered.append(task.split(" [")[0].split("\n")[-1])
        if "hold" in task:
            type(self).held.set()
            deadline = time.monotonic() + TIMEOUT
            while not type(self).hold.is_set() and time.monotonic() < deadline:
                if should_stop is not None and should_stop():
                    break
                time.sleep(0.01)
        return AgentResult(
            answer="done", steps=1, stopped_reason="final",
            transcript=[{"role": "user", "content": task}, {"role": "assistant", "content": "done"}],
        )


@pytest.fixture
def turn() -> Any:
    _Turn.hold.clear()
    _Turn.held.clear()
    _Turn.entered = []
    yield _Turn
    _Turn.hold.set()


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import chimera.core
    from chimera.api import build_api_app

    home = tmp_path / "home"
    monkeypatch.setenv("CHIMERA_HOME", str(home))
    get_settings.cache_clear()
    monkeypatch.setattr(chimera.core, "Agent", _Turn, raising=True)
    ws = tmp_path / "default-ws"
    ws.mkdir(exist_ok=True)
    settings = Settings(CHIMERA_HOME=str(home), CHIMERA_MEMORY_BACKEND="json")
    return TestClient(build_api_app(lambda: ChatSession(_Turn()), workspace=ws, settings=settings))


def _send(client: TestClient, folder: Path, message: str, *, read_only: bool) -> str:
    body: dict[str, Any] = {
        "message": f"{message} [{folder}]", "workspace": str(folder), "stream": False,
    }
    if read_only:
        body["posture"] = {"reach": "read_only", "approval": "never"}
    return client.post("/api/code/turn", json=body).text


def test_a_read_only_turn_runs_while_a_writing_turn_holds_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, turn: Any
) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    client = _client(tmp_path, monkeypatch)
    writer = threading.Thread(
        target=lambda: _send(client, folder, "hold", read_only=False), daemon=True
    )
    writer.start()
    assert turn.held.wait(TIMEOUT)

    reply = _send(client, folder, "read", read_only=True)

    assert "folder_busy" not in reply
    assert turn.entered == ["hold", "read"]
    turn.hold.set()
    writer.join(TIMEOUT)


def test_a_read_only_turn_does_not_make_a_writing_turn_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, turn: Any
) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    client = _client(tmp_path, monkeypatch)
    reader = threading.Thread(
        target=lambda: _send(client, folder, "hold", read_only=True), daemon=True
    )
    reader.start()
    assert turn.held.wait(TIMEOUT)

    reply = _send(client, folder, "write", read_only=False)

    assert "folder_busy" not in reply
    assert turn.entered == ["hold", "write"]
    turn.hold.set()
    reader.join(TIMEOUT)


def test_two_writing_turns_still_take_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, turn: Any
) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    client = _client(tmp_path, monkeypatch)
    replies: dict[str, str] = {}
    first = threading.Thread(
        target=lambda: replies.setdefault("first", _send(client, folder, "hold", read_only=False)),
        daemon=True,
    )
    first.start()
    assert turn.held.wait(TIMEOUT)
    second = threading.Thread(
        target=lambda: replies.setdefault("second", _send(client, folder, "write", read_only=False)),
        daemon=True,
    )
    second.start()
    time.sleep(0.4)
    assert turn.entered == ["hold"]
    turn.hold.set()
    first.join(TIMEOUT)
    second.join(TIMEOUT)
    assert "folder_busy" in replies["second"]
