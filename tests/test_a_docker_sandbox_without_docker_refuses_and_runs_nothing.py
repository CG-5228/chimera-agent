"""With the docker sandbox chosen and no daemon, a command is refused and nothing runs (plan M8).

It used to run on the host with one warning in the log (`chimera/sandbox/docker.py`, "falling back
to the local sandbox"). The person who chose a container had their commands run on their own
computer, and nothing on any screen said so. Now the command is refused with the reason and the two
ways out; a caller that wants the host passes ``fallback=`` itself.

The verifier is the one place where a refusal must not read as a failure: verify-or-revert would
undo a change because a daemon was down. There it abstains, as it does for a command that does not
exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from chimera.core.verify import CommandVerifier
from chimera.sandbox import LocalSandbox, get_sandbox
from chimera.sandbox.docker import (
    DOCKER_UNAVAILABLE,
    DOCKER_UNAVAILABLE_EXIT,
    RECHECK_SECONDS,
    DockerSandbox,
    docker_refusal,
)
from chimera.tools.code import ExecuteCodeTool
from chimera.tools.shell import RunShellTool


def _down(sandbox: DockerSandbox, monkeypatch: pytest.MonkeyPatch) -> DockerSandbox:
    monkeypatch.setattr(sandbox, "available", lambda: False)
    return sandbox


def _never_asked(command: str) -> bool:
    raise AssertionError(f"the person was asked about a command that cannot run: {command}")


def test_the_configured_sandbox_refuses_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHIMERA_SANDBOX", "docker")
    from chimera.config import Settings

    sandbox = get_sandbox(Settings())
    assert isinstance(sandbox, DockerSandbox) and sandbox.fallback is None
    _down(sandbox, monkeypatch)

    result = sandbox.run("echo ran > made.txt", cwd=tmp_path)

    assert result.exit_code == DOCKER_UNAVAILABLE_EXIT
    assert result.stderr == DOCKER_UNAVAILABLE
    assert not (tmp_path / "made.txt").exists()


def test_the_message_says_what_happened_and_both_ways_out() -> None:
    assert DOCKER_UNAVAILABLE.startswith("error:")
    assert "nothing ran on this computer" in DOCKER_UNAVAILABLE
    assert "Start Docker" in DOCKER_UNAVAILABLE
    assert "CHIMERA_SANDBOX=local" in DOCKER_UNAVAILABLE


def test_a_fallback_the_caller_gave_is_still_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _down(DockerSandbox(fallback=LocalSandbox()), monkeypatch)
    result = sandbox.run("echo ran", cwd=tmp_path)
    assert result.exit_code == 0 and "ran" in result.stdout
    assert docker_refusal(sandbox) is None


def test_a_missing_daemon_is_not_reported_as_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    # The host-exec gate and the posture screen read this: "isolated" must mean a container exists.
    assert _down(DockerSandbox(), monkeypatch).is_isolated() is False


def test_run_shell_refuses_before_asking_the_person(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _down(DockerSandbox(), monkeypatch)
    out = RunShellTool(tmp_path, sandbox, confirm=_never_asked).run(command="echo ran > made.txt")
    assert out == DOCKER_UNAVAILABLE
    assert not (tmp_path / "made.txt").exists()


def test_execute_code_refuses_before_asking_the_person(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _down(DockerSandbox(), monkeypatch)
    out = ExecuteCodeTool(workspace=tmp_path, sandbox=sandbox, confirm=_never_asked).run(
        code="open('made.txt', 'w').write('ran')"
    )
    assert out == DOCKER_UNAVAILABLE
    assert not (tmp_path / "made.txt").exists()
    assert not list(tmp_path.glob(".chimera_exec_*.py"))


def test_the_verifier_abstains_instead_of_failing_the_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _down(DockerSandbox(), monkeypatch)
    verdict = CommandVerifier("exit 1", tmp_path, sandbox=sandbox, source="user").verify()
    assert verdict.abstained is True
    assert verdict.passed is True  # no verdict: the other gates decide, nothing is reverted for it
    assert "Docker is not reachable" in verdict.output


def test_a_no_is_asked_again_after_the_recheck_window(monkeypatch: pytest.MonkeyPatch) -> None:
    # A refusal that cached "no" forever would keep refusing after the owner starts Docker.
    import chimera.sandbox.docker as docker_mod

    probes: list[Any] = []

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        probes.append(argv)
        return type("P", (), {"returncode": 1 if len(probes) == 1 else 0})()

    monkeypatch.setattr(docker_mod.subprocess, "run", fake_run)
    clock = [1000.0]
    monkeypatch.setattr(docker_mod.time, "monotonic", lambda: clock[0])
    sandbox = DockerSandbox()

    assert sandbox.available() is False
    assert sandbox.available() is False  # inside the window: no second probe
    assert len(probes) == 1
    clock[0] += RECHECK_SECONDS + 1
    assert sandbox.available() is True
    assert len(probes) == 2
    clock[0] += 10 * RECHECK_SECONDS
    assert sandbox.available() is True
    assert len(probes) == 2  # a "yes" is kept
