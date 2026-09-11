"""Central logging setup: console sink + optional file sink + secret redaction."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from app.config import Settings

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Patterns that must never reach logs
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9\-_]{8,}")
_BEARER_PATTERN = re.compile(r"Bearer [A-Za-z0-9\-_.~+/]+=*")

_REDACTED = "[REDACTED]"


class _SecretFilter(logging.Filter):
    """Scrub API keys and Bearer tokens from all log records."""

    def __init__(self, extra_secrets: list[str] | None = None) -> None:
        super().__init__()
        self._extra: list[str] = [s for s in (extra_secrets or []) if s]

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.msg = self._scrub(str(record.msg))
        record.args = self._scrub_args(record.args)
        return True

    def _scrub(self, text: str) -> str:
        text = _SK_PATTERN.sub(_REDACTED, text)
        text = _BEARER_PATTERN.sub(f"Bearer {_REDACTED}", text)
        for secret in self._extra:
            if secret:
                text = text.replace(secret, _REDACTED)
        return text

    def _scrub_args(self, args: object) -> object:
        if args is None:
            return args
        if isinstance(args, tuple):
            return tuple(self._scrub(str(a)) if isinstance(a, str) else a for a in args)
        if isinstance(args, dict):
            return {k: self._scrub(str(v)) if isinstance(v, str) else v for k, v in args.items()}
        return args


def setup_logging(settings: Settings) -> None:
    """Configure root logging once; safe to call again (replaces handlers)."""
    extra_secrets = [
        settings.upstream_api_key,
        settings.memory_ai_api_key,
    ]
    secret_filter = _SecretFilter(extra_secrets=extra_secrets)

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_FORMAT))
    console.addFilter(secret_filter)
    root.addHandler(console)

    file_handler: logging.Handler | None = None
    if settings.log_file:
        path = Path(settings.log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_FORMAT))
        file_handler.addFilter(secret_filter)
        root.addHandler(file_handler)

    # Trace payloads go only to the log file (fallback: console) — never
    # both, so the chat terminal stays clean.
    trace = logging.getLogger("gateway.trace")
    trace.setLevel(settings.log_level.upper())
    trace.handlers.clear()
    trace.propagate = False
    sink = file_handler if file_handler is not None else console
    sink.addFilter(secret_filter)  # belt-and-suspenders on trace sink
    trace.addHandler(sink)

    # Upstream HTTP access lines are noise on the console.
    logging.getLogger("httpx").setLevel(logging.WARNING)
