"""Central logging setup: console sink + optional file sink."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.config import Settings

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(settings: Settings) -> None:
    """Configure root logging once; safe to call again (replaces handlers)."""
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)

    file_handler: logging.Handler | None = None
    if settings.log_file:
        path = Path(settings.log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(file_handler)

    # Trace payloads go only to the log file (fallback: console) — never
    # both, so the chat terminal stays clean.
    trace = logging.getLogger("gateway.trace")
    trace.setLevel(settings.log_level.upper())
    trace.handlers.clear()
    trace.propagate = False
    sink = file_handler if file_handler is not None else console
    trace.addHandler(sink)

    # Upstream HTTP access lines are noise on the console.
    logging.getLogger("httpx").setLevel(logging.WARNING)
