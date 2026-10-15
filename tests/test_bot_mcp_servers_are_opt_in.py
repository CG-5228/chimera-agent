"""Bot MCP mounting is explicit: global autoload is not permission to expose owner servers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chimera.config import Settings
from chimera.governance.profile import governed_profile
from chimera.tools.base import Tool
from chimera.tools.registry import ToolRegistry


class _Tool(Tool):
    description = "test tool"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def run(self, **kwargs: Any) -> str:
        self.calls += 1
        return "ok"


class _Pool:
    def __init__(self) -> None:
        self.tools = {"private": _Tool("private_read"), "public": _Tool("public_read")}

    def names(self) -> list[str]:
        return list(self.tools)

    def get(self, name: str) -> Any:
        tool = self.tools[name]
        return type(
            "Connector", (), {"name": name, "tools": lambda self, tool=tool: [tool]}
        )()

    def into_tool_registry(self, registry: ToolRegistry) -> int:
        for tool in self.tools.values():
            registry.register(tool)
        return len(self.tools)


class _MCP:
    def __init__(self, pool: _Pool) -> None:
        self.pool = pool
        self.requests = 0

    def connectors(self, settings: Settings) -> _Pool:
        self.requests += 1
        return self.pool


def _settings(home: Path, *, opt_in: str = "") -> Settings:
    return Settings(
        _env_file=None,
        CHIMERA_HOME=str(home),
        CHIMERA_MCP_AUTOLOAD=True,
        CHIMERA_BOT_MCP_SERVERS=opt_in,
    )


def test_bot_never_mounts_global_mcp_autoload_without_server_opt_in(
    tmp_path: Path, monkeypatch: Any
) -> None:
    pool = _Pool()
    mcp = _MCP(pool)
    monkeypatch.setattr("chimera.integrations.mcp_pool.connectors", mcp.connectors)
    settings = _settings(tmp_path)
    registry = ToolRegistry()

    governed_profile(registry, settings=settings, home=tmp_path, surface="app-messaging:discord")

    assert mcp.requests == 0
    assert "private_read" not in registry
    assert "public_read" not in registry


def test_bot_mounts_only_named_mcp_servers_and_the_readonly_fence_still_applies(
    tmp_path: Path, monkeypatch: Any
) -> None:
    # This fake rea server makes the production policy read-only without starting MCP or touching
    # the network; the ordinary selected server remains available to the bot.
    (tmp_path / "mcp.json").write_text(
        '[{"name":"rea","command":"rea-agents","args":[]},'
        '{"name":"public","command":"node","args":[]}]',
        encoding="utf-8",
    )
    rea_tool = _Tool("rea_instrument_with_frida")
    public_tool = _Tool("public_read")
    private_tool = _Tool("private_read")
    pool = _Pool()
    pool.tools = {"rea": rea_tool, "public": public_tool, "private": private_tool}
    mcp = _MCP(pool)

    monkeypatch.setattr("chimera.integrations.mcp_pool.connectors", mcp.connectors)
    settings = _settings(tmp_path, opt_in="rea, public")
    registry = ToolRegistry()

    governed_profile(registry, settings=settings, home=tmp_path, surface="platform:discord")

    assert mcp.requests == 1
    assert "public_read" in registry
    assert "private_read" not in registry
    assert "rea_instrument_with_frida" not in registry


def test_settings_reads_the_bot_server_opt_in_from_its_environment(monkeypatch: Any) -> None:
    monkeypatch.setenv("CHIMERA_BOT_MCP_SERVERS", "github, rea")
    settings = Settings(_env_file=None)

    assert settings.bot_mcp_servers == "github, rea"
