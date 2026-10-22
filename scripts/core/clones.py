"""Code written twice, found by hashing structure rather than text.

Names and literals are erased, structure is kept. ``calc_range(a, b)`` and
``compute_range(x, y)`` with the same body hash identically, which is the point: a model
duplicates because it generated each site without looking at the other, and it renames
things on the way.

Three granularities, because duplication hides at three scales:

* **class** - a type written twice
* **function** - the classic copy-paste
* **block** - consecutive sibling statements repeated, which is a ``for`` loop nobody wrote

**What this cannot see.** ``x * x`` and ``x ** 2`` compute the same thing and hash
differently. That is a Type 4 clone - semantically identical, syntactically different - and
no structural hash reaches it. Detecting those needs a judgment, on candidates a cheap
filter produced, and it is deliberately not attempted here: an all-pairs comparison over
five hundred functions is a hundred and twenty-five thousand questions, and a judge asked
"are these the same" says yes far too often.

A finding is not a verdict. ``reach.py`` supplies the context that decides what a duplicate
means: two copies in independent features are the complaint this plugin exists for, two in
one feature are a note, and a copy that nothing reaches is a deletion rather than a
refactor.
"""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Final

CLASS: Final = "class"
FUNCTION: Final = "function"
BLOCK: Final = "block"

#: Below this, everything matches everything. A two-line accessor is not a clone of another
#: two-line accessor; it is what a two-line accessor looks like.
MIN_STATEMENTS: Final = 5

#: A repeated run of sibling statements shorter than this is a coincidence, not a loop.
MIN_BLOCK: Final = 3


@dataclass(frozen=True, slots=True, order=True)
class Fragment:
    """One hashable piece of code, and where it was."""

    digest: str
    kind: str
    qualified: str
    path: str
    line: int
    size: int


@dataclass(frozen=True, slots=True)
class Clone:
    """Two or more fragments with the same shape."""

    digest: str
    kind: str
    size: int
    sites: tuple[Fragment, ...]


class _Normalise(ast.NodeTransformer):
    """Erase what a copy would have renamed, keep what it would have kept."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        return ast.copy_location(ast.arg(arg="_", annotation=None), node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        # A docstring is prose, not structure, and two functions should not be clones
        # because they share a sentence. Type is kept so 1 and "1" stay different shapes.
        return ast.copy_location(ast.Constant(value=type(node.value).__name__), node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        inner = self.visit(node.value)
        return ast.copy_location(ast.Attribute(value=inner, attr="_", ctx=node.ctx), node)


def _digest(nodes: list[ast.stmt]) -> str:
    module = ast.Module(
        body=[_Normalise().visit(ast.parse(ast.unparse(n))) for n in nodes], type_ignores=[]
    )
    return hashlib.blake2b(ast.dump(module).encode("utf-8"), digest_size=16).hexdigest()


def _statements(node: ast.AST) -> int:
    return sum(1 for n in ast.walk(node) if isinstance(n, ast.stmt))


def _is_record(node: ast.ClassDef) -> bool:
    """A class that only declares fields, which every other such class matches.

    ``Finding``, ``EntryPoint`` and ``Waiver`` are unrelated types that happen to hold the
    same number of annotated fields, so they hash identically and were reported as copies
    of each other. Structural identity means nothing for a declaration - the shape *is* the
    field count. Only a class with real statements in it can be a clone.
    """
    return not any(
        isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.If, ast.For, ast.While))
        for stmt in node.body
    )


def _fragments_in(tree: ast.Module, module: str, path: str) -> list[Fragment]:
    found: list[Fragment] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            size = _statements(node)
            if size >= MIN_STATEMENTS and not _is_record(node):
                found.append(
                    Fragment(
                        _digest(node.body), CLASS, f"{module}.{node.name}", path, node.lineno, size
                    )
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            size = _statements(node)
            if size >= MIN_STATEMENTS:
                found.append(
                    Fragment(
                        _digest(node.body),
                        FUNCTION,
                        f"{module}.{node.name}",
                        path,
                        node.lineno,
                        size,
                    )
                )
    return found


def _blocks_in(tree: ast.Module, module: str, path: str) -> list[Fragment]:
    """Runs of consecutive sibling statements - the unrolled loop case."""
    found: list[Fragment] = []
    for parent in ast.walk(tree):
        body = getattr(parent, "body", None)
        if not isinstance(body, list) or len(body) < MIN_BLOCK * 2:
            continue
        statements = [s for s in body if isinstance(s, ast.stmt)]
        for start in range(len(statements) - MIN_BLOCK + 1):
            window = statements[start : start + MIN_BLOCK]
            found.append(
                Fragment(
                    _digest(window),
                    BLOCK,
                    f"{module}:{window[0].lineno}",
                    path,
                    window[0].lineno,
                    MIN_BLOCK,
                )
            )
    return found


def find(parsed: dict[str, tuple[ast.Module, str]], *, blocks: bool = False) -> list[Clone]:
    """Every shape that occurs more than once, largest first.

    ``blocks`` is off by default: the sliding window over sibling statements is quadratic in
    body length and finds mostly noise in well-factored code. Turn it on when looking for
    the loop somebody wrote out by hand.
    """
    fragments: list[Fragment] = []
    for module, (tree, path) in sorted(parsed.items()):
        fragments += _fragments_in(tree, module, path)
        if blocks:
            fragments += _blocks_in(tree, module, path)

    grouped: dict[str, list[Fragment]] = defaultdict(list)
    for fragment in fragments:
        grouped[fragment.digest].append(fragment)

    clones = [
        Clone(digest, sites[0].kind, sites[0].size, tuple(sorted(sites)))
        for digest, sites in grouped.items()
        if len({(s.qualified, s.line) for s in sites}) > 1
    ]
    return sorted(clones, key=lambda c: (-c.size, -len(c.sites), c.digest))


def duplication_rate(parsed: dict[str, tuple[ast.Module, str]]) -> float:
    """Fraction of definitions that are a copy of another definition.

    A ratio rather than a count, so it does not drift with repository size and cannot be
    improved by splitting code into more pieces - which is what sank every class-count
    metric considered before this one.
    """
    fragments = [f for _m, (t, p) in sorted(parsed.items()) for f in _fragments_in(t, p, p)]
    if not fragments:
        return 0.0
    shapes = len({f.digest for f in fragments})
    return 1.0 - shapes / len(fragments)


#: What a duplicate means, once reachability says where the copies live.
ACROSS_FEATURES: Final = "across features"
WITHIN_FEATURE: Final = "within one feature"
WITH_DEAD_COPY: Final = "one copy is unreachable"


def verdict(clone: Clone, feature_local: dict[str, frozenset[str]], dead: frozenset[str]) -> str:
    """How seriously to take one clone, which only reachability can say.

    Two copies in independent features is the complaint this plugin was built for: logic
    that is genuinely separate, duplicated because nobody saw the other copy. Two in the
    same feature is a note - it may be the right call, since merging things that change for
    different reasons creates worse coupling than it removes. A copy nothing reaches is not
    a refactor at all; it is a deletion.
    """
    names = {site.qualified for site in clone.sites}
    if names & dead:
        return WITH_DEAD_COPY
    owners = {owner for owner, owned in feature_local.items() if names & owned}
    return ACROSS_FEATURES if len(owners) > 1 else WITHIN_FEATURE
