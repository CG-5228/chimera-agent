"""CLI coverage for per-server MCP timeout options."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_mcp_add_persists_provided_timeouts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from chimera.cli.main import app

    home = tmp_path / "home"
    monkeypatch.setenv("CHIMERA_HOME", str(home))

    result = CliRunner().invoke(
        app,
        ["mcp", "add", "analysis", "--command", "python", "--call-timeout", "600", "--connect-timeout", "60"],
    )

    assert result.exit_code == 0, result.output
    servers = json.loads((home / "mcp.json").read_text(encoding="utf-8"))
    assert servers[0]["call_timeout"] == 600.0
    assert servers[0]["connect_timeout"] == 60.0


def test_mcp_add_omits_unset_timeouts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from chimera.cli.main import app

    home = tmp_path / "home"
    monkeypatch.setenv("CHIMERA_HOME", str(home))

    result = CliRunner().invoke(app, ["mcp", "add", "analysis", "--command", "python"])

    assert result.exit_code == 0, result.output
    servers = json.loads((home / "mcp.json").read_text(encoding="utf-8"))
    assert "call_timeout" not in servers[0]
    assert "connect_timeout" not in servers[0]


def test_mcp_add_rejects_nonpositive_timeout_without_saving_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from chimera.cli.main import app

    home = tmp_path / "home"
    monkeypatch.setenv("CHIMERA_HOME", str(home))

    result = CliRunner().invoke(
        app, ["mcp", "add", "analysis", "--command", "python", "--call-timeout", "0"]
    )

    assert result.exit_code == 1
    assert not (home / "mcp.json").exists()


