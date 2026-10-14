"""Per-server MCP response caps persist and are applied at the session boundary."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from chimera.integrations.mcp_client import StdioMCPSession, StreamableHTTPMCPSession
from chimera.integrations.mcp_config import McpServerConfig, load_servers, save_servers


class _FakeClientSession:
    def __init__(self, result: Any) -> None:
        self.result = result

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return self.result


def _result(text: str, *, is_error: bool = False) -> Any:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], isError=is_error)


def _with_fake_session(session: Any, result: Any) -> tuple[Any, asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    session._loop = loop
    session._session = _FakeClientSession(result)
    return session, loop


def _close_loop(loop: asyncio.AbstractEventLoop) -> None:
    loop.call_soon_threadsafe(loop.stop)


def test_output_cap_serializes_only_when_set_and_round_trips(tmp_path: Path) -> None:
    plain = McpServerConfig(name="plain", command="server")
    capped = McpServerConfig(name="rea", command="server", max_output_chars=5000)
    assert "max_output_chars" not in plain.model_dump()
    assert capped.model_dump()["max_output_chars"] == 5000

    path = tmp_path / "mcp.json"
    save_servers(path, [plain, capped])
    loaded = load_servers(path)
    assert [config.max_output_chars for config in loaded] == [None, 5000]
    assert json.loads(path.read_text(encoding="utf-8"))[1]["max_output_chars"] == 5000


def test_stdio_caps_output_after_formatting_and_preserves_error_marker() -> None:
    session, loop = _with_fake_session(
        StdioMCPSession("unused", max_output_chars=12), _result("abcdefghijk", is_error=True)
    )
    try:
        output = session.call_tool("analyze", {})
    finally:
        _close_loop(loop)

    assert output.startswith("error: ")
    assert output.endswith("[truncated, 18 chars total; limit 12 chars]")
    assert "abcdefghijk" not in output


def test_stdio_without_cap_preserves_the_complete_result() -> None:
    expected = "a" * 100
    session, loop = _with_fake_session(StdioMCPSession("unused"), _result(expected))
    try:
        assert session.call_tool("analyze", {}) == expected
    finally:
        _close_loop(loop)


def test_http_session_caps_output_too() -> None:
    session, loop = _with_fake_session(
        StreamableHTTPMCPSession("http://localhost", max_output_chars=4), _result("abcdef")
    )
    try:
        output = session.call_tool("analyze", {})
    finally:
        _close_loop(loop)

    assert output.startswith("abcd\n... [truncated, 6 chars total; limit 4 chars]")


def test_http_from_config_uses_server_output_cap() -> None:
    config = McpServerConfig(name="rea", url="http://localhost", max_output_chars=123)
    session = StreamableHTTPMCPSession.from_config(config)
    assert session.max_output_chars == 123


def test_cli_mcp_add_persists_cap_and_rejects_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from chimera.cli.main import app

    home = tmp_path / "home"
    monkeypatch.setenv("CHIMERA_HOME", str(home))
    runner = CliRunner()

    added = runner.invoke(
        app,
        ["mcp", "add", "rea", "--command", "python", "--max-output-chars", "5000"],
    )
    assert added.exit_code == 0, added.output
    assert json.loads((home / "mcp.json").read_text(encoding="utf-8"))[0]["max_output_chars"] == 5000

    rejected = runner.invoke(
        app,
        ["mcp", "add", "zero", "--command", "python", "--max-output-chars", "0"],
    )
    assert rejected.exit_code == 1
    assert "--max-output-chars must be greater than 0" in rejected.output
    assert len(load_servers(home / "mcp.json")) == 1
