"""Behaviour of the reachability sweep: entry points, the call graph, and the four sets.

Every test here plants a known structure and checks the answer, because a reachability
analysis has no safe failure mode. Reporting live code dead is how a tool that proposes
deletions deletes something that runs, so the cases that matter most are the ones where a
naive call graph gets it wrong: a dispatch table, a type annotation, two modules that both
define ``main``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import callgraph, entrypoints, reach


def parse(**modules: str) -> dict[str, tuple[ast.Module, str]]:
    return {name: (ast.parse(src), f"{name}.py") for name, src in modules.items()}


def entries_for(parsed: dict[str, tuple[ast.Module, str]]) -> list[entrypoints.EntryPoint]:
    found: list[entrypoints.EntryPoint] = []
    for module, (tree, path) in sorted(parsed.items()):
        found += entrypoints.in_module(tree, module, path, set())
    return found


# --- finding the way in -----------------------------------------------------------------------


def test_a_main_guard_is_an_entry_point() -> None:
    parsed = parse(app='def run() -> None:\n    pass\n\n\nif __name__ == "__main__":\n    run()\n')
    kinds = {e.kind for e in entries_for(parsed)}
    assert entrypoints.MAIN_GUARD in kinds


def test_a_framework_decorator_is_an_entry_point() -> None:
    """Nothing in the source calls a route; without this every handler reads as dead."""
    parsed = parse(api='@app.route("/")\ndef index() -> str:\n    return "hi"\n')
    found = entries_for(parsed)
    assert [(e.qualified, e.kind) for e in found] == [("api.index", entrypoints.FRAMEWORK)]


def test_a_test_function_is_marked_as_a_test_not_a_feature() -> None:
    parsed = parse(t="def test_thing() -> None:\n    pass\n")
    assert [e.kind for e in entries_for(parsed)] == [entrypoints.TEST]


def test_a_repository_with_no_way_in_is_a_library() -> None:
    """Every exported name is an entry, so 'dead' is not a meaningful answer there."""
    assert entrypoints.classify([], exported=40) == entrypoints.LIBRARY


def test_a_repository_with_a_main_is_an_application() -> None:
    entry = entrypoints.EntryPoint("app.__main__", entrypoints.MAIN_GUARD, "app.py", 1)
    assert entrypoints.classify([entry], exported=3) == entrypoints.APPLICATION


# --- resolving a call -------------------------------------------------------------------------


def test_a_local_name_wins_over_the_same_name_elsewhere() -> None:
    """Every module here defines main; bare-name matching made all of them reach each other."""
    parsed = parse(
        one="def helper() -> None:\n    pass\n\n\ndef main() -> None:\n    helper()\n",
        two="def helper() -> None:\n    pass\n\n\ndef main() -> None:\n    helper()\n",
    )
    graph = callgraph.build(parsed)
    assert graph.successors("one.main") == {"one.helper"}
    assert graph.successors("two.main") == {"two.helper"}


def test_an_imported_name_resolves_to_what_was_imported() -> None:
    parsed = parse(
        lib="def work() -> None:\n    pass\n",
        app="from lib import work\n\n\ndef main() -> None:\n    work()\n",
    )
    assert callgraph.build(parsed).successors("app.main") == {"lib.work"}


def test_a_type_annotation_is_not_a_call() -> None:
    """Counting annotations as edges made every annotated name reachable and dead empty."""
    parsed = parse(
        lib="class Report:\n    pass\n\n\ndef unused() -> None:\n    pass\n",
        app="from lib import Report\n\n\ndef main(r: Report) -> None:\n    pass\n",
    )
    assert callgraph.build(parsed).successors("app.main") == set()


# --- the four sets ----------------------------------------------------------------------------


LIVE_AND_DEAD = {
    "app": (
        "def used() -> None:\n"
        "    pass\n\n\n"
        "def never_called() -> None:\n"
        "    pass\n\n\n"
        "def main() -> None:\n"
        "    used()\n\n\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )
}


def test_a_planted_dead_function_is_found() -> None:
    """The fault-injection case: something nothing reaches must be reported."""
    parsed = parse(**LIVE_AND_DEAD)
    part = reach.partition(callgraph.build(parsed), entries_for(parsed))
    assert "app.never_called" in part.dead
    assert "app.used" not in part.dead


def test_a_dispatch_table_is_not_dead() -> None:
    """RULES = (rule_one,) then rule(x) - the names are never called by name.

    detect_patterns.py has exactly this shape, and a call-only graph reported all 18 of its
    rules dead on the first real run.
    """
    parsed = parse(
        engine=(
            "def rule_one(x: int) -> int:\n"
            "    return x\n\n\n"
            "RULES = (rule_one,)\n\n\n"
            "def main() -> None:\n"
            "    for rule in RULES:\n"
            "        rule(1)\n\n\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
        )
    )
    part = reach.partition(callgraph.build(parsed), entries_for(parsed))
    assert "engine.rule_one" not in part.dead


def test_what_only_one_entry_reaches_is_feature_local() -> None:
    parsed = parse(
        a='def only_a() -> None:\n    pass\n\n\nif __name__ == "__main__":\n    only_a()\n',
        b='def only_b() -> None:\n    pass\n\n\nif __name__ == "__main__":\n    only_b()\n',
    )
    part = reach.partition(callgraph.build(parsed), entries_for(parsed))
    assert part.feature_local["a.__main__"] == frozenset({"a.only_a"})
    assert part.feature_local["b.__main__"] == frozenset({"b.only_b"})


def test_what_every_entry_reaches_is_core() -> None:
    parsed = parse(
        shared="def spine() -> None:\n    pass\n",
        a='from shared import spine\n\n\nif __name__ == "__main__":\n    spine()\n',
        b='from shared import spine\n\n\nif __name__ == "__main__":\n    spine()\n',
    )
    part = reach.partition(callgraph.build(parsed), entries_for(parsed))
    assert "shared.spine" in part.core


def test_two_entries_sharing_everything_score_one() -> None:
    """The compartmentalisation number: 1.0 is one tangle with two doors."""
    parsed = parse(
        shared="def spine() -> None:\n    pass\n",
        a='from shared import spine\n\n\nif __name__ == "__main__":\n    spine()\n',
        b='from shared import spine\n\n\nif __name__ == "__main__":\n    spine()\n',
    )
    part = reach.partition(callgraph.build(parsed), entries_for(parsed))
    assert list(reach.overlap(part).values()) == [1.0]


def test_two_entries_sharing_nothing_score_zero() -> None:
    parsed = parse(
        a='def only_a() -> None:\n    pass\n\n\nif __name__ == "__main__":\n    only_a()\n',
        b='def only_b() -> None:\n    pass\n\n\nif __name__ == "__main__":\n    only_b()\n',
    )
    part = reach.partition(callgraph.build(parsed), entries_for(parsed))
    assert list(reach.overlap(part).values()) == [0.0]


def test_a_test_function_is_not_reported_as_dead_code() -> None:
    """Tests are never called by the runtime; without this the suite dominates the number."""
    parsed = parse(
        app='def used() -> None:\n    pass\n\n\nif __name__ == "__main__":\n    used()\n',
        test_app="from app import used\n\n\ndef test_used() -> None:\n    used()\n",
    )
    found = entries_for(parsed)
    runtime = [e for e in found if e.kind != entrypoints.TEST]
    tests = [e for e in found if e.kind == entrypoints.TEST]
    part = reach.partition(callgraph.build(parsed), runtime, tests)
    assert part.dead == frozenset()


def test_live_code_no_test_reaches_is_named() -> None:
    parsed = parse(
        app=(
            "def tested() -> None:\n"
            "    pass\n\n\n"
            "def untested() -> None:\n"
            "    pass\n\n\n"
            'if __name__ == "__main__":\n'
            "    tested()\n"
            "    untested()\n"
        ),
        test_app="from app import tested\n\n\ndef test_it() -> None:\n    tested()\n",
    )
    found = entries_for(parsed)
    part = reach.partition(
        callgraph.build(parsed),
        [e for e in found if e.kind != entrypoints.TEST],
        [e for e in found if e.kind == entrypoints.TEST],
    )
    assert "app.untested" in part.untested
    assert "app.tested" not in part.untested


def test_a_name_that_ran_but_looked_unreachable_is_the_graphs_error() -> None:
    """Coverage beats the parser. That disagreement is worth more than the dead count."""
    parsed = parse(**LIVE_AND_DEAD)
    part = reach.partition(
        callgraph.build(parsed), entries_for(parsed), observed=frozenset({"app.never_called"})
    )
    assert part.graph_was_wrong == frozenset({"app.never_called"})
    assert part.dead == frozenset()
