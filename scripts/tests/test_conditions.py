"""Behaviour of the projection from a contract's Preconditions table into the code.

The claim under test is the one in docs/proposals/001a: the verdict decides which condition
is correct, and emitting the same annotation for all three would be worse than emitting
none. A ``pre:`` on a reject row tells CrossHair to skip the very inputs the guard exists
for, which hides the bug the guard was written to catch.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conditions import (
    STALE_CONDITIONS,
    existing_block,
    expression_for,
    project,
    render_conditions,
    stale,
)
from contracts import Precondition, parse_preconditions

CONTRACT = """## Preconditions

| Parameter | Must satisfy | On violation |
| --- | --- | --- |
| `hfov_deg` | `0 < hfov_deg < 180` | **reject** - `InvalidFovError` naming the value |
| `width` | `> 0` | **propagate** - the caller read it off the sensor |
| `rate` | `> 0` | **clamp** to the default, log at WARNING |
| `source` | open, not already consumed | **propagate** - the caller owns it |
"""

ROWS = parse_preconditions(CONTRACT)
PATH = "docs/contracts/trackscope.data.md"

MODULE = '''"""A module."""


def intrinsics_from_fov(width: int, hfov_deg: float) -> dict:
    """Build a pinhole camera model.

    A caller passes the sensor size it actually captured at.
    """
    return {"fx": width / hfov_deg}


def unrelated(name: str) -> str:
    """Takes nothing the table covers."""
    return name
'''


def row(parameter: str, must: str, verdict: str, detail: str = "") -> Precondition:
    return Precondition(parameter, must, verdict, detail or verdict)


# --- the verdict decides the annotation -------------------------------------------------------


def test_reject_emits_raises_not_pre() -> None:
    """A pre: here would tell CrossHair to skip the inputs the guard exists for."""
    assert render_conditions([ROWS[0]], PATH)[1:-1] == ["raises: InvalidFovError"]


def test_propagate_emits_pre() -> None:
    """The one case where a precondition is literally true: undefined outside the range."""
    assert render_conditions([ROWS[1]], PATH)[1:-1] == ["pre: width > 0"]


def test_clamp_emits_nothing() -> None:
    """Total, defined everywhere, raises nothing. There is no condition to state."""
    assert render_conditions([ROWS[2]], PATH) == []


def test_the_exception_name_comes_from_the_verdict_cell() -> None:
    """`reject - InvalidFovError naming the value` names the type; the condition does not."""
    assert render_conditions([ROWS[0]], PATH)[1] == "raises: InvalidFovError"


def test_a_reject_naming_no_exception_falls_back_to_value_error() -> None:
    assert render_conditions([row("x", "> 0", "reject")], PATH)[1] == "raises: ValueError"


# --- what cannot be projected -----------------------------------------------------------------


def test_a_shorthand_condition_gains_its_parameter() -> None:
    assert expression_for(row("width", "> 0", "propagate")) == "width > 0"


def test_prose_is_not_projectable() -> None:
    """An unparseable pre: hands CrossHair a syntax error instead of a claim."""
    assert expression_for(ROWS[3]) is None


def test_a_prose_row_contributes_no_line() -> None:
    assert render_conditions([ROWS[3]], PATH) == []


def test_a_table_producing_nothing_produces_no_block() -> None:
    """A block saying nothing is noise a reader has to scroll past."""
    assert render_conditions([ROWS[2], ROWS[3]], PATH) == []


# --- writing it into a module -----------------------------------------------------------------


def test_the_block_lands_in_the_docstring() -> None:
    out = project(MODULE, ROWS, PATH)
    assert "    raises: InvalidFovError\n" in out
    assert "    pre: width > 0\n" in out


def test_the_authors_prose_survives_untouched() -> None:
    out = project(MODULE, ROWS, PATH)
    assert "    A caller passes the sensor size it actually captured at.\n" in out


def test_indentation_is_not_shifted() -> None:
    """Rendering from the parsed string re-indents the body a little further on each run."""
    out = project(MODULE, ROWS, PATH)
    assert '    """Build a pinhole camera model.\n' in out
    assert "        A caller passes" not in out


def test_projecting_twice_changes_nothing() -> None:
    once = project(MODULE, ROWS, PATH)
    assert project(once, ROWS, PATH) == once


def test_a_function_taking_none_of_those_parameters_is_left_alone() -> None:
    """A contract covers a module; without this every function inherits every row."""
    out = project(MODULE, ROWS, PATH)
    assert out.count("end derived") == 1
    assert '"""Takes nothing the table covers."""' in out


def test_a_function_with_no_docstring_is_left_alone() -> None:
    """This generates a contract's executable half, not a docstring nobody wrote."""
    bare = "def intrinsics_from_fov(width: int) -> int:\n    return width\n"
    assert project(bare, ROWS, PATH) == bare


def test_a_one_line_docstring_becomes_a_block() -> None:
    source = 'def intrinsics_from_fov(width: int) -> int:\n    """Short."""\n    return width\n'
    out = project(source, ROWS, PATH)
    assert '    """Short.\n' in out
    assert "    pre: width > 0\n" in out


def test_a_module_that_does_not_parse_is_returned_unchanged() -> None:
    broken = "def oops(:\n"
    assert project(broken, ROWS, PATH) == broken


# --- drift ------------------------------------------------------------------------------------


def test_a_fresh_projection_is_current() -> None:
    assert stale(project(MODULE, ROWS, PATH), ROWS, PATH) == []


def test_a_module_with_no_block_is_a_migration_state_not_a_defect() -> None:
    assert stale(MODULE, ROWS, PATH) == []


def test_an_edited_block_is_reported() -> None:
    edited = project(MODULE, ROWS, PATH).replace("pre: width > 0", "pre: width > 1")
    found = stale(edited, ROWS, PATH)
    assert [f.rule for f in found] == [STALE_CONDITIONS]
    assert found[0].name == "intrinsics_from_fov"
    assert "Regenerate rather than edit" in found[0].message


def test_a_contract_change_makes_the_block_stale() -> None:
    """The drift that lands in a file nobody edited."""
    projected = project(MODULE, ROWS, PATH)
    widened = [row("width", "> 1", "propagate"), ROWS[0]]
    assert [f.name for f in stale(projected, widened, PATH)] == ["intrinsics_from_fov"]


def test_the_block_is_read_back_out_of_a_docstring() -> None:
    docstring = "Summary.\n\n    .. derived from x.md - regenerate, do not edit\n    pre: a > 0\n    .. end derived\n    "
    assert existing_block(docstring) == ["pre: a > 0"]


def test_an_unclosed_marker_reads_as_no_block() -> None:
    """Half a block is not a block; guessing where it ends would eat the docstring."""
    assert existing_block("Summary.\n\n    .. derived from x.md - regenerate, do not edit\n") == []
