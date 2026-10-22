"""Behaviour of duplicate detection: what counts as the same shape, and what does not.

The detector's whole job is to see through a rename, because that is how a model duplicates
- it generates each site without looking at the other, and the names come out different.
The tests that matter are therefore the ones where text comparison would fail and the ones
where structural comparison over-fires.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import clones

LOOP_AND_GUARD = """
    total = 0
    for item in {arg}:
        total += item
    if total > 10:
        return total
    return 0
"""


def module(**functions: tuple[str, str]) -> dict[str, tuple[ast.Module, str]]:
    """One synthetic module, from name -> (parameter list, body)."""
    source = "\n\n".join(f"def {name}({args}):{body}" for name, (args, body) in functions.items())
    return {"m": (ast.parse(source), "m.py")}


def two_renamed_copies() -> dict[str, tuple[ast.Module, str]]:
    return module(
        calc_range=("a", LOOP_AND_GUARD.format(arg="a")),
        compute_span=("x", LOOP_AND_GUARD.format(arg="x")),
    )


# --- seeing through a rename ------------------------------------------------------------------


def test_the_same_function_under_two_names_is_one_clone() -> None:
    found = clones.find(two_renamed_copies())
    assert [c.kind for c in found] == [clones.FUNCTION]
    assert {s.qualified for s in found[0].sites} == {"m.calc_range", "m.compute_span"}


def test_different_logic_is_not_a_clone() -> None:
    found = clones.find(
        module(
            calc=("a", LOOP_AND_GUARD.format(arg="a")),
            other=("p", "\n    q = p * 2\n    r = q + 1\n    s = r - 3\n    return s\n"),
        )
    )
    assert found == []


def test_a_shared_docstring_does_not_make_two_functions_clones() -> None:
    """Prose is not structure. Two functions explaining themselves the same way are not copies."""
    body = '\n    """Same sentence."""\n    {}\n'
    found = clones.find(
        module(
            one=("a", body.format("return a + 1")),
            two=("b", body.format("raise ValueError(b)")),
        )
    )
    assert found == []


def test_a_short_function_is_not_a_clone_of_another_short_function() -> None:
    """Below the floor everything matches everything; that is what a two-line function is."""
    found = clones.find(
        module(first=("self", "\n    return self._x\n"), second=("self", "\n    return self._y\n"))
    )
    assert found == []


# --- where structural comparison over-fires ----------------------------------------------------


def test_two_unrelated_records_are_not_clones() -> None:
    """Finding, EntryPoint and Waiver hold the same field count and hashed identically.

    For a declaration the shape *is* the field count, so structural identity says nothing.
    """
    source = (
        "class Finding:\n"
        '    """One."""\n\n'
        "    rule: int\n    name: str\n    line: int\n    verdict: str\n    message: str\n\n\n"
        "class EntryPoint:\n"
        '    """Another."""\n\n'
        "    rule: int\n    name: str\n    line: int\n    verdict: str\n    message: str\n"
    )
    assert clones.find({"m": (ast.parse(source), "m.py")}) == []


def test_a_class_with_real_logic_can_still_be_a_clone() -> None:
    body = (
        "class {name}:\n"
        '    """Doc."""\n\n'
        "    def run(self, data):\n"
        "        total = 0\n"
        "        for row in data:\n"
        "            total += row\n"
        "        if total > 3:\n"
        "            return total\n"
        "        return 0\n"
    )
    source = body.format(name="Alpha") + "\n\n" + body.format(name="Beta")
    kinds = {c.kind for c in clones.find({"m": (ast.parse(source), "m.py")})}
    assert clones.CLASS in kinds


# --- the rate ----------------------------------------------------------------------------------


def test_the_rate_is_a_ratio_not_a_count() -> None:
    """A count rises with repository size; splitting code cannot improve a ratio."""
    assert clones.duplication_rate(two_renamed_copies()) == 0.5


def test_a_repository_with_no_duplicates_scores_zero() -> None:
    assert clones.duplication_rate(module(only=("a", LOOP_AND_GUARD.format(arg="a")))) == 0.0


def test_an_empty_repository_scores_zero_rather_than_dividing_by_nothing() -> None:
    assert clones.duplication_rate({}) == 0.0


# --- the verdict, which only reachability can give ---------------------------------------------


def _clone() -> clones.Clone:
    return clones.find(two_renamed_copies())[0]


def test_copies_in_independent_features_are_the_complaint() -> None:
    where = clones.verdict(
        _clone(),
        {"a": frozenset({"m.calc_range"}), "b": frozenset({"m.compute_span"})},
        frozenset(),
    )
    assert where == clones.ACROSS_FEATURES


def test_copies_inside_one_feature_are_a_note() -> None:
    """Merging things that change for different reasons costs more coupling than it saves."""
    where = clones.verdict(
        _clone(), {"a": frozenset({"m.calc_range", "m.compute_span"})}, frozenset()
    )
    assert where == clones.WITHIN_FEATURE


def test_a_copy_nothing_reaches_is_a_deletion_not_a_refactor() -> None:
    where = clones.verdict(
        _clone(), {"a": frozenset({"m.calc_range"})}, frozenset({"m.compute_span"})
    )
    assert where == clones.WITH_DEAD_COPY
