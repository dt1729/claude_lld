"""Project a contract's Preconditions table into conditions a tool can execute.

A contract lives in ``docs/contracts/*.md``, where nothing can run it. CrossHair reads
conditions out of a function's own docstring. Same facts, two places, and only one of them
is checkable - so this module generates the second from the first.

**The verdict decides which condition is correct**, and that is the whole design. CrossHair's
``pre:`` means *assume this holds, do not explore outside it*:

- ``reject`` emits ``raises:``. The function is total; outside the range it raises on
  purpose. A ``pre:`` here would tell CrossHair to skip the exact inputs the guard exists
  for, hiding the bug the guard was written to catch.
- ``clamp`` emits nothing. Total, defined everywhere, raises nothing.
- ``propagate`` emits ``pre:``. The one case where a precondition is literally true: the
  function is undefined outside the range and the caller carries it.

A projection reproduces a claim; it cannot improve one. CrossHair found a counterexample
*inside* a hand-written precondition (``5e-324`` satisfies ``0 < hfov_deg < 180`` and still
divides by zero). That is the insufficient-guard case and no generator reaches it.

See docs/proposals/001a-where-contracts-execute.md.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Final

from contracts import Precondition, contract_path_for, parse_preconditions
from findings import JUDGE, Finding

#: Delimiters for the generated block, so the boundary between generated and hand-written is
#: visible in the file rather than remembered. Same discipline as the contract's own
#: ``<!-- derived -->`` markers, in the only comment syntax a docstring has.
OPEN: Final = ".. derived from {contract} - regenerate, do not edit"
CLOSE: Final = ".. end derived"

_OPEN_ANY: Final = re.compile(r"^\s*\.\. derived from .+ - regenerate, do not edit\s*$")
_CLOSE_ANY: Final = re.compile(r"^\s*\.\. end derived\s*$")

#: Rule 39. A module whose projected conditions no longer match its contract.
STALE_CONDITIONS: Final = 39


_LEADING_OP: Final = re.compile(r"^[<>=!]")
_EXCEPTION_NAME: Final = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception))\b")


def _error_name(row: Precondition) -> str:
    """The exception a reject row names, defaulting to ValueError when it names none.

    The name lives in the verdict cell - ``reject - InvalidFovError naming the value`` -
    not in the condition, so the whole cell is searched before falling back.
    """
    match = _EXCEPTION_NAME.search(row.detail) or _EXCEPTION_NAME.search(row.must_satisfy)
    return match.group(1) if match else "ValueError"


def expression_for(row: Precondition) -> str | None:
    """The condition as a Python expression, or None when it is prose.

    A table may say ``> 0``, which is shorthand for ``<parameter> > 0``, or it may say
    "open, not already consumed". The first is projectable and the second is not: emitting
    an unparseable ``pre:`` would hand CrossHair a syntax error instead of a claim. Prose
    preconditions stay in the contract where a person reads them.
    """
    text = row.must_satisfy.strip()
    if not text:
        return None
    if _LEADING_OP.match(text):
        text = f"{row.parameter} {text}"
    try:
        ast.parse(text, mode="eval")
    except SyntaxError:
        return None
    return text


def conditions_for(row: Precondition) -> list[str]:
    """The condition lines one Preconditions row produces, which may be none.

    The verdict decides the form. See this module's docstring: a ``pre:`` on a reject row
    would tell CrossHair to skip the inputs the guard exists for.
    """
    if row.verdict == "reject":
        return [f"raises: {_error_name(row)}"]
    if row.verdict == "propagate":
        expression = expression_for(row)
        return [f"pre: {expression}"] if expression else []
    return []


def render_conditions(rows: list[Precondition], contract: Path | str) -> list[str]:
    """The whole generated block for one function, markers included.

    Empty when no row produces a condition: a block saying nothing is noise in a docstring
    that a reader has to scroll past.
    """
    lines: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for line in conditions_for(row):
            if line not in seen:
                seen.add(line)
                lines.append(line)
    if not lines:
        return []
    contract_path = contract.as_posix() if isinstance(contract, Path) else contract
    return [OPEN.format(contract=contract_path), *lines, CLOSE]


def _docstring_node(func: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Constant | None:
    """The docstring's own node, which is where the line numbers come from."""
    if not func.body:
        return None
    first = func.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first.value
    return None


def existing_block(docstring: str) -> list[str]:
    """The condition lines already inside the markers, stripped of indentation."""
    lines = docstring.splitlines()
    opened = next((i for i, line in enumerate(lines) if _OPEN_ANY.match(line)), None)
    if opened is None:
        return []
    closed = next((i for i in range(opened + 1, len(lines)) if _CLOSE_ANY.match(lines[i])), None)
    if closed is None:
        return []
    return [line.strip() for line in lines[opened + 1 : closed] if line.strip()]


def _public_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Module-level public functions. Methods are reached through their class."""
    out: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(
            "_"
        ):
            out.append(node)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            out.extend(
                m
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not m.name.startswith("_")
            )
    return out


def _parameter_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = func.args
    every = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg:
        every.append(args.vararg)
    if args.kwarg:
        every.append(args.kwarg)
    return {a.arg for a in every} - {"self", "cls"}


def _rows_for(
    func: ast.FunctionDef | ast.AsyncFunctionDef, rows: list[Precondition]
) -> list[Precondition]:
    """The rows that are about this function's parameters, and no others.

    A row may be written ``hfov_deg`` or ``intrinsics_from_fov.hfov_deg``; the qualified
    form keeps two functions sharing a parameter name separable. An unqualified row applies
    only when the function actually takes that parameter - a contract covers a whole module,
    so without this check every function in it inherits every other function's conditions.
    ``cfg.threshold`` is matched on ``cfg``, the parameter the caller passes.
    """
    qualified = [r for r in rows if r.parameter.startswith(f"{func.name}.")]
    if qualified:
        return qualified
    taken = _parameter_names(func)
    return [r for r in rows if r.parameter.split(".")[0] in taken]


def stale(source: str, rows: list[Precondition], contract: Path | str) -> list[Finding]:
    """Where a module's projected conditions no longer match its contract.

    A module with no block anywhere is a migration state, not a defect - the same rule the
    derived contract blocks follow. Only a block that exists and disagrees is reported.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    found: list[Finding] = []
    for func in _public_functions(tree):
        node = _docstring_node(func)
        if node is None:
            continue
        current = existing_block(str(node.value))
        if not current:
            continue
        expected = render_conditions(_rows_for(func, rows), contract)[1:-1]
        if current != expected:
            found.append(
                Finding(
                    rule=STALE_CONDITIONS,
                    name=func.name,
                    line=node.lineno,
                    verdict=JUDGE,
                    message=(
                        f"{func.name}: the generated conditions no longer match the "
                        f"contract. Has {current or 'nothing'}, the contract says "
                        f"{expected or 'nothing'}. Regenerate rather than edit."
                    ),
                )
            )
    return found


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _without_block(lines: list[str]) -> list[str]:
    """The docstring's own lines, with any previously generated block removed."""
    opened = next((i for i, line in enumerate(lines) if _OPEN_ANY.match(line)), None)
    if opened is None:
        return lines
    closed = next((i for i in range(opened + 1, len(lines)) if _CLOSE_ANY.match(lines[i])), None)
    if closed is None:
        return lines
    kept = lines[:opened] + lines[closed + 1 :]
    while kept and not kept[-1].strip():
        kept.pop()
    return kept


def project(source: str, rows: list[Precondition], contract: Path | str) -> str:
    """The module's source with every public function's condition block inserted or refreshed.

    Returns new text; it writes nothing. A function with no docstring is left alone - this
    generates a contract's executable half, not a docstring the author never wrote.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, str]] = []
    for func in _public_functions(tree):
        node = _docstring_node(func)
        if node is None or node.end_lineno is None:
            continue
        raw = lines[node.lineno - 1 : node.end_lineno]
        rendered = _rewrite_docstring(raw, render_conditions(_rows_for(func, rows), contract))
        if rendered is not None:
            edits.append((node.lineno - 1, node.end_lineno, rendered))

    for start, end, text in reversed(edits):
        lines[start:end] = [text]
    return "".join(lines)


def _rewrite_docstring(raw_lines: list[str], block: list[str]) -> str | None:
    """One docstring re-rendered around the generated block, or None when nothing changes.

    Works on the source text rather than on the parsed string, so every line keeps the
    indentation its author gave it. Rendering from the parsed string re-indents the body
    against the opening quote and shifts the whole docstring on each run.
    """
    original = "".join(raw_lines)
    raw = original.rstrip("\n")
    quote = '"""' if '"""' in raw else "'''"
    indent = _indent_of(raw_lines[0])
    start = raw.index(quote) + len(quote)
    end = raw.rindex(quote)
    if end < start:
        return None

    kept = _without_block(raw[start:end].splitlines() or [""])
    while kept and not kept[-1].strip():
        kept.pop()
    if not kept:
        kept = [""]
    if block:
        kept = [*kept, "", *[f"{indent}{line}" for line in block]]

    if len(kept) == 1:
        rendered = f"{indent}{quote}{kept[0].strip()}{quote}\n"
    else:
        body = "\n".join(line.rstrip() for line in kept[1:])
        rendered = f"{indent}{quote}{kept[0].rstrip()}\n{body}\n{indent}{quote}\n"
    return rendered if rendered != original else None


def main(argv: list[str] | None = None) -> int:
    """Project a module's contract into its docstrings, or report where they disagree."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path)
    parser.add_argument("--src-root", default="src")
    parser.add_argument("--check", action="store_true", help="fail if a block is stale")
    parser.add_argument(
        "--write",
        action="store_true",
        help="edit the module in place; without it the projection is printed",
    )
    args = parser.parse_args(argv)

    contract = contract_path_for(args.module, args.src_root)
    if not contract.exists():
        print(f"no contract at {contract.as_posix()}", file=sys.stderr)
        return 2

    rows = parse_preconditions(contract.read_text(encoding="utf-8"))
    source = args.module.read_text(encoding="utf-8")

    if args.check:
        problems = stale(source, rows, contract)
        for finding in problems:
            print(f"{args.module.as_posix()}:{finding.line}: {finding.message}")
        if not problems:
            print(f"{args.module.as_posix()}: conditions are current")
        return 1 if problems else 0

    updated = project(source, rows, contract)
    if updated == source:
        print(f"{args.module.as_posix()}: already current")
        return 0
    if not args.write:
        # The projection edits a file the author owns, which no other generator here does.
        # Printing by default makes that an explicit choice rather than a silent one.
        print(updated)
        return 0
    args.module.write_text(updated, encoding="utf-8")
    print(f"{args.module.as_posix()}: conditions written from {contract.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
