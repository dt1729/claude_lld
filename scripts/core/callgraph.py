"""A function-level call graph, and the honest account of what it cannot see.

``derive.py`` already builds this one level up, between modules. That is enough to answer
"who imports whom" and not enough to answer "what runs", because a module can be imported
for one function and carry forty.

**What this resolves.** A direct call to a name defined in the same module, or imported from
a module in the same package. That covers the ordinary case and nothing more.

**What it cannot resolve, and why that is dangerous.** ``getattr(obj, name)()``, a method
called on a value whose type is not known here, a callback registered at runtime, anything
reached through ``__getattr__``. Python has no sound static call graph, so this one
under-reports: it will call live code unreachable. For a report that is noise; for a tool
proposing deletions it is the worst error available, which is why ``reach.py`` takes a set
of names observed at runtime and treats them as ground truth over anything decided here.

Resolution follows the order Python itself uses: a name defined in the calling module
wins, then a name the module explicitly imported, and only then any definition anywhere
with that name. The last rule exists for method calls - ``x.write()`` cannot be resolved
without types - and it over-reports, in the opposite direction from the under-reporting
above. The two do not cancel. Both are recorded rather than hidden, because a figure that
silently splits the difference is the kind of claim this plugin exists to refuse.

Without the first two rules the graph collapses: every module in this repository defines
``main``, so a bare-name match made all thirteen entry points reach each other and reported
two thirds of the codebase dead.

A function handed somewhere as a value is an edge too. ``RULES = (rule_01, rule_02, ...)``
followed by ``rule(tree, ctx)`` is a dispatch table: the names are never called directly and
a call-only graph reports every one of them dead. The same shape covers callbacks, handler
maps, decorators and anything a framework is given. So a bare reference to a known
definition counts as an edge from the scope that mentions it. It over-reports - a name
mentioned and never invoked still links - and that is the safe direction.

A call into a dependency is not an edge at all. ``requests.get(...)`` reduces to the bare
name ``get``, which then matched every internal ``get`` in the repository and manufactured
an edge to code the caller has never heard of. The dependency manifest says which import
roots are foreign - that is what ``requirements.txt`` is for - and a call whose receiver is
one of them resolves to nothing. Only the code someone wrote here is worth a graph.

Annotations are excluded from that rule. ``def f(x: Finding) -> Report`` names two types
and calls neither, and counting them made every annotated name reachable and the dead set
empty. A type is a claim about a value, not a transfer of control.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Definition:
    """One function a call can land on."""

    qualified: str
    module: str
    name: str
    path: str
    line: int


@dataclass(slots=True)
class CallGraph:
    """Definitions, and the edges between them that could be resolved."""

    definitions: dict[str, Definition] = field(default_factory=dict)
    edges: dict[str, set[str]] = field(default_factory=dict)
    #: Call sites whose target could not be named at all - the measure of how much this
    #: graph does not know. Reported rather than rounded away.
    unresolved: int = 0

    def successors(self, qualified: str) -> set[str]:
        return self.edges.get(qualified, set())


def _called_name(node: ast.Call, foreign: frozenset[str] = frozenset()) -> str:
    """The last name in a call expression, or empty when it is computed or not ours.

    ``foreign`` holds the names bound to a dependency in this module. ``requests.get()``
    with ``requests`` foreign returns nothing, because the callee is not in this codebase
    and matching it against an internal ``get`` is an invention.
    """
    func = node.func
    if isinstance(func, ast.Name):
        return "" if func.id in foreign else func.id
    if isinstance(func, ast.Attribute):
        root = func.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and root.id in foreign:
            return ""
        return func.attr
    return ""


def _definitions_in(tree: ast.Module, module: str, path: str) -> list[Definition]:
    out: list[Definition] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(Definition(f"{module}.{node.name}", module, node.name, path, node.lineno))
        elif isinstance(node, ast.ClassDef):
            out += [
                Definition(f"{module}.{node.name}.{m.name}", module, m.name, path, m.lineno)
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
    return out


def _body_of(tree: ast.Module, qualified: str) -> ast.AST | None:
    """The node whose calls belong to this definition."""
    tail = qualified.split(".")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == tail[-1]:
            return node
        if isinstance(node, ast.ClassDef) and len(tail) >= 2 and node.name == tail[-2]:
            for member in node.body:
                if (
                    isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and member.name == tail[-1]
                ):
                    return member
    return None


def _annotation_nodes(node: ast.AST) -> set[int]:
    """Every node that is part of a type annotation rather than of the running code."""
    out: set[int] = set()
    for inner in ast.walk(node):
        annotations: list[ast.expr | None] = []
        if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotations = [inner.returns, *(a.annotation for a in inner.args.args)]
            annotations += [a.annotation for a in inner.args.kwonlyargs]
            annotations += [a.annotation for a in inner.args.posonlyargs]
        elif isinstance(inner, ast.AnnAssign):
            annotations = [inner.annotation]
        for annotation in annotations:
            if annotation is not None:
                out |= {id(n) for n in ast.walk(annotation)}
    return out


def _referenced_names(node: ast.AST, foreign: frozenset[str] = frozenset()) -> list[str]:
    """Every name this scope reads: calls, and functions handed around as values."""
    skip = _annotation_nodes(node)
    names = [_called_name(c, foreign) for c in ast.walk(node) if isinstance(c, ast.Call)]
    names += [
        n.id
        for n in ast.walk(node)
        if isinstance(n, ast.Name)
        and isinstance(n.ctx, ast.Load)
        and id(n) not in skip
        and n.id not in foreign
    ]
    return [n for n in names if n]


def _module_level_calls(tree: ast.Module, foreign: frozenset[str]) -> list[str]:
    """Names read at import time, which run whether or not anything calls the module."""
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        names += _referenced_names(node, foreign)
    return names


def internal_roots(known: set[str]) -> frozenset[str]:
    """Every spelling by which a module in this repository can be imported.

    A module this sweep calls ``scripts.contracts`` is imported as ``contracts`` by a script
    that put its own directory on ``sys.path`` first, which is ordinary Python and extremely
    common. Matching only the full dotted name marked every such sibling as a dependency and
    reported fourteen live modules dead.

    Suffixes are included, so a local ``json.py`` would shadow the standard library here the
    same way it would at runtime. That errs toward calling things internal, which
    over-reports reachability - the safe direction.
    """
    roots: set[str] = set()
    for name in known:
        parts = name.split(".")
        roots |= {".".join(parts[i:]) for i in range(len(parts))}
        roots |= {parts[i] for i in range(len(parts))}
    return frozenset(roots)


def foreign_names(tree: ast.Module, known: set[str]) -> frozenset[str]:
    """Names this module bound to something outside the repository.

    A module imported but absent from ``known`` is a dependency, a standard-library module,
    or a package this sweep did not parse. In every case its internals are not ours.
    """
    roots = internal_roots(known)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in roots:
                    out.add(alias.asname or alias.name.split(".")[0])
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.level == 0
            and node.module.split(".")[0] not in roots
        ):
            out |= {a.asname or a.name for a in node.names}
    return frozenset(out)


def _imported_names(tree: ast.Module, known: set[str]) -> dict[str, str]:
    """Bare name -> dotted definition, for names this module imported explicitly.

    ``from contracts import validate_contract`` makes ``validate_contract`` mean exactly
    ``contracts.validate_contract`` here, which is the difference between a call graph and
    a name collision.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                candidate = f"{node.module}.{alias.name}"
                if candidate in known:
                    out[alias.asname or alias.name] = candidate
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out[alias.asname or alias.name.split(".")[0]] = alias.name
    return out


def _resolve(
    name: str, module: str, imported: dict[str, str], by_name: dict[str, set[str]]
) -> set[str]:
    """Where a bare call lands, in Python's own lookup order."""
    local = f"{module}.{name}"
    if local in by_name.get(name, set()):
        return {local}
    if name in imported and imported[name] in by_name.get(name, set()):
        return {imported[name]}
    return by_name.get(name, set())


def _targets_of(
    body: ast.AST,
    module: str,
    imported: dict[str, str],
    by_name: dict[str, set[str]],
    foreign: frozenset[str] = frozenset(),
) -> tuple[set[str], int]:
    """What one definition reaches, and how many call sites could not be named at all."""
    blind = sum(
        1 for c in ast.walk(body) if isinstance(c, ast.Call) and not _called_name(c, foreign)
    )
    targets: set[str] = set()
    for name in _referenced_names(body, foreign):
        targets |= _resolve(name, module, imported, by_name)
    return targets, blind


def build(parsed: dict[str, tuple[ast.Module, str]]) -> CallGraph:
    """The call graph over every parsed module, keyed by dotted name.

    ``parsed`` maps a module's dotted name to its tree and its path. Resolution is by bare
    name across the whole package: ambiguity is resolved by linking to every candidate,
    which over-reports reachability rather than under-reporting it. Given the choice, a
    graph that calls dead code live is safer than one that calls live code dead.
    """
    graph = CallGraph()
    by_name: dict[str, set[str]] = {}

    for module, (tree, path) in sorted(parsed.items()):
        for definition in _definitions_in(tree, module, path):
            graph.definitions[definition.qualified] = definition
            by_name.setdefault(definition.name, set()).add(definition.qualified)

    known = set(graph.definitions)
    for module, (tree, _path) in sorted(parsed.items()):
        imported = _imported_names(tree, known)
        outside = foreign_names(tree, set(parsed))
        import_root = f"{module}.__import__"
        graph.edges.setdefault(import_root, set())
        for name in _module_level_calls(tree, outside):
            graph.edges[import_root] |= _resolve(name, module, imported, by_name)

        for qualified in [d for d in graph.definitions if d.startswith(f"{module}.")]:
            body = _body_of(tree, qualified)
            if body is None:
                continue
            targets, blind = _targets_of(body, module, imported, by_name, outside)
            graph.unresolved += blind
            graph.edges[qualified] = targets - {qualified}
    return graph


def parse_tree(path: Path) -> tuple[ast.Module, str] | None:
    """One module parsed, or None when it does not read or does not parse."""
    try:
        return ast.parse(path.read_text(encoding="utf-8")), path.as_posix()
    except (OSError, SyntaxError, ValueError):
        return None
