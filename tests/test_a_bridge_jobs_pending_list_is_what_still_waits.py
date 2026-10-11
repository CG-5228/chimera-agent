"""A bridge job's ``pending_approvals`` lists the questions still waiting, not every one it asked.

Observed on 2026-10-10: ``desktop_job`` kept listing ~20 questions the owner had already answered,
while ``desktop_approvals list`` (the queue on disk) showed the truth. `BridgeJob.take` appended
every ``approval`` frame to ``job.approvals`` and nothing ever took one out; `_job_out` printed the
whole list whenever the latest frame was a question. The stream says when a question is ASKED and
never when it is answered or refused by silence, so the job's own memory cannot know — the question
file can: `pending.ask_durably` writes it before the frame goes out and deletes it once the question
resolves, which is what the global list reads.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sse_starlette.sse import EventSourceResponse

from chimera.api import build_api_app
from chimera.api.bridge_routes import ROUTES, BridgeRoute
from chimera.config import get_settings
from chimera.interface import ChatSession
from chimera.interface.session import SupportsRun

URL = "http://127.0.0.1:65012"


def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CHIMERA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHIMERA_DESKTOP_BRIDGE", "true")
    monkeypatch.setenv("CHIMERA_DESKTOP_BRIDGE_FULL", "false")
    get_settings.cache_clear()
    app = build_api_app(lambda: ChatSession(cast(SupportsRun, None)))
    app.state.desktop_bridge.attach(URL)
    return app


def _ask(home: Path, request_id: str, action: str) -> Path:
    directory = home / "approvals"
    directory.mkdir(parents=True, exist_ok=True)
    question = directory / f"{request_id}.ask.json"
    question.write_text(
        json.dumps(
            {"id": request_id, "action": action, "reason": "review", "asked_at": time.time()}
        ),
        encoding="utf-8",
    )
    return question


def test_answered_and_expired_questions_leave_the_jobs_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    home = tmp_path / "home"
    first = _ask(home, "qa", "run_shell: one")
    second = _ask(home, "qb", "run_shell: two")
    release = threading.Event()

    @app.post("/api/test/asks")
    async def _stream() -> EventSourceResponse:
        async def frames() -> Any:
            for qid, action in (("qa", "run_shell: one"), ("qb", "run_shell: two")):
                yield {
                    "event": "approval",
                    "data": json.dumps(
                        {
                            "id": qid,
                            "action": action,
                            "reason": "review",
                            "asked_at": time.time(),
                            "wait_seconds": 300.0,
                        }
                    ),
                }
            while not release.is_set():
                await asyncio.sleep(0.02)
            yield {"event": "done", "data": "{}"}

        return EventSourceResponse(frames())

    monkeypatch.setitem(ROUTES, "test.asks", BridgeRoute("POST", "/api/test/asks", stream=True))
    headers = {"Authorization": f"Bearer {app.state.desktop_bridge.token}"}
    with TestClient(app) as client:
        job = client.post(
            "/api/bridge/call",
            json={"route": "test.asks", "body": {}, "wait_seconds": 10},
            headers=headers,
        ).json()["job"]
        assert job["waiting_for_approval"] is True
        assert [a["id"] for a in job["pending_approvals"]] == ["qa", "qb"]
        # How long silence leaves each one, so a client can tell "waiting" from "about to refuse".
        assert all(0 < a["seconds_left"] <= 300 for a in job["pending_approvals"])

        first.unlink()  # answered in the app: the waiting thread removes the file
        later = client.get(f"/api/bridge/jobs/{job['job_id']}", headers=headers).json()
        assert [a["id"] for a in later["pending_approvals"]] == ["qb"]
        assert later["waiting_for_approval"] is True

        second.unlink()  # refused by silence after its wait: the file goes the same way
        after = client.get(f"/api/bridge/jobs/{job['job_id']}", headers=headers).json()
        assert after["pending_approvals"] == []
        assert after["waiting_for_approval"] is False
        release.set()


def test_the_mcp_summary_says_when_silence_refuses_each_question() -> None:
    from chimera.server.desktop_mcp import DesktopMCP

    job = {
        "job_id": "j3",
        "done": False,
        "waiting_for_approval": True,
        "pending_approvals": [
            {"id": "q1", "action": "run_shell: ls", "reason": "review", "seconds_left": 42}
        ],
        "events": [],
        "next": 1,
        "text": "",
    }
    text = DesktopMCP(discover=lambda: None)._render_job(job, "tok")
    assert "run_shell: ls (review)" in text and "refused by silence in 42s" in text
