"""Derive, from a module's AST, the tests that must exist for it.

This is the half the prose could not do. A contract's Tests section is written by hand and
goes stale; the source is the thing that is actually true. Every public name, every raise,
and every guard that produces one is an obligation the suite owes, read off the syntax tree
rather than off someone's memory of what the module does.

Obligations are facts about the code. They say what must be tested and why. They never say
what to assert - a generated assertion is a shallow test with a passing grade, which is the
failure this plugin exists to prevent. The AST supplies the obligation; a reader supplies
the judgment.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Final

#: Comparison operators that mark a guard boundary, and how the boundary reads.
BOUNDARY_OPS: Final[dict[type[ast.cmpop], str]] = {
    ast.Lt: "just below",
    ast.LtE: "at and just below",
    ast.Gt: "just above",
    ast.GtE: "at and just above",
    ast.Eq: "equal to",
    ast.NotEq: "not equal to",
}

PUBLIC_NAME: Final = "public-name"
RAISE: Final = "raise"
BOUNDARY: Final = "boundary"


@dataclass(frozen=True, slots=True)
class Obligation:
    """One test the suite owes, and the fact in the source that demands it."""

    kind: str
    target: str
    line: int
    reason: str
    suggested_name: str

    def as_stub(self) -> str:
        """A failing test stub. Red by construction, so it cannot pass unwritten."""
        return (
            f"def {self.suggested_name}() -> None:\n"
            f'    """{self.reason}\n\n'
            f"    Obligation: {self.kind} at line {self.line} of the module under test.\n"
            f'    """\n'
            f'    pytest.fail("not written yet")\n'
        )


def _snake(text: str) -> str:
    """A readable test-name fragment from an identifier or dotted name."""
    out: list[str] = []
    for index, char in enumerate(text.replace(".", "_")):
        if char.isupper() and index and out and out[-1] != "_":
            out.append("_")
        out.append(char.lower())
    return "".join(out)


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _public_defs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and _is_public(node.name)
    ]


def _raised_name(node: ast.Raise) -> str | None:
    """The exception type a raise statement names, when it names one."""
    exc = node.exc
    if isinstance(exc, ast.Call):
        exc = exc.func
    if isinstance(exc, ast.Name):
        return exc.id
    if isinstance(exc, ast.Attribute):
        return exc.attr
    return None


def _guard_of(tree: ast.Module, raise_node: ast.Raise) -> ast.Compare | None:
    """The comparison guarding a raise, when it sits directly inside one.

    Only a direct `if <compare>: raise` counts. A raise reached through several conditions
    has no single boundary, and inventing one would put a number in a test name that the
    code does not actually turn on.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        if any(stmt is raise_node for stmt in node.body):
            return node.test
    return None


def _describe_boundary(compare: ast.Compare) -> tuple[str, str] | None:
    """The subject and the threshold of a guard, as text for a test name and reason."""
    if len(compare.ops) != 1 or len(compare.comparators) != 1:
        return None
    op = type(compare.ops[0])
    if op not in BOUNDARY_OPS:
        return None
    right = compare.comparators[0]
    # str and bytes thresholds are excluded: a boundary is a number, and formatting bytes
    # into a test name would write b'...' there.
    if not isinstance(right, ast.Constant) or isinstance(right.value, (str, bytes)):
        return None

    left = compare.left
    if isinstance(left, ast.Attribute):
        subject = left.attr
    elif isinstance(left, ast.Name):
        subject = left.id
    else:
        return None
    return subject, f"{BOUNDARY_OPS[op]} {right.value}"


def _public_methods(cls: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        n
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public(n.name)
    ]


def _name_obligations(tree: ast.Module) -> list[Obligation]:
    """One obligation per name a caller can reach."""
    found: list[Obligation] = []
    for node in _public_defs(tree):
        found.append(
            Obligation(
                kind=PUBLIC_NAME,
                target=node.name,
                line=node.lineno,
                reason=f"{node.name} is public, so a caller can reach it and a test must too.",
                suggested_name=f"test_{_snake(node.name)}_behaves_as_documented",
            )
        )
        if isinstance(node, ast.ClassDef):
            for method in _public_methods(node):
                qualified = f"{node.name}.{method.name}"
                found.append(
                    Obligation(
                        kind=PUBLIC_NAME,
                        target=qualified,
                        line=method.lineno,
                        reason=f"{qualified} is part of the public surface of {node.name}.",
                        suggested_name=f"test_{_snake(qualified)}_behaves_as_documented",
                    )
                )
    return found


def _raise_obligations(tree: ast.Module) -> list[Obligation]:
    """One obligation per exception the module raises, plus its guard boundary."""
    found: list[Obligation] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        name = _raised_name(node)
        if name is None or name in seen:
            continue
        seen.add(name)
        found.append(
            Obligation(
                kind=RAISE,
                target=name,
                line=node.lineno,
                reason=f"The module raises {name}; a test must expect it, or nothing proves "
                "the failure path works.",
                suggested_name=f"test_raises_{_snake(name)}",
            )
        )

        guard = _guard_of(tree, node)
        described = _describe_boundary(guard) if guard is not None else None
        if described is not None:
            subject, threshold = described
            found.append(
                Obligation(
                    kind=BOUNDARY,
                    target=f"{subject} {threshold}",
                    line=node.lineno,
                    reason=f"{name} is raised when {subject} is {threshold}; the value either "
                    "side of that threshold is where off-by-one lives.",
                    suggested_name=f"test_{_snake(subject)}_boundary_is_respected",
                )
            )
    return found


def obligations(source: str) -> list[Obligation]:
    """Every test this module owes, ordered by the line that demands it.

    Raises SyntaxError if the source does not parse.
    """
    tree = ast.parse(source)
    found = _name_obligations(tree) + _raise_obligations(tree)
    return sorted(found, key=lambda o: (o.line, o.kind, o.target))


def public_constructors(source: str) -> list[tuple[str, list[str]]]:
    """Public classes and the parameter names their constructors take.

    Used by the sandbox generator, which needs to know what to build and with what, not
    what the result should be.
    """
    tree = ast.parse(source)
    out: list[tuple[str, list[str]]] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not _is_public(node.name):
            continue
        fields = [
            stmt.target.id
            for stmt in node.body
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
        ]
        # __init__ is private by name and public by role, so it is searched for among all
        # methods rather than through the public filter, which excluded it.
        init = next(
            (
                m
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == "__init__"
            ),
            None,
        )
        if init is not None:
            fields = [a.arg for a in init.args.args if a.arg != "self"]
        out.append((node.name, fields))
    return out
