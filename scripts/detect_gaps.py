"""Rule 35: obligations the source demands that the suite does not meet.

The other detectors read one file. This one reads a module and its test module together,
because the question - is this behaviour tested - cannot be answered from either alone.

Obligations come from ``obligations.py``, which reads them off the source AST. A gap is an
obligation with nothing in the suite that plausibly covers it: the name is never mentioned,
or the exception is never expected. That is a weaker check than coverage, and deliberately
so - it answers "did anyone think about this" rather than "was this line executed", and the
two fail in different ways. Run both.

Usage:
    python detect_gaps.py src/shapes/square.py [--src-root src]
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from findings import BLOCK, JUDGE, Finding, format_report
from logsetup import configure
from obligations import BOUNDARY, PUBLIC_NAME, RAISE, Obligation, obligations

log = logging.getLogger("lld.gaps")


def test_path_for(module: Path) -> Path:
    """Where this module's suite lives."""
    return module.parent / "tests" / f"test_{module.name}"


def _names_mentioned(test_source: str) -> set[str]:
    """Every identifier and attribute the suite mentions, however it mentions it."""
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return set()
    mentioned: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            mentioned.add(node.id)
        elif isinstance(node, ast.Attribute):
            mentioned.add(node.attr)
        elif isinstance(node, ast.alias):
            mentioned.add(node.asname or node.name.split(".")[-1])
    return mentioned


def _expected_exceptions(test_source: str) -> set[str]:
    """Exception types the suite expects through pytest.raises."""
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return set()
    expected: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "raises" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Name):
            expected.add(first.id)
        elif isinstance(first, ast.Attribute):
            expected.add(first.attr)
        elif isinstance(first, ast.Tuple):
            for element in first.elts:
                if isinstance(element, ast.Name):
                    expected.add(element.id)
    return expected


def _is_met(obligation: Obligation, mentioned: set[str], expected: set[str]) -> bool:
    """Whether the suite plausibly covers this obligation."""
    if obligation.kind == RAISE:
        return obligation.target in expected
    if obligation.kind == PUBLIC_NAME:
        return all(part in mentioned for part in obligation.target.split("."))
    # A boundary is covered when its exception is expected somewhere; which value was used
    # is not visible from the AST, so this half is judgment.
    return True


def gaps(source: str, test_source: str) -> list[Finding]:
    """Obligations the suite does not meet, ordered by the line that demands them."""
    mentioned = _names_mentioned(test_source)
    expected = _expected_exceptions(test_source)

    found: list[Finding] = []
    for obligation in obligations(source):
        if obligation.kind == BOUNDARY:
            found.append(
                Finding(
                    35,
                    obligation.target,
                    obligation.line,
                    JUDGE,
                    f"{obligation.reason} Confirm a test uses the value either side of it; the "
                    "AST cannot see which value a test passed.",
                )
            )
            continue
        if _is_met(obligation, mentioned, expected):
            continue
        found.append(
            Finding(
                35,
                obligation.target,
                obligation.line,
                BLOCK,
                f"{obligation.reason} Nothing in the suite covers it; scaffold_tests.py will "
                f"write the stub ({obligation.suggested_name}).",
            )
        )
    return sorted(found, key=lambda f: (f.line, f.rule))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modules", type=Path, nargs="+")
    parser.add_argument("--src-root", default="src")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--log-level", default=None)
    args = parser.parse_args(argv)
    configure(level=args.log_level, log_file=None)

    blocked = False
    everything: list[Finding] = []
    for module in args.modules:
        if module.name.startswith("test_") or "tests" in module.as_posix().split("/"):
            continue
        try:
            source = module.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"cannot read {module}: {exc}", file=sys.stderr)
            return 2

        suite = test_path_for(module)
        test_source = suite.read_text(encoding="utf-8") if suite.exists() else ""
        try:
            found = gaps(source, test_source)
        except SyntaxError as exc:
            print(f"{module} does not parse: {exc}", file=sys.stderr)
            return 2

        if found and not args.json:
            print(f"{module.as_posix()} (suite: {suite.as_posix()}):")
            print(format_report(found))
        everything.extend(found)
        blocked = blocked or any(f.verdict == BLOCK for f in found)

    if args.json:
        print(json.dumps([asdict(f) for f in everything], indent=2))
    elif not everything:
        print("every obligation is met")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
