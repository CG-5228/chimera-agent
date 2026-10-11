"""A turn started through the desktop bridge can be stopped there, and its job says how it stands (M1).

Observed on 2026-10-09/10 while running a research task through the bridge:

- a turn queued behind another in the same folder could not be stopped from the bridge, and read as
  one that had hung. The app could always stop a turn (``POST /api/code/turns/{id}/stop``), but the
  bridge offered no way to reach it from a job;
- a turn that failed at about 15:43 read as "still running" for 90 minutes. The job is ``done`` only
  when the stream closes, the stream closes after the turn's bookkeeping, and the summary checked
  ``done`` before it looked at the error the turn had already sent.
"""

from __future__ import annotations

import asyncio
import json
import threading
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
from chimera.server.desktop_mcp import DesktopMCP

URL = "http://127.0.0.1:65013"


def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CHIMERA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHIMERA_DESKTOP_BRIDGE", "true")
    monkeypatch.setenv("CHIMERA_DESKTOP_BRIDGE_FULL", "false")
    get_settings.cache_clear()
    app = build_api_app(lambda: ChatSession(cast(SupportsRun, None)))
    app.state.desktop_bridge.attach(URL)
    return app


def _turn(app: Any, monkeypatch: pytest.MonkeyPatch, frames: Any) -> None:
    """Stand in for the coding turn: `conversations.send` streams whatever ``frames`` yields."""

    @app.post("/api/test/turn")
    async def _stream() -> EventSourceResponse:
        return EventSourceResponse(frames())

    monkeypatch.setitem(
        ROUTES, "conversations.send", BridgeRoute("POST", "/api/test/turn", stream=True)
    )


def _session(turn_id: str) -> dict[str, str]:
    return {"event": "session", "data": json.dumps({"session_id": "s1", "turn_id": turn_id})}


def test_a_turn_queued_for_its_folder_says_so_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    live = app.state.live_turns
    live.start(turn_id="t1", session_id="s1", workspace=str(tmp_path), message="m", live_since=0)

    async def frames() -> Any:
        yield _session("t1")
        busy = {"code": "folder_busy", "text": "Waiting: another conversation is working here."}
        yield {"event": "notice", "data": json.dumps(busy)}
        stop = live.should_stop("t1")
        while not stop():  # the turn's folder wait, which polls the same signal
            await asyncio.sleep(0.02)
        live.finish("t1")
        yield {"event": "error", "data": json.dumps({"message": "stopped while waiting"})}

    _turn(app, monkeypatch, frames)
    headers = {"Authorization": f"Bearer {app.state.desktop_bridge.token}"}
    with TestClient(app) as client:
        job = client.post(
            "/api/bridge/call",
            json={"route": "conversations.send", "body": {"message": "m"}, "wait_seconds": 1},
            headers=headers,
        ).json()["job"]
        assert job["waiting_for_folder"] is True
        assert job["ended"] is False and job["turn_running"] is True

        text = DesktopMCP(discover=lambda: None)._render_job(job, "tok")
        assert "WAITING FOR THE FOLDER" in text
        assert f"desktop_job job_id={job['job_id']} stop=true" in text

        stopped = client.post(f"/api/bridge/jobs/{job['job_id']}/stop", headers=headers)
        assert stopped.status_code == 200
        assert stopped.json() == {"job_id": job["job_id"], "turn_id": "t1", "stopping": True}

        after = client.get(
            f"/api/bridge/jobs/{job['job_id']}?wait_seconds=5", headers=headers
        ).json()
        assert after["ended"] is True and after["waiting_for_folder"] is False
        assert after["error"] == "stopped while waiting"


def test_a_failure_reads_as_ended_while_the_stream_is_still_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    release = threading.Event()

    async def frames() -> Any:
        yield _session("t2")
        yield {"event": "error", "data": json.dumps({"message": "the coding turn failed"})}
        while not release.is_set():  # bookkeeping after the last word keeps the stream open
            await asyncio.sleep(0.02)

    _turn(app, monkeypatch, frames)
    headers = {"Authorization": f"Bearer {app.state.desktop_bridge.token}"}
    with TestClient(app) as client:
        job = client.post(
            "/api/bridge/call",
            json={"route": "conversations.send", "body": {"message": "m"}, "wait_seconds": 0.5},
            headers=headers,
        ).json()["job"]
        assert job["done"] is False
        assert job["ended"] is True

        text = DesktopMCP(discover=lambda: None)._render_job(job, "tok")
        assert text.startswith("Ended with an error: the coding turn failed")
        assert "Still running" not in text

        refused = client.post(f"/api/bridge/jobs/{job['job_id']}/stop", headers=headers)
        assert refused.status_code == 409 and "already ended" in refused.json()["detail"]
        release.set()


def test_a_stop_that_reaches_nothing_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    release = threading.Event()

    async def frames() -> Any:
        yield _session("t3")  # registered nowhere: the app has no such running turn
        while not release.is_set():
            await asyncio.sleep(0.02)

    _turn(app, monkeypatch, frames)

    @app.post("/api/test/other")
    async def _other() -> EventSourceResponse:
        async def done() -> Any:
            while not release.is_set():
                await asyncio.sleep(0.02)
            yield {"event": "done", "data": "{}"}

        return EventSourceResponse(done())

    monkeypatch.setitem(ROUTES, "test.other", BridgeRoute("POST", "/api/test/other", stream=True))
    headers = {"Authorization": f"Bearer {app.state.desktop_bridge.token}"}
    with TestClient(app) as client:
        assert client.post("/api/bridge/jobs/nope/stop", headers=headers).status_code == 404

        other = client.post(
            "/api/bridge/call", json={"route": "test.other", "body": {}, "wait_seconds": 0.2},
            headers=headers,
        ).json()["job"]
        wrong = client.post(f"/api/bridge/jobs/{other['job_id']}/stop", headers=headers)
        assert wrong.status_code == 400 and "runs.cancel" in wrong.json()["detail"]

        job = client.post(
            "/api/bridge/call",
            json={"route": "conversations.send", "body": {"message": "m"}, "wait_seconds": 0.5},
            headers=headers,
        ).json()["job"]
        # The registry does not list it, so the job says so rather than "still running".
        assert job["turn_running"] is False
        text = DesktopMCP(discover=lambda: None)._render_job(job, "tok")
        assert "no longer lists this turn as running" in text

        gone = client.post(f"/api/bridge/jobs/{job['job_id']}/stop", headers=headers)
        assert gone.status_code == 409 and "not running" in gone.json()["detail"]
        release.set()


def test_the_stop_route_needs_the_bridge_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.post("/api/bridge/jobs/x/stop").status_code == 401


def test_the_mcp_tool_sends_the_stop_then_reports_the_job() -> None:
    calls: list[tuple[str, str]] = []

    def http(method: str, url: str, token: str, body: Any, timeout: float) -> tuple[int, Any]:
        calls.append((method, url))
        if method == "POST":
            return 200, {"job_id": "j9", "turn_id": "t9", "stopping": True}
        return 200, {
            "job_id": "j9", "route": "conversations.send", "done": True, "ended": True,
            "error": "stopped", "events": [], "next": 3, "text": "", "result": None,
            "elapsed_seconds": 0.5,
        }

    mcp = DesktopMCP(discover=lambda: {"url": "http://x", "token": "tok", "full": False})
    mcp.http = http  # type: ignore[method-assign]
    out = json.loads(mcp.dispatch("desktop_job", {"job_id": "j9", "stop": True}))
    assert calls[0] == ("POST", "http://x/api/bridge/jobs/j9/stop")
    assert calls[1][0] == "GET"
    # Still one JSON record a client can parse, with how it stands as its first fields.
    assert list(out)[:2] == ["stop", "status"]
    assert out["stop"].startswith("requested")
    assert out["status"] == "Ended with an error: stopped"


def test_a_polled_failure_says_so_before_done_false() -> None:
    def http(method: str, url: str, token: str, body: Any, timeout: float) -> tuple[int, Any]:
        return 200, {
            "job_id": "j8", "route": "conversations.send", "done": False, "ended": True,
            "error": "the coding turn failed", "events": [], "next": 2, "text": "",
        }

    mcp = DesktopMCP(discover=lambda: {"url": "http://x", "token": "tok", "full": False})
    mcp.http = http  # type: ignore[method-assign]
    out = json.loads(mcp.dispatch("desktop_job", {"job_id": "j8"}))
    assert list(out)[0] == "status"
    assert out["status"] == "Ended with an error: the coding turn failed"
