"""Behaviour of the AST obligation reader and the gap detector.

The square from the demo is the fixture, because it is the module these rules were written
against and its shape is the one the plugin tells people to write.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts import Precondition
from detect_gaps import gaps
from findings import BLOCK, JUDGE
from obligations import (
    BOUNDARY,
    PRECONDITION,
    PUBLIC_NAME,
    RAISE,
    boundary_hints,
    obligations,
    precondition_obligations,
    public_constructors,
)

SQUARE = '''"""A square, whose side length cannot be zero or negative."""

from dataclasses import dataclass


class InvalidSideError(ValueError):
    """A side length that is not strictly positive."""


@dataclass(frozen=True, slots=True)
class Square:
    side_m: float

    def __post_init__(self) -> None:
        if self.side_m <= 0:
            raise InvalidSideError("side must be > 0")

    @property
    def area_m2(self) -> float:
        return self.side_m**2
'''

FULL_SUITE = """
import pytest

from shapes.square import InvalidSideError, Square


def test_area_of_a_unit_square_is_one() -> None:
    assert Square(1.0).area_m2 == 1.0


def test_zero_side_is_refused() -> None:
    with pytest.raises(InvalidSideError):
        Square(0.0)
"""


def kinds(source: str) -> list[str]:
    return [o.kind for o in obligations(source)]


def targets(source: str, kind: str) -> list[str]:
    return [o.target for o in obligations(source) if o.kind == kind]


# --- obligations from the source ---------------------------------------------------------


def test_every_public_class_is_an_obligation() -> None:
    assert "Square" in targets(SQUARE, PUBLIC_NAME)


def test_a_public_property_is_its_own_obligation() -> None:
    assert "Square.area_m2" in targets(SQUARE, PUBLIC_NAME)


def test_a_private_method_is_not_an_obligation() -> None:
    """__post_init__ is not reachable by a caller, so no test owes it a name."""
    assert "Square.__post_init__" not in targets(SQUARE, PUBLIC_NAME)


def test_each_raised_exception_is_an_obligation() -> None:
    assert targets(SQUARE, RAISE) == ["InvalidSideError"]


def test_the_guard_on_a_raise_becomes_a_boundary_obligation() -> None:
    assert targets(SQUARE, BOUNDARY) == ["side_m at and just below 0"]


def test_the_same_exception_raised_twice_is_one_obligation() -> None:
    src = """
def run(x: int) -> int:
    if x < 0:
        raise ValueError("negative")
    if x > 10:
        raise ValueError("too big")
    return x
"""
    assert targets(src, RAISE) == ["ValueError"]


def test_a_module_with_nothing_public_owes_nothing() -> None:
    assert obligations("def _helper() -> int:\n    return 1\n") == []


def test_a_raise_with_no_simple_guard_yields_no_boundary() -> None:
    """Inventing a threshold the code does not turn on would put a lie in a test name."""
    src = """
def run(a: int, b: int) -> int:
    if a < b and a > 0:
        raise ValueError("bad")
    return a
"""
    assert BOUNDARY not in kinds(src)


def test_obligations_are_ordered_by_line() -> None:
    lines = [o.line for o in obligations(SQUARE)]
    assert lines == sorted(lines)


def test_unparseable_source_raises_syntaxerror() -> None:
    with pytest.raises(SyntaxError):
        obligations("def broken(:\n")


# --- stubs -------------------------------------------------------------------------------


def test_a_stub_fails_so_it_cannot_pass_unwritten() -> None:
    stub = obligations(SQUARE)[0].as_stub()
    assert "pytest.fail" in stub


def test_a_stub_records_why_the_obligation_exists() -> None:
    stub = next(o for o in obligations(SQUARE) if o.kind == RAISE).as_stub()
    assert "InvalidSideError" in stub


# --- constructors for the sandbox ---------------------------------------------------------


def test_a_dataclass_field_is_a_constructor_parameter() -> None:
    assert public_constructors(SQUARE) == [("InvalidSideError", []), ("Square", ["side_m"])]


def test_an_explicit_init_wins_over_fields() -> None:
    src = """
class Thing:
    count: int

    def __init__(self, name: str, size: int) -> None:
        self.name = name
"""
    assert public_constructors(src) == [("Thing", ["name", "size"])]


# --- gaps ---------------------------------------------------------------------------------


def test_a_complete_suite_leaves_no_blocking_gap() -> None:
    blocking = [f for f in gaps(SQUARE, FULL_SUITE) if f.verdict == BLOCK]
    assert blocking == []


def test_an_unexpected_exception_is_a_blocking_gap() -> None:
    suite = FULL_SUITE.replace(
        "def test_zero_side_is_refused() -> None:\n"
        "    with pytest.raises(InvalidSideError):\n"
        "        Square(0.0)\n",
        "",
    )
    blocking = [f for f in gaps(SQUARE, suite) if f.verdict == BLOCK]
    assert "InvalidSideError" in {f.name for f in blocking}


def test_an_untouched_public_name_is_a_blocking_gap() -> None:
    suite = """
import pytest

from shapes.square import InvalidSideError, Square


def test_zero_side_is_refused() -> None:
    with pytest.raises(InvalidSideError):
        Square(0.0)
"""
    blocking = {f.name for f in gaps(SQUARE, suite) if f.verdict == BLOCK}
    assert "Square.area_m2" in blocking


def test_no_suite_at_all_is_every_obligation_unmet() -> None:
    blocking = [f for f in gaps(SQUARE, "") if f.verdict == BLOCK]
    assert len(blocking) >= 2


def test_a_boundary_is_judgment_because_the_value_used_is_invisible() -> None:
    boundaries = [f for f in gaps(SQUARE, FULL_SUITE) if f.verdict == JUDGE]
    assert boundaries and "side_m" in boundaries[0].name


def test_an_unparseable_suite_does_not_mask_the_gaps() -> None:
    """A broken test file means nothing is covered, not that everything is."""
    blocking = [f for f in gaps(SQUARE, "def broken(:\n") if f.verdict == BLOCK]
    assert blocking != []


# --- obligations that come from the contract, not the code ------------------------------------
#
# Every other kind here reads the syntax tree. These read the Preconditions table, because a
# guard that was never written leaves no trace in the source - which is exactly the gap
# proposal 001 found: every gate green on code with no validation anywhere.


def _row(parameter: str, must: str, verdict: str, detail: str = "") -> Precondition:
    return Precondition(parameter, must, verdict, detail or verdict)


REJECT_FOV = _row("hfov_deg", "0 < hfov_deg < 180", "reject", "reject - InvalidFovError")


def test_a_reject_row_owes_a_rejection_test() -> None:
    owed = precondition_obligations([REJECT_FOV])
    assert [o.suggested_name for o in owed] == ["test_rejects_hfov_deg"]
    assert owed[0].kind == PRECONDITION


def test_a_clamp_row_owes_no_rejection_test() -> None:
    """Clamp substitutes rather than raises; a test asserting an exception would be wrong."""
    assert precondition_obligations([_row("rate", "> 0", "clamp")]) == []


def test_a_propagate_row_owes_no_rejection_test() -> None:
    """The author is stating nothing is checked. A test for that tests the caller."""
    assert precondition_obligations([_row("marks", "ascending t", "propagate")]) == []


def test_the_boundary_values_are_offered_as_hints() -> None:
    """Where off-by-one lives, handed to the author rather than guessed into an assertion."""
    assert boundary_hints("0 < hfov_deg < 180") == ["0", "180"]


def test_a_condition_with_no_numbers_offers_no_hints() -> None:
    assert boundary_hints("ascending t") == []


def test_the_stub_says_what_to_do_rather_than_not_written_yet() -> None:
    owed = precondition_obligations([REJECT_FOV])[0]
    assert "violating 0 < hfov_deg < 180" in owed.instruction
    assert "the boundary values are 0, 180" in owed.instruction
    assert "not written yet" not in owed.as_stub()


def test_the_stub_still_fails_until_someone_writes_it() -> None:
    """The rule the whole scaffolder follows: no generated assertion, ever."""
    assert "pytest.fail(" in precondition_obligations([REJECT_FOV])[0].as_stub()


def test_a_shorthand_condition_reads_as_a_claim() -> None:
    """`rejected unless > 0` is not a sentence; `rejected unless width > 0` is."""
    assert "width > 0" in precondition_obligations([_row("width", "> 0", "reject")])[0].reason


def test_no_generated_line_exceeds_the_shipped_line_length() -> None:
    """A generator whose output fails the linter it installed is incident 004."""
    stub = precondition_obligations([REJECT_FOV])[0].as_stub()
    assert max(len(line) for line in stub.splitlines()) <= 100


def test_the_generated_stub_is_valid_python() -> None:
    """Wrapping a long message into string parts is where a generator breaks its output."""
    tree = ast.parse(precondition_obligations([REJECT_FOV])[0].as_stub())
    assert [f.name for f in tree.body if isinstance(f, ast.FunctionDef)] == [
        "test_rejects_hfov_deg"
    ]


def test_contract_obligations_come_before_the_code_ones() -> None:
    """A row is numbered by table position; the code it describes may not exist yet."""
    source = "def run(hfov_deg: float) -> float:\n    return hfov_deg\n"
    kinds = [o.kind for o in obligations(source, [REJECT_FOV])]
    assert kinds[0] == PRECONDITION
    assert PUBLIC_NAME in kinds


def test_a_module_with_no_contract_rows_is_unchanged() -> None:
    source = "def run(x: int) -> int:\n    return x\n"
    assert obligations(source) == obligations(source, [])
