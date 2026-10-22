"""Read a repository the way it executes, and report what that says about its structure.

Walks every Python file under a root - not ``src/``, which was an assumption that made the
old gate inert on flat layouts, and not one directory per language either. Finds where
execution begins, builds the call graph, and reports the four reachable sets plus the
numbers over them.

What it does not do is decide anything. Every figure here is a measurement with a stated
method and a stated blind spot, because the call graph under it is approximate by
construction and a tool that hid that would be making exactly the kind of confident claim
this plugin was built to refuse.

Usage:
    python sweep.py .                       # this repository
    python sweep.py /path/to/repo --json    # machine-readable
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "core"))

from core import callgraph, clones, entrypoints, reach
from logsetup import configure

log = logging.getLogger("lld.sweep")

#: Directories that are never the program under study.
SKIP: Final = frozenset(
    {".git", ".venv", "venv", "__pycache__", "node_modules", ".tox", "build", "dist", ".mypy_cache"}
)


def dotted(path: Path, root: Path) -> str:
    """A module's dotted name relative to the repository root, layout-independent."""
    relative = path.relative_to(root).with_suffix("")
    parts = [p for p in relative.parts if p != "__init__"]
    return ".".join(parts) if parts else relative.stem


def python_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*.py")
        if not (SKIP & set(p.relative_to(root).parts)) and p.name != "setup.py"
    )


def read(root: Path) -> dict[str, tuple[Any, str]]:
    """Every module that parses, keyed by dotted name."""
    out: dict[str, tuple[Any, str]] = {}
    for path in python_files(root):
        parsed = callgraph.parse_tree(path)
        if parsed is not None:
            out[dotted(path, root)] = parsed
    return out


def find_entries(parsed: dict[str, tuple[Any, str]], root: Path) -> list[entrypoints.EntryPoint]:
    declared = entrypoints._console_scripts(root)
    found: list[entrypoints.EntryPoint] = []
    for module, (tree, path) in sorted(parsed.items()):
        found += entrypoints.in_module(tree, module, path, declared)
    return sorted(found)


def _report(
    part: reach.Partition,
    graph: callgraph.CallGraph,
    kind: str,
    parsed: dict[str, tuple[Any, str]],
) -> str:
    total = len(graph.definitions)
    lines = [
        f"repository kind: {kind}",
        f"definitions: {total}   entry points: {len(part.per_entry)}"
        f"   unresolved call sites: {graph.unresolved}",
        "",
        f"  core            {len(part.core):4d}  reachable from every entry",
        f"  shared          {len(part.shared):4d}  reachable from some",
        f"  dead            {len(part.dead):4d}  reachable from nothing",
    ]
    if total:
        lines.append(f"  dead fraction   {len(part.dead) / total:.1%}")
    if part.graph_was_wrong:
        lines.append(
            f"  graph was wrong {len(part.graph_was_wrong):4d}  ran at runtime, "
            "unreachable on paper"
        )

    lines += ["", "feature-local (reachable from one entry only):"]
    for name, owned in sorted(part.feature_local.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {len(owned):4d}  {name}")

    pairs = reach.overlap(part)
    if pairs:
        lines += ["", "entry-point overlap (1.0 means one tangle with two doors):"]
        for (left, right), score in sorted(pairs.items(), key=lambda kv: -kv[1])[:10]:
            lines.append(f"  {score:.2f}  {left}  <->  {right}")

    found = clones.find(parsed)
    if found:
        rate = clones.duplication_rate(parsed)
        lines += ["", f"duplication rate {rate:.1%}  ({len(found)} repeated shapes):"]
        for clone in found[:10]:
            where = clones.verdict(clone, part.feature_local, part.dead)
            sites = ", ".join(s.qualified for s in clone.sites[:3])
            lines.append(f"  {clone.size:3d} stmts  {where:24s}  {sites}")

    if kind == entrypoints.LIBRARY:
        lines += [
            "",
            "This looks like a library: no main, no console script, no framework entry.",
            "Every exported name is a way in, so 'dead' is not a meaningful answer here.",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=None)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--log-level", default=None)
    args = parser.parse_args(argv)
    configure(level=args.log_level, log_file=None)

    root = (args.root or Path.cwd()).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    parsed = read(root)
    if not parsed:
        print(f"no Python files under {root}", file=sys.stderr)
        return 2

    graph = callgraph.build(parsed)
    entries = find_entries(parsed, root)
    exported = sum(1 for d in graph.definitions if not d.rsplit(".", 1)[-1].startswith("_"))
    kind = entrypoints.classify([e for e in entries if e.kind != entrypoints.TEST], exported)
    runtime = [e for e in entries if e.kind != entrypoints.TEST]
    tests = [e for e in entries if e.kind == entrypoints.TEST]
    part = reach.partition(graph, runtime, tests)
    log.info(
        "swept %s: %d definitions, %d runtime entries, %d tests",
        root,
        len(graph.definitions),
        len(runtime),
        len(tests),
    )

    if args.json:
        print(
            json.dumps(
                {
                    "kind": kind,
                    "definitions": len(graph.definitions),
                    "unresolved": graph.unresolved,
                    "core": sorted(part.core),
                    "dead": sorted(part.dead),
                    "feature_local": {k: sorted(v) for k, v in part.feature_local.items()},
                    "overlap": {f"{a} <-> {b}": v for (a, b), v in reach.overlap(part).items()},
                    "duplication_rate": clones.duplication_rate(parsed),
                },
                indent=2,
            )
        )
        return 0

    print(_report(part, graph, kind, parsed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
