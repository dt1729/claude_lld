"""Logging configuration for the gate scripts.

One rule dominates the design: **nothing may write to stdout**. The PreToolUse hook's
stdout carries the permission decision as JSON, and a stray log line there breaks the
protocol in a way that is hard to trace from the session. Handlers go to stderr and to a
file; stdout is never touched.

Configuration happens at the composition root (each script's ``main``), never at import, so
importing a module has no side effect and a caller can choose its own level.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Final

DEFAULT_LEVEL: Final = "INFO"
DEFAULT_LOG_DIR: Final = ".lld"
DEFAULT_LOG_NAME: Final = "gate.log"

_FORMAT: Final = "%(asctime)s %(levelname)-7s %(name)s %(message)s"
_DATE_FORMAT: Final = "%H:%M:%S"


def resolve_level(requested: str | None) -> int:
    """Map a level name to its numeric value, falling back to INFO on anything unknown.

    An unusable level must not stop the gate: a misspelled environment variable should
    degrade to the default, not disable the tool that enforces the standards.
    """
    name = (requested or DEFAULT_LEVEL).strip().upper()
    resolved = logging.getLevelNamesMapping().get(name)
    return resolved if resolved is not None else logging.INFO


def log_path(project_dir: Path, override: str | None = None) -> Path:
    """Where the log lands: an explicit override, else .lld/gate.log under the project."""
    if override:
        return Path(override)
    return project_dir / DEFAULT_LOG_DIR / DEFAULT_LOG_NAME


def configure(
    *,
    level: str | None = None,
    log_file: Path | None = None,
    stream: bool = True,
) -> logging.Logger:
    """Configure the ``lld`` logger tree and return its root.

    Calling this twice replaces the handlers rather than adding a second set, so a script
    invoked repeatedly in one process does not emit each line N times.

    A log file that cannot be opened is skipped with a warning on stderr: observability is
    worth having, but never at the cost of the gate refusing to run.
    """
    logger = logging.getLogger("lld")
    logger.setLevel(resolve_level(level))
    logger.propagate = False

    for existing in list(logger.handlers):
        logger.removeHandler(existing)
        existing.close()

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    if stream:
        # stderr, never stdout: stdout is the hook's JSON channel.
        handler: logging.Handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
        except OSError as exc:
            print(f"lld: cannot open log file {log_file}: {exc}", file=sys.stderr)
        else:
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger
