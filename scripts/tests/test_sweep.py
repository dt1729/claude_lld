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


def calls(graph: callgraph.CallGraph, name: str) -> set[str]:
    """Successors that are definitions - the module-body roots a call also implies are
    not what these tests are about."""
    return {s for s in graph.successors(name) if not s.endswith((".__import__", ".__main__"))}


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
    assert calls(graph, "one.main") == {"one.helper"}
    assert calls(graph, "two.main") == {"two.helper"}


def test_an_imported_name_resolves_to_what_was_imported() -> None:
    parsed = parse(
        lib="def work() -> None:\n    pass\n",
        app="from lib import work\n\n\ndef main() -> None:\n    work()\n",
    )
    assert calls(callgraph.build(parsed), "app.main") == {"lib.work"}


def test_a_type_annotation_is_not_a_call() -> None:
    """Counting annotations as edges made every annotated name reachable and dead empty."""
    parsed = parse(
        lib="class Report:\n    pass\n\n\ndef unused() -> None:\n    pass\n",
        app="from lib import Report\n\n\ndef main(r: Report) -> None:\n    pass\n",
    )
    assert calls(callgraph.build(parsed), "app.main") == set()


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


def test_a_migration_is_an_entry_point_a_tool_runs() -> None:
    """Alembic imports a migration and calls upgrade(); nothing in the source references it.

    Found on codesense-ai, where two of nineteen names reported dead were a migration's
    upgrade and downgrade. The other seventeen were a utility layer nothing called, which
    was correct.
    """
    tree = ast.parse("def upgrade() -> None:\n    pass\n\n\ndef downgrade() -> None:\n    pass\n")
    found = entrypoints.in_module(tree, "v1", "alembic/versions/v1.py", set())
    assert {e.kind for e in found} == {entrypoints.TOOL_RUN}


def test_the_same_name_outside_a_migration_directory_is_not_an_entry_point() -> None:
    """upgrade() in ordinary code is an ordinary function."""
    tree = ast.parse("def upgrade() -> None:\n    pass\n")
    assert entrypoints.in_module(tree, "app", "app/service.py", set()) == []


# --- dependencies are not ours ------------------------------------------------------------------


def test_a_call_into_a_dependency_is_not_an_edge() -> None:
    """requests.get() reduced to `get` and matched every internal get in the repository."""
    parsed = parse(
        app="import requests\n\n\ndef fetch():\n    return requests.get('http://x')\n",
        store="def get():\n    return 1\n",
    )
    assert calls(callgraph.build(parsed), "app.fetch") == set()


def test_an_internal_call_of_the_same_name_still_resolves() -> None:
    parsed = parse(
        app="from store import get\n\n\ndef fetch():\n    return get()\n",
        store="def get():\n    return 1\n",
    )
    assert calls(callgraph.build(parsed), "app.fetch") == {"store.get"}


def test_a_sibling_import_through_sys_path_is_internal() -> None:
    """A script that puts its own directory on sys.path imports `contracts`, not
    `scripts.contracts`. Matching only the full dotted name called fourteen live modules dead.
    """
    roots = callgraph.internal_roots({"scripts.contracts", "scripts.core.reach"})
    assert "contracts" in roots
    assert "core" in roots
    assert "requests" not in roots


def test_a_dependency_bound_by_from_import_is_foreign() -> None:
    tree = ast.parse("from requests import get\n")
    assert "get" in callgraph.foreign_names(tree, {"store"})


# --- what gta-clipper taught: two ways a package refers to its own modules ---------------------


def reach_of(parsed: dict[str, tuple[ast.Module, str]], start: str) -> set[str]:
    graph = callgraph.build(parsed)
    seen, todo = set(), [start]
    while todo:
        node = todo.pop()
        for nxt in graph.successors(node):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def test_a_relative_import_of_a_sibling_module_resolves() -> None:
    """``from . import batch`` inside ``pkg/jobs.py`` has no module name to resolve against; it
    reaches ``pkg.batch`` today only through the bare-name fallback. Pinned so a stricter
    resolver cannot lose it."""
    parsed = {
        "pkg.batch": (ast.parse("def submit():\n    return 1\n"), "pkg/batch.py"),
        "pkg.jobs": (
            ast.parse("def process():\n    from . import batch\n    return batch.submit()\n"),
            "pkg/jobs.py",
        ),
    }
    assert "pkg.batch.submit" in reach_of(parsed, "pkg.jobs.process")


def test_a_relative_from_import_resolves_against_the_package() -> None:
    parsed = {
        "pkg.batch": (ast.parse("def submit():\n    return 1\n"), "pkg/batch.py"),
        "pkg.jobs": (
            ast.parse("from .batch import submit\n\n\ndef process():\n    return submit()\n"),
            "pkg/jobs.py",
        ),
    }
    assert "pkg.batch.submit" in reach_of(parsed, "pkg.jobs.process")


def test_a_module_attribute_handed_around_as_a_value_is_an_edge() -> None:
    """``CMDS = {"process": jobs.process}`` never calls ``jobs.process``; bare names as values
    were already edges, dotted ones were not, and a whole command table read as dead."""
    parsed = {
        "pkg.jobs": (ast.parse("def process():\n    return 1\n"), "pkg/jobs.py"),
        "pkg.__main__": (
            ast.parse(
                'from . import jobs\n\nCMDS = {"process": jobs.process}\n\n'
                'if __name__ == "__main__":\n    CMDS[__import__("sys").argv[1]]()\n'
            ),
            "pkg/__main__.py",
        ),
    }
    assert "pkg.jobs.process" in reach_of(parsed, "pkg.__main__.__import__")


def test_an_attribute_of_something_not_an_internal_module_is_not_an_edge() -> None:
    """``cfg.get`` must not resolve to an internal ``get`` just because the word matches."""
    parsed = {
        "pkg.store": (ast.parse("def get():\n    return 1\n"), "pkg/store.py"),
        "pkg.app": (ast.parse("def run(cfg):\n    return cfg.get\n"), "pkg/app.py"),
    }
    assert "pkg.store.get" not in reach_of(parsed, "pkg.app.run")


# --- what the second batch taught ---------------------------------------------------------------


def test_a_constructor_call_reaches_init() -> None:
    """``Foo()`` runs ``Foo.__init__``; a graph keyed on function names never saw that, and in
    one tkinter application the constructor and the sixty methods it set up all read as dead."""
    src = "\n".join(
        [
            "class Foo:",
            "    def __init__(self):",
            "        self.setup()",
            "",
            "    def setup(self):",
            "        pass",
            "",
            "",
            "def main():",
            "    return Foo()",
        ]
    )
    assert {"app.Foo.__init__", "app.Foo.setup"} <= reach_of(parse(app=src), "app.main")


def test_an_mcp_tool_is_a_framework_entry_point() -> None:
    parsed = parse(server='@mcp.tool(name="x")\ndef x():\n    return 1\n')
    assert [(e.qualified, e.kind) for e in entries_for(parsed)] == [
        ("server.x", entrypoints.FRAMEWORK)
    ]


def test_a_module_that_builds_the_served_app_is_an_entry_point() -> None:
    """uvicorn imports ``main:app`` from a string; nothing in the source calls the module."""
    parsed = parse(main="from fastapi import FastAPI\n\napp = FastAPI()\napp.include_router(r)\n")
    assert [(e.qualified, e.kind) for e in entries_for(parsed)] == [
        ("main.__main__", entrypoints.SERVED)
    ]


def test_a_module_with_a_main_guard_is_not_listed_twice_for_its_app() -> None:
    parsed = parse(main='app = Flask(__name__)\n\nif __name__ == "__main__":\n    app.run()\n')
    assert [e.kind for e in entries_for(parsed)] == [entrypoints.MAIN_GUARD]


def test_an_app_built_by_a_factory_is_still_a_served_module() -> None:
    """``app = create_application()`` in main.py is what uvicorn imports; the factory's name
    is the author's, so the target name carries the convention."""
    parsed = parse(main="from src.core import create_application\n\napp = create_application()\n")
    assert [e.kind for e in entries_for(parsed)] == [entrypoints.SERVED]


def test_a_method_handed_to_a_widget_as_a_callback_is_reached() -> None:
    """``Button(command=self._send)`` never calls ``_send`` in the source; in one tkinter
    application every handler wired that way read as dead - 127 of 859 definitions."""
    src = "\n".join(
        [
            "class App:",
            "    def __init__(self):",
            "        self.button = Button(command=self._send)",
            "",
            "    def _send(self):",
            "        pass",
            "",
            "",
            "def main():",
            "    return App()",
        ]
    )
    assert "app.App._send" in reach_of(parse(app=src), "app.main")


def test_a_table_built_at_import_time_is_reached_through_the_import() -> None:
    """``SCREENS = [Gate(fn=_margin)]`` is the only reference to ``_margin``; it runs when the
    module is imported, never when anything is called. 66 gate functions in one screener
    read as dead for this."""
    parsed = {
        "qs.screens": (
            ast.parse("def _margin(c):\n    return 1\n\n\nSCREENS = [_margin]\n"),
            "qs/screens.py",
        ),
        "qs.audit": (
            ast.parse("from .screens import SCREENS\n\n\ndef run():\n    return len(SCREENS)\n"),
            "qs/audit.py",
        ),
    }
    assert "qs.screens._margin" in reach_of(parsed, "qs.audit.run")


def test_calling_a_function_counts_its_modules_body_as_run() -> None:
    parsed = parse(
        util="def helper():\n    return 1\n\n\nREGISTRY = [helper]\n\n\ndef lookup():\n    return REGISTRY\n",
        app="from util import lookup\n\n\ndef main():\n    return lookup()\n",
    )
    assert "util.helper" in reach_of(parsed, "app.main")
