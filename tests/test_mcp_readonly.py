"""Tests for rea's target-changing tools and unattended-surface policy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chimera.config import Settings
from chimera.governance.mcp_readonly import REA_WRITE_TOOLS, is_unattended, read_only_denials


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, CHIMERA_HOME=str(tmp_path / "home"))


def test_rea_write_tool_catalog_is_the_expected_set() -> None:
    assert frozenset(
        {
            "instrument_with_frida",
            "load_frida_script",
            "unload_frida_script",
            "start_frida_session",
            "resume_frida_session",
            "close_frida_session",
            "install_adb_package",
            "uninstall_adb_package",
            "push_adb_file",
            "start_adb_app",
            "start_adb_activity",
            "stop_adb_app",
            "capture_process_scenario",
            "capture_browser_scenario",
            "capture_electron_scenario",
            "capture_native_ui_scenario",
            "observe_native_calls",
            "observe_web_execution",
            "annotate_native_function",
            "set_comment",
            "set_inline_comment",
            "set_address_name",
            "set_addresses_names",
            "set_bookmark",
            "unset_bookmark",
        }
    ) == REA_WRITE_TOOLS


@pytest.mark.parametrize(
    ("surface", "expected"),
    [
        ("app-messaging:discord", True),
        ("cron:task", True),
        ("a2a", True),
        ("mcp", True),
        ("github-issue", True),
        ("chat", False),
        ("tui", False),
        ("assist", False),
        ("api:run", False),
    ],
)
def test_surface_attendance_classification(surface: str, expected: bool) -> None:
    assert is_unattended(surface) is expected


def test_read_only_denials_for_catalogue_name(settings: Settings) -> None:
    settings.home.mkdir(parents=True, exist_ok=True)
    (settings.home / "mcp.json").write_text(
        json.dumps([{"name": "rea", "command": "npx", "args": ["-y", "rea"]}]),
        encoding="utf-8",
    )

    assert read_only_denials(settings) == sorted(f"rea_{tool}" for tool in REA_WRITE_TOOLS)


def test_read_only_denials_without_rea_server(settings: Settings) -> None:
    settings.home.mkdir(parents=True, exist_ok=True)
    (settings.home / "mcp.json").write_text(
        json.dumps([{"name": "other", "command": "node", "args": ["server.js"]}]),
        encoding="utf-8",
    )

    assert read_only_denials(settings) == []


def test_read_only_denials_match_package_when_name_differs(settings: Settings) -> None:
    settings.home.mkdir(parents=True, exist_ok=True)
    (settings.home / "mcp.json").write_text(
        json.dumps(
            [
                {
                    "name": "reverse-engineer",
                    "command": "npx",
                    "args": ["-y", "--package=rea-agents@6.4.0", "rea", "mcp"],
                }
            ]
        ),
        encoding="utf-8",
    )

    assert read_only_denials(settings) == sorted(
        f"reverse-engineer_{tool}" for tool in REA_WRITE_TOOLS
    )


def test_read_only_denials_require_configured_rea_tools(settings: Settings) -> None:
    settings.home.mkdir(parents=True, exist_ok=True)
    (settings.home / "mcp.json").write_text(
        json.dumps([{"name": "rea", "command": "npx", "args": ["-y", "rea"]}]),
        encoding="utf-8",
    )

    assert len(read_only_denials(settings)) == 25
    assert all(name.startswith("rea_") for name in read_only_denials(settings))


def test_rea_catalog_declares_no_auth_secrets() -> None:
    from chimera.integrations.mcp_catalog import CATALOG

    rea = next(entry for entry in CATALOG if entry.id == "rea")
    assert rea.auth == "none"
    assert rea.secrets == []
    assert len(rea.exec_tools) == 25
    assert rea.exec_tools == tuple(sorted(REA_WRITE_TOOLS))
    assert rea.match == "rea-agents"

