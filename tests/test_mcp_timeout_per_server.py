"""Per-server MCP timeouts persist without changing legacy config serialization."""

from __future__ import annotations

from typing import Any

from chimera.integrations.mcp_client import StdioMCPSession
from chimera.integrations.mcp_config import McpServerConfig, load_servers, save_servers


def test_call_timeout_serializes_only_when_configured(tmp_path: Any) -> None:
    configured = McpServerConfig(name="x", command="c", call_timeout=600)
    assert configured.model_dump()["call_timeout"] == 600

    legacy = McpServerConfig(name="legacy", command="c")
    assert "call_timeout" not in legacy.model_dump()
    assert "connect_timeout" not in legacy.model_dump()

    path = tmp_path / "mcp.json"
    save_servers(path, [configured])
    loaded = load_servers(path)
    assert len(loaded) == 1
    assert loaded[0].call_timeout == 600


def test_stdio_session_call_timeout_defaults_and_override() -> None:
    assert StdioMCPSession("unused", call_timeout=5).call_timeout == 5
    assert StdioMCPSession("unused").call_timeout == 120.0
