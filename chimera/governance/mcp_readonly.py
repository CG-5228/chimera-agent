"""Select and wrap catalogued rea tools for per-invocation owner alerts and audit records.

The tool list follows rea-agents 6.4.0's TOOL_EFFECTS entries marked
``executesForeignCode``, ``mutatesDevice`` or ``mutatesTarget``. These tools remain available;
this module no longer enforces read-only restrictions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from chimera.config import Settings
from chimera.integrations.mcp_catalog import CATALOG
from chimera.integrations.mcp_config import load_servers
from chimera.tools.base import Tool, is_refusal
from chimera.tools.registry import ToolRegistry

_log = logging.getLogger(__name__)

REA_WRITE_TOOLS: frozenset[str] = frozenset(next(e.exec_tools for e in CATALOG if e.id == "rea"))


def rea_alert_names(settings: Settings) -> list[str]:
    """Return names of configured rea tools that execute code or mutate a target.

    This preserves the catalogue-name and package-match rules used by the former denial helper,
    but the returned names are now selected for alert wrapping, not removal.
    """
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


class ReaAlertTool(Tool):
    """Execute a catalogued rea tool and report each invocation to the owner."""

    def __init__(
        self,
        inner: Tool,
        *,
        surface: str,
        audit: Any,
        alert: Callable[[str], None] | None,
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self.description = inner.description
        self.parameters = inner.parameters
        self.open_arguments = getattr(inner, "open_arguments", False)
        self.untrusted_output = getattr(inner, "untrusted_output", False)
        self._surface = surface
        self._audit = audit
        self._alert = alert

    def __getattr__(self, name: str) -> Any:
        """Expose optional tool capabilities (approval hooks, reach settings) to outer layers."""
        return getattr(self.inner, name)

    def run(self, **kwargs: Any) -> str:
        """Run the original tool; the alert is additional and never changes its result."""
        result = self.inner.run(**kwargs)
        if is_refusal(result):
            return result

        at = datetime.now(UTC).isoformat()
        payload = {"tool": self.name, "surface": self._surface, "at": at}
        try:
            self._audit.record("rea_tool_executed", payload)
        except Exception:  # noqa: BLE001 — audit failure must not change tool behavior
            _log.exception("rea execution audit failed for %s on %s", self.name, self._surface)
        if self._alert is not None:
            try:
                self._alert(
                    f"Chimera ran rea tool {self.name} on {self._surface} at {at}."
                )
            except Exception:  # noqa: BLE001 — notification failure must not change tool behavior
                _log.warning("rea execution alert failed for %s on %s", self.name, self._surface)
        else:
            _log.warning("rea tool %s ran on %s at %s", self.name, self._surface, at)
        return result


def alert_rea_tools(
    registry: ToolRegistry,
    *,
    settings: Settings,
    surface: str,
    audit: Any,
    alert: Callable[[str], None] | None = None,
) -> ToolRegistry:
    """Wrap configured rea target-changing tools for per-call audit and owner alerts.

    An explicit ``alert`` is the surface's notice sink (and the test seam). Otherwise the
    configured approval webhook is the existing out-of-band channel; the audit log remains the
    durable in-app record when no webhook is configured. Wrapping is independent of the surface's
    approval capability, so any existing approval or ledger layer remains active around these tools.
    """
    names = set(rea_alert_names(settings))
    tools = registry.tools()
    if not any(tool.name in names for tool in tools):
        # Off-mode tests require identity, and an installation without rea must remain unchanged.
        return registry
    if alert is None:
        from chimera.governance.approval import deliverer_for

        alert = deliverer_for(settings)
    wrapped = ToolRegistry.like(registry)
    for tool in tools:
        wrapped.register(
            ReaAlertTool(tool, surface=surface, audit=audit, alert=alert)
            if tool.name in names
            else tool
        )
    return wrapped
