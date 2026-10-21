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
import re
import textwrap
from dataclasses import dataclass
from typing import Final

from contracts import Precondition

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

#: An obligation that comes from the contract rather than from the code. Every other kind
#: here reads the syntax tree and asks "what does this module do?". This one reads the
#: Preconditions table and asks "what did the author promise it refuses?" - which is the
#: question the source cannot answer, because a guard that was never written leaves no trace.
PRECONDITION: Final = "precondition"

_NUMBER: Final = re.compile(r"-?\d+(?:\.\d+)?")


def _fail_call(message: str) -> str:
    """``pytest.fail(...)``, wrapped so the generated file passes the linter it ships with.

    A long message becomes implicitly concatenated string parts rather than one long line;
    a backslash continuation inside a string literal would change the message itself.
    """
    if len(message) <= 70:
        return f'    pytest.fail("{message}")\n'
    parts = textwrap.wrap(message, width=70)
    body = "\n".join(f'        "{part}{" " if part is not parts[-1] else ""}"' for part in parts)
    return f"    pytest.fail(\n{body}\n    )\n"


@dataclass(frozen=True, slots=True)
class Obligation:
    """One test the suite owes, and the fact in the source that demands it."""

    kind: str
    target: str
    line: int
    reason: str
    suggested_name: str
    #: What the author has to do, when the obligation knows. A contract row knows the
    #: condition to violate and the values worth trying; "not written yet" does not.
    instruction: str = ""

    def as_stub(self) -> str:
        """A failing test stub. Red by construction, so it cannot pass unwritten.

        Wrapped to the line length this plugin configures in the repositories it seeds. A
        contract row carries a real condition, and unwrapped it ran past 100 characters -
        a generator whose output fails the linter the same generator installed is the
        system contradicting itself, which is incident 004.

        The scaffolded file still reports F401 on its import line: the names are imported
        for the tests the author is about to write, and no stub uses them yet. That is
        older than this method and is not fixed here.
        """
        where = (
            f"the contract's Preconditions table, row {self.line + 1}"
            if self.kind == PRECONDITION
            else f"line {self.line} of the module under test"
        )
        summary = textwrap.fill(self.reason, width=94, subsequent_indent="    ")
        return (
            f"def {self.suggested_name}() -> None:\n"
            f'    """{summary}\n\n'
            f"    Obligation: {self.kind} from {where}.\n"
            f'    """\n'
            f"{_fail_call(self.instruction or 'not written yet')}"
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


def _as_claim(parameter: str, condition: str) -> str:
    """``> 0`` is shorthand; spelled out it is ``width > 0``, which reads as a claim."""
    text = condition.strip()
    return f"{parameter} {text}" if text[:1] in "<>=!" else text


def boundary_hints(condition: str) -> list[str]:
    """The numbers in a condition, which are where a violating value lives.

    ``0 < hfov_deg < 180`` hands back ``0`` and ``180``. These are hints in a failure
    message, never generated arguments: the stub still refuses to pass until a person picks
    the value and writes the assertion.
    """
    return _NUMBER.findall(condition)


def precondition_obligations(rows: list[Precondition]) -> list[Obligation]:
    """One rejection test per parameter the contract promises to refuse.

    Only ``reject`` rows produce one. ``clamp`` substitutes rather than raises, so a test
    asserting an exception would be wrong; ``propagate`` is the author stating that nothing
    is checked, and a test for unchecked behaviour tests the caller.
    """
    found: list[Obligation] = []
    for index, row in enumerate(rows):
        if row.verdict != "reject":
            continue
        condition = _as_claim(row.parameter, row.must_satisfy)
        hints = boundary_hints(row.must_satisfy)
        suffix = f" (the boundary values are {', '.join(hints)})" if hints else ""
        found.append(
            Obligation(
                kind=PRECONDITION,
                target=row.parameter,
                line=index,
                reason=(
                    f"The contract promises {row.parameter} is rejected unless "
                    f"{condition}. Nothing proves that until a test violates it."
                ),
                suggested_name=f"test_rejects_{_snake(row.parameter)}",
                instruction=(
                    f"pass a {row.parameter} violating {condition}{suffix} and assert the rejection"
                ),
            )
        )
    return found


def obligations(source: str, preconditions: list[Precondition] | None = None) -> list[Obligation]:
    """Every test this module owes, ordered by the line that demands it.

    Contract obligations come first: they are numbered by table row rather than by source
    line, because the code they describe may not exist yet - which is the point.

    Raises SyntaxError if the source does not parse.
    """
    tree = ast.parse(source)
    from_contract = precondition_obligations(preconditions or [])
    from_code = _name_obligations(tree) + _raise_obligations(tree)
    return from_contract + sorted(from_code, key=lambda o: (o.line, o.kind, o.target))


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
