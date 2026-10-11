"""A compacted coding conversation keeps the title it started with (found in the 0.65.0 visual check).

The Code screen titles a conversation with the first thing the person asked. Once a conversation
compacts, that message is gone and the first user message is compaction's own note, so the sidebar
read "[earlier conversation, compacted] 26 earlier messages were removed to free conte..." for every
long conversation, and they could not be told apart. The note also counted as a turn.

The restored block compaction writes carries the task verbatim; the title now comes from there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chimera.core.code_session import CodeSession, CodeSessionStore
from chimera.core.context_budget import RunState, compact

TASK = "Tarefa de pesquisa (fase A — comparação de modelos). Trabalhe só nesta pasta."


class _Agent:
    def run(self, *_a: Any, **_k: Any) -> Any:
        raise AssertionError("not run here")


def _compacted() -> list[Any]:
    messages: list[Any] = [{"role": "system", "content": "s"}, {"role": "user", "content": TASK}]
    for i in range(12):
        messages.append({"role": "assistant", "content": f"step {i}"})
    out, changed = compact(messages, keep_recent=3, state=RunState(task=TASK))
    assert changed
    return out[1:]  # a CodeSession stores the conversation without the system message


def test_the_title_is_the_task_not_the_compaction_note() -> None:
    session = CodeSession(_Agent(), messages=_compacted())
    assert str(session.messages[0]["content"]).startswith("[earlier conversation, compacted]")
    assert session.title() == TASK[:80]


def test_the_saved_list_shows_the_task_and_does_not_count_the_notes(tmp_path: Path) -> None:
    store = CodeSessionStore(tmp_path)
    session = CodeSession(_Agent(), messages=_compacted())
    store.save(session)
    row = next(r for r in store.list_meta() if r["id"] == session.session_id)
    assert row["title"] == TASK[:80]
    assert row["turns"] == 0  # the original turn was compacted away; the notes are not turns


def test_without_a_restored_task_the_first_message_the_person_typed_names_it() -> None:
    session = CodeSession(
        _Agent(),
        messages=[
            {"role": "user", "content": "[earlier conversation, compacted]\n9 earlier messages were removed"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "now fix the login redirect"},
        ],
    )
    assert session.title() == "now fix the login redirect"


def test_an_uncompacted_conversation_is_titled_as_before() -> None:
    session = CodeSession(_Agent(), messages=[{"role": "user", "content": "explain this\nproject"}])
    assert session.title() == "explain this project"
