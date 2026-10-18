"""Detection of the logging anti-patterns, entries 19 to 24.

Each rule gets a case that must fire and one that must stay silent. The silent ones are
load-bearing: a logging rule that cries wolf gets the whole gate switched off.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detect_patterns import detect
from findings import BLOCK, JUDGE

LIBRARY = Path("src/pkg/thing.py")
COMPOSITION_ROOT = Path("src/pkg/cli.py")


def rules(source: str, path: Path = LIBRARY) -> list[int]:
    return [f.rule for f in detect(source, path)]


def verdict_of(source: str, rule: int, path: Path = LIBRARY) -> str:
    return next(f.verdict for f in detect(source, path) if f.rule == rule)


# --- 19: print in a package module ------------------------------------------------------


def test_print_in_a_library_module_blocks() -> None:
    assert 19 in rules("def run() -> None:\n    print('done')\n")


def test_print_in_the_composition_root_is_clean() -> None:
    """A CLI writing its actual output to stdout is the exception."""
    assert 19 not in rules("def main() -> None:\n    print('done')\n", COMPOSITION_ROOT)


def test_a_log_call_is_not_a_print() -> None:
    src = "import logging\nlog = logging.getLogger(__name__)\n\ndef run() -> None:\n    log.info('done')\n"
    assert 19 not in rules(src)


# --- 20: configuration below the composition root ---------------------------------------


def test_basicconfig_in_a_library_blocks() -> None:
    src = "import logging\n\ndef setup() -> None:\n    logging.basicConfig(level=logging.INFO)\n"
    assert 20 in rules(src)
    assert verdict_of(src, 20) == BLOCK


def test_addhandler_in_a_library_blocks() -> None:
    src = "import logging\nlog = logging.getLogger(__name__)\n\ndef setup(h: object) -> None:\n    log.addHandler(h)\n"
    assert 20 in rules(src)


def test_basicconfig_in_the_composition_root_is_clean() -> None:
    src = "import logging\n\ndef main() -> None:\n    logging.basicConfig(level=logging.INFO)\n"
    assert 20 not in rules(src, COMPOSITION_ROOT)


def test_merely_emitting_is_clean() -> None:
    src = "import logging\nlog = logging.getLogger(__name__)\n\ndef run() -> None:\n    log.info('x %s', 1)\n"
    assert 20 not in rules(src)


# --- 21: eager formatting ---------------------------------------------------------------


def test_fstring_in_a_log_call_blocks() -> None:
    src = "def run(name: str) -> None:\n    log.info(f'loaded {name}')\n"
    assert 21 in rules(src)
    assert verdict_of(src, 21) == BLOCK


def test_format_call_in_a_log_call_blocks() -> None:
    assert 21 in rules("def run(name: str) -> None:\n    log.info('loaded {}'.format(name))\n")


def test_percent_formatting_in_a_log_call_blocks() -> None:
    assert 21 in rules("def run(name: str) -> None:\n    log.info('loaded %s' % name)\n")


def test_lazy_arguments_are_clean() -> None:
    assert 21 not in rules("def run(name: str) -> None:\n    log.info('loaded %s', name)\n")


def test_an_fstring_outside_a_log_call_is_clean() -> None:
    """The rule is about log calls, not f-strings."""
    assert 21 not in rules("def run(name: str) -> str:\n    return f'loaded {name}'\n")


# --- 22: literal logger name ------------------------------------------------------------


def test_logger_named_by_a_literal_blocks() -> None:
    assert 22 in rules("import logging\nlog = logging.getLogger('mypkg.thing')\n")


def test_logger_named_by_dunder_name_is_clean() -> None:
    assert 22 not in rules("import logging\nlog = logging.getLogger(__name__)\n")


def test_a_deliberate_tree_root_in_the_composition_root_is_clean() -> None:
    assert 22 not in rules("import logging\nlog = logging.getLogger('myapp')\n", COMPOSITION_ROOT)


# --- 23: exception logged without its traceback -----------------------------------------


def test_log_error_in_a_handler_without_traceback_blocks() -> None:
    src = """
def run() -> None:
    try:
        work()
    except ValueError as exc:
        log.error("failed: %s", exc)
        raise
"""
    assert 23 in rules(src)
    assert verdict_of(src, 23) == BLOCK


def test_log_exception_in_a_handler_is_clean() -> None:
    src = """
def run() -> None:
    try:
        work()
    except ValueError:
        log.exception("failed")
        raise
"""
    assert 23 not in rules(src)


def test_exc_info_keyword_is_clean() -> None:
    src = """
def run() -> None:
    try:
        work()
    except ValueError:
        log.error("failed", exc_info=True)
        raise
"""
    assert 23 not in rules(src)


def test_log_error_outside_a_handler_is_clean() -> None:
    """Not every error log is about an exception."""
    assert 23 not in rules(
        "def run(ok: bool) -> None:\n    if not ok:\n        log.error('bad state %s', ok)\n"
    )


# --- 24: caught, logged, swallowed ------------------------------------------------------


def test_handler_that_only_logs_is_judged() -> None:
    src = """
def run() -> None:
    try:
        work()
    except ValueError:
        log.exception("failed")
"""
    assert verdict_of(src, 24) == JUDGE


def test_handler_that_reraises_is_clean() -> None:
    src = """
def run() -> None:
    try:
        work()
    except ValueError:
        log.exception("failed")
        raise
"""
    assert 24 not in rules(src)


def test_handler_that_recovers_explicitly_is_clean() -> None:
    src = """
def run() -> int:
    try:
        return work()
    except ValueError:
        log.exception("failed, using the default")
        return 0
"""
    assert 24 not in rules(src)


def test_handler_that_assigns_a_fallback_is_clean() -> None:
    src = """
def run() -> int:
    try:
        value = work()
    except ValueError:
        log.exception("failed, using the default")
        value = 0
    return value
"""
    assert 24 not in rules(src)


# --- the detector still passes its own rules ---------------------------------------------


def test_the_gate_scripts_are_clean_under_the_logging_rules() -> None:
    """Dogfood: the scripts added logging, and must satisfy the rules they enforce."""
    scripts = Path(__file__).resolve().parents[1]
    for name in ("detect_patterns.py", "contracts.py", "merge_claude_md.py", "logsetup.py"):
        source = (scripts / name).read_text(encoding="utf-8")
        found = [f for f in detect(source, Path(f"src/lld/{name}")) if f.rule in range(19, 25)]
        assert found == [], f"{name}: {[(f.rule, f.line, f.message) for f in found]}"
