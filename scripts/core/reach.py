"""Which code belongs to which execution thread, as set operations and nothing else.

A repository is not a bag of files. It is one or more places execution begins, and from
each a tree of what that run can reach. "Which files are part of this feature" has an exact
answer once you have those trees, and it needs no clustering algorithm, no threshold and no
tuning parameter:

    Core            intersection of every reachable set - the shared spine
    feature-local   reachable from exactly one entry - belongs to that thread alone
    shared          reachable from some but not all
    dead            reachable from nothing

Modularity scores were the obvious alternative and they do not survive the sizes this tool
targets: the measure has a resolution limit below roughly the square root of the edge count,
no absolute scale for software, and the field that invented it validates against a human
decomposition rather than trusting the number. Set overlap has none of those problems
because it is a ratio of counts, not an optimisation over partitions.

The static graph under all of this under-reports - Python has no sound call graph. So
``reachable`` takes names observed at runtime and unions them in. A name the parser could
not reach and a test executed anyway is not dead; it is proof the graph is wrong there.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from core.callgraph import CallGraph
from core.entrypoints import EntryPoint


@dataclass(frozen=True, slots=True)
class Partition:
    """The four sets, plus what produced them."""

    core: frozenset[str]
    feature_local: dict[str, frozenset[str]]
    shared: frozenset[str]
    dead: frozenset[str]
    per_entry: dict[str, frozenset[str]]
    #: Names the static graph called unreachable that ran anyway. Each one is a place the
    #: call graph is wrong, which is worth more than the dead-code number it corrects.
    graph_was_wrong: frozenset[str]
    #: Live code no test reaches. Falls out for free once test entries are walked
    #: separately from runtime ones, and is the gap a coverage tool would also report.
    untested: frozenset[str]


def reachable(graph: CallGraph, start: str) -> frozenset[str]:
    """Every definition reachable from one entry, by breadth-first walk."""
    seen: set[str] = set()
    queue = [start]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(graph.successors(current) - seen)
    return frozenset(seen)


def _entry_root(graph: CallGraph, entry: EntryPoint) -> str:
    """The graph node an entry point starts from.

    A ``__main__`` guard is not a definition - it is the module's import-time body, which
    the graph records under a synthetic name so the two cases walk identically.
    """
    if entry.qualified in graph.definitions:
        return entry.qualified
    module = entry.qualified.rsplit(".", 1)[0]
    return f"{module}.__import__"


def partition(
    graph: CallGraph,
    entries: list[EntryPoint],
    tests: list[EntryPoint] | None = None,
    observed: frozenset[str] = frozenset(),
) -> Partition:
    """The four sets over every definition in the graph.

    ``entries`` are runtime entry points only. A test is an entry point in the technical
    sense - pytest calls it - but walking three hundred of them makes ``Core`` the
    intersection of three hundred sets, which is empty, and makes every feature one test
    long. Tests answer a different question and are passed separately: what the suite
    reaches, so that live code it never reaches can be named.

    ``observed`` is the set of names a run actually executed - coverage, not inference. It
    is unioned into reachability and the difference is reported, because a name that ran
    while the parser called it unreachable is the parser's error, not dead code.
    """
    everything = frozenset(graph.definitions)
    per_entry = {e.qualified: reachable(graph, _entry_root(graph, e)) & everything for e in entries}

    live_statically = frozenset().union(*per_entry.values()) if per_entry else frozenset()
    wrong = (observed & everything) - live_statically
    live = live_statically | wrong

    core = frozenset.intersection(*per_entry.values()) if per_entry else frozenset()
    local: dict[str, frozenset[str]] = {}
    for name, reached in per_entry.items():
        others = frozenset().union(*(r for k, r in per_entry.items() if k != name)) or frozenset()
        local[name] = reached - others

    test_reach: frozenset[str] = frozenset()
    for entry in tests or []:
        test_reach |= reachable(graph, _entry_root(graph, entry)) & everything

    # A test function is a definition the runtime never calls, so without this every test in
    # the suite lands in `dead` and the number says more about the suite than the code.
    claimed = frozenset().union(*local.values()) if local else frozenset()
    return Partition(
        core=core,
        feature_local=local,
        shared=live - core - claimed,
        dead=everything - live - test_reach,
        per_entry=per_entry,
        graph_was_wrong=wrong,
        untested=live - test_reach,
    )


def overlap(part: Partition) -> dict[tuple[str, str], float]:
    """Jaccard overlap between each pair of entry points.

    This is the compartmentalisation number. Two entry points sharing most of what they
    reach are not two features; they are one tangle with two doors. It is a ratio, so it
    does not drift with repository size, and it needs no threshold because the question
    asked of it is whether a change moved it.
    """
    out: dict[tuple[str, str], float] = {}
    for (left, a), (right, b) in combinations(sorted(part.per_entry.items()), 2):
        union = a | b
        out[(left, right)] = len(a & b) / len(union) if union else 0.0
    return out
