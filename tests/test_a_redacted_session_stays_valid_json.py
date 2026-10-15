from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chimera.core.code_session import CodeSession, CodeSessionStore
from chimera.core.redact import redact_json
from chimera.core.steplog import StepLog


class _Agent:
    def run(self, task: str, **_: Any) -> Any:
        raise AssertionError("saving a session must not run the agent")


def _credential_text() -> str:
    return 'command arguments:\n"--header", "Authorization: Bearer abc123",\nnext argument'


def test_saving_a_redacted_session_keeps_the_file_valid_json(tmp_path: Path) -> None:
    store = CodeSessionStore(tmp_path)
    session = CodeSession(_Agent(), session_id="credential-session")
    session.messages = [{"role": "user", "content": _credential_text()}]

    store.save(session)

    saved = (tmp_path / "credential-session.json").read_text(encoding="utf-8")
    data = json.loads(saved)
    assert data["messages"][0]["content"]
    assert "abc123" not in saved


def test_steplog_writes_a_redacted_valid_jsonl_record(tmp_path: Path) -> None:
    path = tmp_path / "steps.jsonl"

    StepLog().write(path, task=_credential_text(), stopped_reason="final")

    line = path.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["task"]
    assert "abc123" not in line


def test_redact_json_preserves_structure_and_non_string_values() -> None:
    value = {
        "items": ["Authorization: Bearer abc123", 7, False, None, ("plain", 3)],
        "count": 2,
        "enabled": True,
        "missing": None,
    }

    redacted = redact_json(value)

    assert isinstance(redacted, dict)
    assert redacted["items"] == ["Authorization: [redacted]", 7, False, None, ("plain", 3)]
    assert redacted["count"] == 2
    assert redacted["enabled"] is True
    assert redacted["missing"] is None
    assert isinstance(redacted["items"], list)
    assert isinstance(redacted["items"][4], tuple)
