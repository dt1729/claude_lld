"""Behaviour of logging configuration.

The load-bearing test is the one proving nothing reaches stdout: the hook's stdout carries
its permission decision as JSON, and a stray log line there breaks the protocol in a way
that is near-impossible to trace from inside a session.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logsetup import (
    DEFAULT_LOG_DIR,
    DEFAULT_LOG_NAME,
    configure,
    log_path,
    resolve_level,
)

SCRIPTS = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def reset_logger() -> None:
    """Each test configures from a clean tree, since handlers are process-global."""
    logger = logging.getLogger("lld")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


# --- level resolution -------------------------------------------------------------------

@pytest.mark.parametrize(("given", "expected"), [
    ("DEBUG", logging.DEBUG),
    ("info", logging.INFO),
    ("  Warning  ", logging.WARNING),
    ("ERROR", logging.ERROR),
])
def test_known_levels_resolve(given: str, expected: int) -> None:
    assert resolve_level(given) == expected


def test_no_level_given_defaults_to_info() -> None:
    assert resolve_level(None) == logging.INFO


def test_unknown_level_degrades_to_info_rather_than_failing() -> None:
    """A misspelled env var must not disable the tool that enforces the standards."""
    assert resolve_level("VERBOSE") == logging.INFO


# --- handler configuration --------------------------------------------------------------

def test_configure_sets_the_requested_level() -> None:
    assert configure(level="DEBUG").level == logging.DEBUG


def test_configure_twice_does_not_duplicate_handlers() -> None:
    configure()
    first = len(configure().handlers)
    assert len(configure().handlers) == first


def test_file_handler_is_added_and_writes(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "gate.log"
    logger = configure(level="INFO", log_file=target)
    logger.info("a decision was made")
    for handler in logger.handlers:
        handler.flush()
    assert "a decision was made" in target.read_text(encoding="utf-8")


def test_unwritable_log_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    """Observability is worth having, but never at the cost of the gate refusing to run."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    logger = configure(level="INFO", log_file=blocker / "gate.log")
    assert logger.level == logging.INFO


def test_stream_handler_can_be_switched_off() -> None:
    assert configure(stream=False).handlers == []


def test_log_path_defaults_under_the_project() -> None:
    assert log_path(Path("/proj")) == Path("/proj") / DEFAULT_LOG_DIR / DEFAULT_LOG_NAME


def test_log_path_honours_an_override() -> None:
    assert log_path(Path("/proj"), "/var/log/lld.log") == Path("/var/log/lld.log")


# --- the protocol guarantee ---------------------------------------------------------------

def test_gate_stdout_is_pure_json_even_at_debug_level(tmp_path: Path) -> None:
    """Run the real hook as a subprocess and parse its stdout. Nothing else may be there."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    payload = {
        "tool_name": "Write",
        "cwd": str(tmp_path),
        "tool_input": {
            "file_path": str(tmp_path / "src" / "pkg" / "thing.py"),
            "content": "def run() -> int:\n    return 1\n",
        },
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "require_contract.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "", "SYSTEMROOT": "", "LLD_LOG_LEVEL": "DEBUG"},
    )
    decision = json.loads(result.stdout)
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "lld.gate" in result.stderr


def test_merge_stdout_mode_emits_only_the_document(tmp_path: Path) -> None:
    """--stdout makes stdout the data channel, so logs must move off it."""
    generated = tmp_path / "gen.md"
    generated.write_text("# pkg\n\nBody\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "merge_claude_md.py"),
         str(tmp_path / "CLAUDE.md"), "--generated", str(generated),
         "--stdout", "--log-level", "DEBUG"],
        capture_output=True, text=True, check=False,
    )
    assert result.stdout == "# pkg\n\nBody\n"
