"""Lightweight, structured logging/tracing for Chimera.

A thin wrapper over the stdlib ``logging`` with a Rich handler for readable output.
This is the seam where richer tracing (OpenTelemetry spans, trajectory logging)
will plug in later — call sites only ever touch :func:`get_logger`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

_CONFIGURED = False


def configure_logging(level: str = "INFO") -> None:
    """Install the Rich handler once. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        logging.getLogger("chimera").setLevel(level.upper())
        return

    handler = RichHandler(rich_tracebacks=True, show_path=False, markup=True)
    handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))

    root = logging.getLogger("chimera")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    root.propagate = False
    _CONFIGURED = True

    # Initialise optional OpenTelemetry once logging is up (no-op unless enabled + the [otel] extra is
    # installed). Local import breaks the telemetry<->obs cycle; guarded so a failure never blocks logs.
    try:
        from chimera.obs import configure_otel

        configure_otel()
    except Exception:  # noqa: BLE001 — observability must never break logging/startup
        pass


#: The file :func:`attach_file_log` writes, once attached; None before that and in a CLI run.
_FILE_LOG: Path | None = None

#: One megabyte per file and three old ones kept: warnings and errors only, so this is weeks of
#: failures, and a log that can fill a disk is a second incident.
_FILE_LOG_BYTES = 1_000_000
_FILE_LOG_BACKUPS = 3


class _Redacting(logging.Filter):
    """Masks secrets in a record before it reaches the file (`chimera/core/redact.py`).

    A failure's message often quotes a provider's answer, and a traceback can quote a request. The
    console shows a record and forgets it; this file stays on disk for weeks.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        from chimera.core.redact import redact

        try:
            record.msg = redact(record.getMessage())
            record.args = None
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = redact(record.exc_text)
        except Exception:  # noqa: BLE001 — a record that cannot be masked is not written at all
            return False
        return True


def attach_file_log(path: Path) -> Path | None:
    """Also write warnings and errors to ``path``, rotated and with secrets masked. Idempotent.

    The desktop app's backend logged only to its console, which nobody sees: the app starts it as a
    child process. A turn that failed for a reason no sentence names left nothing anywhere (plan M5,
    observed 2026-10-09/10: "the coding turn failed" with no cause, three times in one day). Returns
    the path, or None when the folder cannot be written, in which case nothing changes.
    """
    global _FILE_LOG
    from logging.handlers import RotatingFileHandler

    get_logger("telemetry")  # configured at the settings' level first, as every other logger is
    root = logging.getLogger("chimera")
    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == path.resolve():
            return _FILE_LOG
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=_FILE_LOG_BYTES, backupCount=_FILE_LOG_BACKUPS, encoding="utf-8"
        )
    except OSError:
        return None
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(_Redacting())
    root.addHandler(handler)
    _FILE_LOG = path.resolve()
    return _FILE_LOG


def file_log_path() -> Path | None:
    """Where warnings and errors are written to disk in this process, if anywhere."""
    return _FILE_LOG


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child logger (``chimera.<name>``).

    Logging is configured lazily on first use using the level from settings.
    """
    if not _CONFIGURED:
        # Local import avoids a config<->telemetry import cycle at module load.
        from chimera.config import get_settings

        configure_logging(get_settings().log_level)
    return logging.getLogger(f"chimera.{name}")
