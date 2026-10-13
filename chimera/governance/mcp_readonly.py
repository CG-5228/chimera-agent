"""Keep rea's target-changing tools out of unattended MCP surfaces.

The tool list follows rea-agents 6.4.0's TOOL_EFFECTS entries marked
``executesForeignCode``, ``mutatesDevice`` or ``mutatesTarget``.
"""

from __future__ import annotations

from chimera.config import Settings
from chimera.integrations.mcp_catalog import CATALOG
from chimera.integrations.mcp_config import load_servers

REA_WRITE_TOOLS: frozenset[str] = frozenset(next(e.exec_tools for e in CATALOG if e.id == "rea"))


def is_unattended(surface: str) -> bool:
    """Whether ``surface`` has no human available to approve a target-changing action."""
    return (
        surface.startswith("app-messaging")
        or surface.startswith("cron:")
        or surface in {"a2a", "mcp", "github-issue"}
    )


def read_only_denials(settings: Settings) -> list[str]:
    """Return prefixed names of catalogued MCP write tools configured for rea."""
    servers = load_servers(settings.home / "mcp.json")
    denials: set[str] = set()
    for cfg in servers:
        command_line = f"{cfg.command} {' '.join(cfg.args)}"
        for entry in CATALOG:
            if not entry.exec_tools:
                continue
            if entry.id == cfg.name or (entry.match and entry.match in command_line):
                denials.update(f"{cfg.name}_{tool}" for tool in entry.exec_tools)
    return sorted(denials)
