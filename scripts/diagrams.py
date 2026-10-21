"""Draw four views of a package from its syntax tree, as SVG beside the contract.

A contract says what a module promises. These say what the code is shaped like, which is a
different question and one a reader answers faster from a picture: which class inherits from
which, which module imports which, where a function branches and raises, and which errors
cross a module boundary.

Every label is one approved verb and every caption stays inside the checkable subset in
``ste.py``, so two diagrams of different packages read the same way. Identifiers pass through
as technical names: a reader must be able to grep for what they see.

Layout is deterministic - nodes in layers, straight edges, fixed spacing - so regenerating
after a code change produces a diff a person can read rather than a reshuffled picture.

Usage:
    python diagrams.py src/shapes --out docs/diagrams
    python diagrams.py src/shapes --check
"""

from __future__ import annotations

import argparse
import ast
import logging
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

from derive import dotted_name, import_graph
from logsetup import configure
from ste import Violation, check_caption, check_label, report

log = logging.getLogger("lld.diagrams")

WIDTH: Final = 1100
BOX_W: Final = 190
BOX_H: Final = 48
GAP_X: Final = 40
GAP_Y: Final = 86
MARGIN: Final = 28

OPEN_BASES: Final = frozenset(
    {
        "ABC",
        "Protocol",
        "Enum",
        "IntEnum",
        "StrEnum",
        "Exception",
        "ValueError",
        "TypeError",
        "RuntimeError",
        "object",
        "NamedTuple",
        "TypedDict",
        "Generic",
    }
)


@dataclass(frozen=True, slots=True)
class Node:
    """One box. ``kind`` picks its colour, ``note`` is the small line beneath the name."""

    key: str
    name: str
    kind: str = "plain"
    note: str = ""


@dataclass(frozen=True, slots=True)
class Edge:
    """One arrow. ``verb`` must be a single approved word."""

    source: str
    target: str
    verb: str


@dataclass(frozen=True, slots=True)
class Diagram:
    """A set of boxes and arrows, plus the one claim the figure makes."""

    title: str
    caption: str
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def violations(self) -> list[Violation]:
        """Every label and caption checked against the approved subset."""
        found = [v for edge in self.edges for v in check_label(edge.verb)]
        return found + check_caption(self.caption)


# --- reading the package ------------------------------------------------------------------


def _modules(package: Path) -> list[Path]:
    return [
        path
        for path in sorted(package.rglob("*.py"))
        if path.name != "__init__.py" and "tests" not in path.parts
    ]


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _base_names(cls: ast.ClassDef) -> list[str]:
    out: list[str] = []
    for base in cls.bases:
        if isinstance(base, ast.Name):
            out.append(base.id)
        elif isinstance(base, ast.Attribute):
            out.append(base.attr)
        elif isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name):
            out.append(base.value.id)
    return out


def inheritance(package: Path, src_root: str) -> Diagram:
    """Classes and the bases they name. The shape INHERITANCE.md has rules about."""
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    for path in _modules(package):
        tree = _parse(path)
        if tree is None:
            continue
        module = dotted_name(path, src_root)
        for item in tree.body:
            if not isinstance(item, ast.ClassDef):
                continue
            bases = _base_names(item)
            raises = any(b.endswith("Error") or b == "Exception" for b in bases)
            kind = "error" if raises else "type"
            nodes[item.name] = Node(item.name, item.name, kind, module.rsplit(".", 1)[-1])
            for base in _base_names(item):
                if base not in nodes:
                    nodes[base] = Node(base, base, "open" if base in OPEN_BASES else "type", "")
                edges.append(Edge(item.name, base, "is"))
    return Diagram(
        title="Inheritance",
        caption="Each arrow shows a class and the base it names. A line of three boxes "
        "shows a base of a base.",
        nodes=list(nodes.values()),
        edges=edges,
    )


def dependencies(package: Path, package_root: str) -> Diagram:
    """Which module imports which, with the entry-point boundary visible."""
    graph = import_graph(package.parent if package.name == package_root else package, package_root)
    nodes = [
        Node(
            name,
            name.rsplit(".", 1)[-1],
            "private" if ".lib." in name or ".internal." in name else "public",
            name.rsplit(".", 1)[0],
        )
        for name in sorted(graph)
    ]
    known = {n.key for n in nodes}
    edges = [
        Edge(source, target, "imports")
        for source, targets in sorted(graph.items())
        for target in sorted(targets)
        if target in known
    ]
    return Diagram(
        title="Module dependencies",
        caption="Each arrow shows one module and a module it imports. An arrow into a "
        "private module from another package breaks the boundary.",
        nodes=nodes,
        edges=edges,
    )


def control_flow(module: Path, src_root: str) -> Diagram:
    """Inside one module: public entry points, their branches, and where each raise sits."""
    tree = _parse(module)
    nodes: list[Node] = []
    edges: list[Edge] = []
    if tree is None:
        return Diagram("Control flow", "The module does not parse.", nodes, edges)

    for item in tree.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if item.name.startswith("_"):
            continue
        nodes.append(Node(item.name, item.name, "public", f"line {item.lineno}"))
        for inner in ast.walk(item):
            if not isinstance(inner, ast.Raise):
                continue
            exc = inner.exc
            if isinstance(exc, ast.Call):
                exc = exc.func
            name = exc.id if isinstance(exc, ast.Name) else getattr(exc, "attr", "")
            if not name:
                continue
            if not any(n.key == name for n in nodes):
                nodes.append(Node(name, name, "error", f"line {inner.lineno}"))
            edges.append(Edge(item.name, name, "raises"))
    return Diagram(
        title=f"Control flow of {dotted_name(module, src_root)}",
        caption="Each arrow shows a public name and an error it raises. A name with no "
        "arrow raises no error.",
        nodes=nodes,
        edges=edges,
    )


def _exception_name(node: ast.expr | None) -> str:
    """The type a raise or an except names, when it names one plainly."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _raised_and_caught(
    package: Path, src_root: str
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Per error type, the modules that raise it and the modules that catch it."""
    raisers: dict[str, set[str]] = {}
    catchers: dict[str, set[str]] = {}
    for path in _modules(package):
        tree = _parse(path)
        if tree is None:
            continue
        module = dotted_name(path, src_root).rsplit(".", 1)[-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise):
                name = _exception_name(node.exc)
                if name:
                    raisers.setdefault(name, set()).add(module)
            elif isinstance(node, ast.ExceptHandler) and node.type is not None:
                parts = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
                for part in parts:
                    name = _exception_name(part)
                    if name:
                        catchers.setdefault(name, set()).add(module)
    return raisers, catchers


def error_flow(package: Path, src_root: str) -> Diagram:
    """Which module raises an error and which module catches it.

    Matched by name, not by resolved symbol: two classes with one name look like one here.
    The caption says so, because a reader should not have to find that out.
    """
    raisers, catchers = _raised_and_caught(package, src_root)
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    for error in sorted(set(raisers) | set(catchers)):
        nodes[error] = Node(error, error, "error", "")
        for module in sorted(raisers.get(error, ())):
            nodes.setdefault(f"m:{module}", Node(f"m:{module}", module, "public", ""))
            edges.append(Edge(f"m:{module}", error, "raises"))
        for module in sorted(catchers.get(error, ())):
            nodes.setdefault(f"c:{module}", Node(f"c:{module}", module, "plain", ""))
            edges.append(Edge(f"c:{module}", error, "catches"))
    return Diagram(
        title="Error flow",
        caption="Each arrow shows a module and an error it raises or catches. The code "
        "matches names as text, so two types of one name look like one type.",
        nodes=list(nodes.values()),
        edges=edges,
    )


# --- drawing -------------------------------------------------------------------------------


def _layers(diagram: Diagram) -> list[list[Node]]:
    """Put every node in a layer below the nodes it points at, so arrows run one way."""
    targets = {e.target for e in diagram.edges}
    sources = {e.source for e in diagram.edges}
    by_key = {n.key: n for n in diagram.nodes}

    depth: dict[str, int] = {k: 0 for k in by_key if k in targets and k not in sources}
    remaining = [n for n in diagram.nodes if n.key not in depth]
    for _ in range(6):
        for node in remaining:
            parents = [e.target for e in diagram.edges if e.source == node.key]
            known = [depth[p] for p in parents if p in depth]
            if known:
                depth[node.key] = max(known) + 1
    for node in diagram.nodes:
        depth.setdefault(node.key, 0 if node.key not in sources else 1)

    rows: dict[int, list[Node]] = {}
    for node in diagram.nodes:
        rows.setdefault(depth[node.key], []).append(node)
    return [rows[k] for k in sorted(rows)]


def _place(diagram: Diagram) -> tuple[dict[str, tuple[int, int]], int]:
    """A centre point for every node, and the height the figure needs.

    Rows are counted cumulatively rather than per layer: a layer wide enough to wrap used to
    push its overflow onto the next layer's row, and two boxes landed on each other.
    """
    per_row = max(1, (WIDTH - 2 * MARGIN) // (BOX_W + GAP_X))
    positions: dict[str, tuple[int, int]] = {}
    row = 0
    for nodes in _layers(diagram):
        for index, node in enumerate(nodes):
            column = index % per_row
            x = MARGIN + column * (BOX_W + GAP_X) + BOX_W // 2
            y = MARGIN + (row + index // per_row) * GAP_Y + BOX_H // 2
            positions[node.key] = (x, y)
        row += (len(nodes) - 1) // per_row + 1
    return positions, MARGIN * 2 + GAP_Y * max(row, 1)


def render(diagram: Diagram) -> str:
    """One self-contained SVG. currentColor so it reads in either theme."""
    positions, height = _place(diagram)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height + 54}" '
        f'role="img" aria-label="{diagram.title}. {diagram.caption}">',
        '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker></defs>',
        "<style>"
        ".b{fill:none;stroke:currentColor;stroke-width:1.4;opacity:.75}"
        ".b.error{stroke:#d1595c}.b.open{stroke-dasharray:5 4}.b.private{opacity:.45}"
        ".n{font:13px ui-monospace,Consolas,monospace;fill:currentColor;text-anchor:middle}"
        ".s{font:10px ui-monospace,Consolas,monospace;fill:currentColor;opacity:.55;"
        "text-anchor:middle}"
        ".e{stroke:currentColor;stroke-width:1.2;fill:none;opacity:.55}"
        ".l{font:10px ui-monospace,Consolas,monospace;fill:currentColor;opacity:.7;"
        "text-anchor:middle}"
        ".c{font:13px Georgia,serif;fill:currentColor;opacity:.75}"
        "</style>",
    ]

    for edge in diagram.edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        x1, y1 = positions[edge.source]
        x2, y2 = positions[edge.target]
        start_y = y1 - BOX_H // 2 if y2 < y1 else y1 + BOX_H // 2
        end_y = y2 + BOX_H // 2 + 8 if y2 < y1 else y2 - BOX_H // 2 - 8
        parts.append(f'<path class="e" d="M{x1},{start_y} L{x2},{end_y}" marker-end="url(#a)"/>')
        parts.append(
            f'<text class="l" x="{(x1 + x2) // 2 + 14}" y="{(start_y + end_y) // 2}">'
            f"{edge.verb}</text>"
        )

    for node in diagram.nodes:
        x, y = positions[node.key]
        left, top = x - BOX_W // 2, y - BOX_H // 2
        parts.append(
            f'<rect class="b {node.kind}" x="{left}" y="{top}" width="{BOX_W}" '
            f'height="{BOX_H}" rx="4"/>'
        )
        label_y = y + 1 if node.note else y + 5
        parts.append(f'<text class="n" x="{x}" y="{label_y}">{node.name}</text>')
        if node.note:
            parts.append(f'<text class="s" x="{x}" y="{y + 16}">{node.note}</text>')

    parts.append(f'<text class="c" x="{MARGIN}" y="{height + 32}">{diagram.caption}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def build(package: Path, src_root: str, package_root: str) -> dict[str, Diagram]:
    """Every diagram this package supports, keyed by file stem."""
    out = {
        "inheritance": inheritance(package, src_root),
        "dependencies": dependencies(package, package_root),
        "errors": error_flow(package, src_root),
    }
    for module in _modules(package):
        flow = control_flow(module, src_root)
        if flow.edges:
            out[f"flow-{module.stem}"] = flow
    return {name: d for name, d in out.items() if d.nodes}


def _all_violations(diagrams: Iterable[Diagram]) -> list[Violation]:
    return [v for d in diagrams for v in d.violations()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--out", type=Path, default=Path("docs/diagrams"))
    parser.add_argument("--src-root", default="src")
    parser.add_argument("--check", action="store_true", help="fail if a file is stale")
    parser.add_argument("--log-level", default=None)
    args = parser.parse_args(argv)
    configure(level=args.log_level, log_file=None)

    diagrams = build(args.package, args.src_root, args.package.name)
    violations = _all_violations(diagrams.values())
    if violations:
        print("labels or captions left the approved subset:")
        print(report(violations))
        return 2

    stale: list[str] = []
    for name, diagram in sorted(diagrams.items()):
        target = args.out / f"{args.package.name}.{name}.svg"
        content = render(diagram)
        if args.check:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current != content:
                stale.append(target.as_posix())
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(
            f"wrote {target.as_posix()}  ({len(diagram.nodes)} boxes, {len(diagram.edges)} arrows)"
        )

    if args.check:
        for path in stale:
            print(f"{path}: stale, regenerate it")
        if not stale:
            print("every diagram is current")
        return 1 if stale else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
