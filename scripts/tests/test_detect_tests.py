"""Behaviour of the test-quality detector, rules 27 to 36.

Every rule gets a case that must fire and one that must stay silent. The silent ones carry
the weight: a test rule that cries wolf gets the whole tier switched off, and a tier that is
off catches nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detect_tests import detect, is_test_file
from findings import BLOCK, JUDGE

HERE = Path("src/pkg/tests/test_thing.py")


def rules(source: str) -> list[int]:
    return [f.rule for f in detect(source, HERE)]


def verdict_of(source: str, rule: int) -> str:
    return next(f.verdict for f in detect(source, HERE) if f.rule == rule)


# A suite that satisfies every rule, used as the baseline each case perturbs.
GOOD = """
import pytest

from pkg.square import InvalidSideError, Square


def test_area_of_a_unit_square_is_one() -> None:
    assert Square(1.0).area_m2 == 1.0


def test_zero_side_is_refused() -> None:
    with pytest.raises(InvalidSideError):
        Square(0.0)
"""


def test_a_well_formed_suite_is_clean() -> None:
    assert detect(GOOD, HERE) == []


# --- 27: a test that asserts nothing ----------------------------------------------------


def test_test_without_an_assertion_blocks() -> None:
    src = """
def test_it_runs() -> None:
    compute(1)
"""
    assert 27 in rules(src)
    assert verdict_of(src, 27) == BLOCK


def test_a_raises_block_counts_as_an_assertion() -> None:
    src = """
import pytest

def test_zero_is_refused() -> None:
    with pytest.raises(ValueError):
        compute(0)

def test_one_works() -> None:
    assert compute(1) == 1
"""
    assert 27 not in rules(src)


def test_delegating_to_a_check_helper_counts() -> None:
    """A helper carries the assertion; flagging this would punish shared setup."""
    src = """
def test_shape_is_valid() -> None:
    check_invariants(build())

def test_other() -> None:
    assert thing() == 1
"""
    assert 27 not in rules(src)


# --- 28: no failure case anywhere -------------------------------------------------------


def test_suite_of_only_happy_paths_is_judged() -> None:
    src = """
def test_area() -> None:
    assert area(2) == 4

def test_perimeter() -> None:
    assert perimeter(2) == 8

def test_diagonal() -> None:
    assert diagonal(2) == 3

def test_scaled() -> None:
    assert scaled(2) == 4

def test_rounded() -> None:
    assert rounded(2) == 2
"""
    assert verdict_of(src, 28) == JUDGE


def test_a_small_suite_is_not_judged_for_lacking_one() -> None:
    """Below the threshold the absence says nothing about the module."""
    src = """
def test_area() -> None:
    assert area(2) == 4
"""
    assert 28 not in rules(src)


def test_one_failure_case_satisfies_the_rule() -> None:
    assert 28 not in rules(GOOD)


def test_a_module_with_no_tests_is_not_flagged() -> None:
    assert 28 not in rules("def helper() -> int:\n    return 1\n")


# --- 29: weak substring assertion -------------------------------------------------------


def test_single_character_substring_assertion_is_judged() -> None:
    """The exact defect found in this plugin's own first module."""
    src = """
import pytest

def test_mismatch_names_the_index() -> None:
    with pytest.raises(ValueError) as caught:
        run()
    assert "1" in str(caught.value)
"""
    assert verdict_of(src, 29) == JUDGE


def test_a_substantial_substring_is_clean() -> None:
    src = """
import pytest

def test_mismatch_names_the_currency() -> None:
    with pytest.raises(ValueError) as caught:
        run()
    assert "expected USD" in str(caught.value)
"""
    assert 29 not in rules(src)


# --- 30: sleep ---------------------------------------------------------------------------


def test_sleep_in_a_test_blocks() -> None:
    src = """
import time
import pytest

def test_eventually() -> None:
    start()
    time.sleep(2)
    assert done()

def test_bad_input() -> None:
    with pytest.raises(ValueError):
        start(None)
"""
    assert 30 in rules(src)


def test_no_sleep_is_clean() -> None:
    assert 30 not in rules(GOOD)


# --- 31: deep imports --------------------------------------------------------------------


def test_import_from_a_private_subpackage_blocks() -> None:
    src = """
import pytest
from pkg.lib.nms import suppress

def test_suppression() -> None:
    assert suppress([]) == []

def test_bad() -> None:
    with pytest.raises(ValueError):
        suppress(None)
"""
    assert 31 in rules(src)


def test_import_from_a_root_module_is_clean() -> None:
    assert 31 not in rules(GOOD)


# --- 32, 33: mocks -----------------------------------------------------------------------


def test_more_mocks_than_assertions_is_judged() -> None:
    src = """
import pytest
from unittest.mock import Mock

def test_pipeline() -> None:
    a, b, c = Mock(), Mock(), Mock()
    assert run(a, b, c) is not None

def test_bad() -> None:
    with pytest.raises(ValueError):
        run(None, None, None)
"""
    assert verdict_of(src, 32) == JUDGE


def test_one_mock_with_assertions_is_clean() -> None:
    src = """
import pytest
from unittest.mock import Mock

def test_pipeline() -> None:
    source = Mock()
    assert run(source) == 1
    assert source is not None

def test_bad() -> None:
    with pytest.raises(ValueError):
        run(None)
"""
    assert 32 not in rules(src)


def test_asserting_a_call_happened_is_judged() -> None:
    src = """
import pytest

def test_saves() -> None:
    store = make_store()
    run(store)
    store.save.assert_called_once()

def test_bad() -> None:
    with pytest.raises(ValueError):
        run(None)
"""
    assert verdict_of(src, 33) == JUDGE


# --- 36: name joins two behaviours -------------------------------------------------------


def test_name_with_and_blocks() -> None:
    src = """
import pytest

def test_validates_and_saves() -> None:
    assert run() == 1

def test_bad() -> None:
    with pytest.raises(ValueError):
        run(None)
"""
    assert verdict_of(src, 36) == JUDGE


def test_a_name_containing_the_word_android_is_not_flagged() -> None:
    """The rule matches the separated word, not the letters."""
    src = """
import pytest

def test_android_build_is_valid() -> None:
    assert run() == 1

def test_bad() -> None:
    with pytest.raises(ValueError):
        run(None)
"""
    assert 36 not in rules(src)


# --- scope and failure modes --------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "src/pkg/tests/test_thing.py",
        "tests/test_thing.py",
        "src/pkg/thing_test.py",
    ],
)
def test_test_files_are_in_scope(path: str) -> None:
    assert is_test_file(Path(path))


@pytest.mark.parametrize("path", ["src/pkg/thing.py", "docs/notes.md", "src/pkg/testing.py"])
def test_other_files_are_not(path: str) -> None:
    assert not is_test_file(Path(path))


def test_unparseable_source_raises_syntaxerror() -> None:
    with pytest.raises(SyntaxError):
        detect("def broken(:\n", HERE)


def test_findings_are_ordered_by_line() -> None:
    src = """
import time

def test_one() -> None:
    compute(1)

def test_two() -> None:
    time.sleep(1)
    assert compute(2) == 2
"""
    lines = [f.line for f in detect(src, HERE)]
    assert lines == sorted(lines)


# --- dogfood -------------------------------------------------------------------------------


def test_this_repos_own_suite_passes_the_test_rules() -> None:
    """The rules apply to the tests that define them."""
    here = Path(__file__).resolve().parent
    offenders: dict[str, list[tuple[int, int, str]]] = {}
    for path in sorted(here.glob("test_*.py")):
        blocking = [f for f in detect(path.read_text(encoding="utf-8"), path) if f.verdict == BLOCK]
        if blocking:
            offenders[path.name] = [(f.rule, f.line, f.message) for f in blocking]
    assert offenders == {}
