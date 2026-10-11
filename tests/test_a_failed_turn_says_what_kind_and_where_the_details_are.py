"""A turn that failed for a reason no provider named says what kind of failure, and where to look.

Plan M5, from the research done inside Chimera Desktop on 2026-10-09/10. Three turns ended with "the
coding turn failed" and nothing else, and the desktop backend wrote no log anywhere: it runs as the
app's child process, and its console is read by nobody. The person could not act on the sentence,
and whoever debugged it had nothing to read.

The rule that kept the sentence generic still holds: no exception text and no stack trace reach the
composer. What is added is the exception's class, a plain sentence for the two common transport
failures, and a rotated log on disk with the traceback, secrets masked.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from chimera import file_log as disk_log
from chimera import telemetry
from chimera.api.code_api import _native_failure


@pytest.fixture
def file_log(tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "logs" / "backend.log"
    yield path
    root = logging.getLogger("chimera")
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            root.removeHandler(handler)
            handler.close()
    disk_log._FILE_LOG = None


def test_without_a_log_the_sentence_names_the_kind_only(file_log: Path) -> None:
    out = _native_failure(RuntimeError("internal detail /home/x/secret_path.py"))
    assert out == "the coding turn failed (RuntimeError)"


def test_a_timeout_and_a_lost_connection_are_said_in_words(file_log: Path) -> None:
    assert _native_failure(TimeoutError("x")) == (
        "the coding turn failed: the model did not answer in time (TimeoutError)"
    )

    class APITimeoutError(Exception):
        pass

    assert "did not answer in time (APITimeoutError)" in _native_failure(APITimeoutError("boom"))
    assert _native_failure(ConnectionResetError("reset")) == (
        "the coding turn failed: the model provider could not be reached (ConnectionResetError)"
    )


def test_with_the_log_attached_the_sentence_says_where_it_is(file_log: Path) -> None:
    assert disk_log.attach_file_log(file_log) == file_log.resolve()
    out = _native_failure(KeyError("k"))
    assert out == f"the coding turn failed (KeyError); the details are in {file_log.resolve()}"


def test_the_log_holds_the_traceback_with_secrets_masked(
    file_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-or-v1-" + "a1b2c3d4" * 6
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    disk_log.attach_file_log(file_log)
    log = telemetry.get_logger("api.code")
    try:
        raise RuntimeError(f"provider said no for key {secret}")
    except RuntimeError as exc:
        log.warning("code turn failed: %s", exc, exc_info=True)

    written = file_log.read_text(encoding="utf-8")
    assert "code turn failed" in written
    assert "Traceback (most recent call last)" in written
    assert secret not in written


def test_only_warnings_and_errors_are_written(file_log: Path) -> None:
    disk_log.attach_file_log(file_log)
    log = telemetry.get_logger("api.code")
    log.info("an ordinary step")
    log.warning("something went wrong")
    written = file_log.read_text(encoding="utf-8")
    assert "something went wrong" in written
    assert "an ordinary step" not in written


def test_attaching_twice_adds_one_handler(file_log: Path) -> None:
    disk_log.attach_file_log(file_log)
    disk_log.attach_file_log(file_log)
    handlers = [
        h for h in logging.getLogger("chimera").handlers if isinstance(h, RotatingFileHandler)
    ]
    assert len(handlers) == 1


def test_a_folder_that_cannot_be_written_changes_nothing(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")
    assert disk_log.attach_file_log(blocker / "backend.log") is None
    assert disk_log.file_log_path() is None
