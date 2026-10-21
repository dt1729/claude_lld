"""Behaviour of the derived half of a contract: what it generates, and what it preserves."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from derive import (
    CLOSE,
    OPEN,
    ModuleFacts,
    apply,
    dotted_name,
    facts_for,
    import_graph,
    render,
    stale,
)

MODULE = Path("src/shapes/square.py")

SQUARE = '''"""A square."""

from dataclasses import dataclass

from shapes.units import Metres


class InvalidSideError(ValueError):
    """Not strictly positive."""


@dataclass(frozen=True, slots=True)
class Square:
    side_m: Metres

    def __post_init__(self) -> None:
        if self.side_m <= 0:
            raise InvalidSideError("side must be > 0")

    @property
    def area_m2(self) -> float:
        return self.side_m**2
'''

GRAPH = {"shapes.square": {"shapes.units"}, "shapes.report": {"shapes.square"}}

CONTRACT = """# Contract: shapes.square

**Status:** accepted

## Responsibility

Represent a square with a validated side length.

## Interface

The side is metres and always above zero, so no caller revalidates it.

## Seam

None. A value type over one number.

## Dependencies

The report path is the only caller that needs the area.

## Errors

A bad side is the caller's mistake, not a system failure.

## Observability

No logging.

## Tests

- area of a unit square is 1
- a zero side is refused
- a negative side is refused

## Deletion test

Every caller would revalidate the side, and one would forget.
"""


def facts() -> ModuleFacts:
    return facts_for(SQUARE, MODULE, GRAPH)


# --- reading the facts ---------------------------------------------------------------------


def test_the_dotted_name_is_what_a_caller_imports() -> None:
    assert dotted_name(MODULE) == "shapes.square"


def test_public_classes_and_members_are_signatures() -> None:
    assert "Square(side_m: Metres)" in facts().signatures
    assert "  .area_m2 -> float" in facts().signatures


def test_private_members_are_not_part_of_the_interface() -> None:
    assert not any("__post_init__" in s for s in facts().signatures)


def test_imports_cover_both_internal_and_external() -> None:
    assert facts().imports == ["shapes.units", "dataclasses"]


def test_importers_come_from_the_graph_not_the_file() -> None:
    """No single file can answer this, which is why ten contracts got it wrong."""
    assert facts().importers == ["shapes.report"]


def test_every_raised_type_is_collected() -> None:
    assert facts().raises == ["InvalidSideError"]


def test_a_module_that_raises_nothing_says_so() -> None:
    plain = facts_for("def run() -> int:\n    return 1\n", MODULE, {})
    assert "No error modes." in render("Errors", plain)


# --- rendering -------------------------------------------------------------------------------


def test_a_block_carries_its_markers() -> None:
    block = render("Interface", facts())
    assert block.startswith(OPEN)
    assert block.endswith(CLOSE)


def test_every_block_states_what_it_cannot_see() -> None:
    """A block that silently under-reports is the same lie in a smaller font."""
    for section in ("Interface", "Dependencies", "Errors"):
        assert "not visible here" in render(section, facts())


def test_a_section_that_is_not_derived_is_refused() -> None:
    with pytest.raises(ValueError, match="not derived"):
        render("Seam", facts())


# --- applying to a contract --------------------------------------------------------------------


def test_the_authors_prose_survives() -> None:
    out = apply(CONTRACT, facts())
    assert "The report path is the only caller that needs the area." in out
    assert "Every caller would revalidate the side, and one would forget." in out


def test_the_facts_land_in_their_sections() -> None:
    out = apply(CONTRACT, facts())
    assert "Square(side_m: Metres)" in out
    assert "**Imported by:** shapes.report" in out
    assert "`InvalidSideError`" in out


def test_applying_twice_changes_nothing() -> None:
    """Idempotence: a second run must not stack blocks or drift the file."""
    once = apply(CONTRACT, facts())
    assert apply(once, facts()) == once


def test_a_contract_without_those_headings_is_left_alone() -> None:
    minimal = "# Contract: x\n\n**Status:** draft\n\n## Seam\n\nNone.\n"
    assert apply(minimal, facts()) == minimal


# --- staleness ------------------------------------------------------------------------------


def test_a_contract_with_no_blocks_yet_is_reported() -> None:
    sections = {f.name for f in stale(CONTRACT, facts())}
    assert sections == {"Interface", "Dependencies", "Errors"}


def test_a_freshly_applied_contract_is_current() -> None:
    assert stale(apply(CONTRACT, facts()), facts()) == []


def test_a_changed_signature_makes_the_block_stale() -> None:
    applied = apply(CONTRACT, facts())
    moved = facts_for(SQUARE.replace("side_m: Metres", "side: float"), MODULE, GRAPH)
    names = {f.name for f in stale(applied, moved)}
    assert "Interface" in names


SCALE = """

def scale(square: Square, by: float) -> Square:
    if by <= 0:
        raise InvalidScaleError(by)
    return square
"""


def test_a_new_raise_makes_the_block_stale() -> None:
    applied = apply(CONTRACT, facts())
    widened = facts_for(SQUARE + SCALE, MODULE, GRAPH)
    assert "Errors" in {f.name for f in stale(applied, widened)}


def test_a_new_importer_makes_the_block_stale() -> None:
    """The drift that lands in a file nobody edited."""
    applied = apply(CONTRACT, facts())
    wider = facts_for(SQUARE, MODULE, {**GRAPH, "shapes.cli": {"shapes.square"}})
    assert "Dependencies" in {f.name for f in stale(applied, wider)}


# --- the graph --------------------------------------------------------------------------------


def test_the_graph_skips_tests_and_package_inits(tmp_path: Path) -> None:
    src = tmp_path / "src" / "shapes"
    (src / "tests").mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "square.py").write_text("from shapes.units import Metres\n", encoding="utf-8")
    (src / "units.py").write_text("Metres = float\n", encoding="utf-8")
    (src / "tests" / "test_square.py").write_text(
        "from shapes.square import Square\n", encoding="utf-8"
    )

    graph = import_graph(tmp_path / "src", "shapes")
    assert graph == {"shapes.square": {"shapes.units"}, "shapes.units": set()}


def test_an_unparseable_module_does_not_break_the_graph(tmp_path: Path) -> None:
    src = tmp_path / "src" / "shapes"
    src.mkdir(parents=True)
    (src / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (src / "good.py").write_text("x = 1\n", encoding="utf-8")
    assert import_graph(tmp_path / "src", "shapes") == {"shapes.good": set()}
