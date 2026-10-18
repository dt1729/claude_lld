"""Detect weak tests: rules 27-36 of skills/design-patterns/ANTI-PATTERNS.md.

A separate detector from ``detect_patterns`` because it reads the files that one excludes,
and because a test rule changes for different reasons than a structure rule. Both emit the
same Finding, so the gate and the pre-commit hook treat them identically.

These rules exist because the first module this plugin built passed every gate and still had
a brittle assertion in its tests (docs/phase-4-review.md, defect 6). A suite nothing checks
is a suite that proves whatever it happens to prove.

Usage:
    python detect_tests.py <path>... [--json]
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
from typing import Final, TypeGuard

sys.path.insert(0, str(Path(__file__).resolve().parent))

from findings import BLOCK, JUDGE, Finding, format_report
from logsetup import configure

log = logging.getLogger("lld.tests")

#: A substring assertion shorter than this proves almost nothing: "1" matches any message
#: containing a 1, including the wrong one.
MIN_SUBSTRING = 4

#: Below this, a suite with no failure case says nothing; above it, the absence is a signal.
MIN_SUITE_FOR_FAILURE_CASE = 5

MOCK_NAMES: Final = frozenset({"Mock", "MagicMock", "AsyncMock", "patch", "patch.object"})
MOCK_ASSERTIONS: Final = frozenset(
    {
        "assert_called",
        "assert_called_once",
        "assert_called_with",
        "assert_called_once_with",
        "assert_any_call",
        "assert_has_calls",
        "assert_not_called",
    }
)

#: Calls that mean a test exercises a failure, not just the happy path.
FAILURE_MARKERS: Final = frozenset({"raises", "warns", "fail", "xfail"})

#: Words in a test name that say it covers a failure. Not every failure is an exception:
#: a test asserting that a detector reports a problem exercises one without ever raising.
FAILURE_WORDS: Final = frozenset(
    {
        "blocks",
        "refused",
        "refuses",
        "rejected",
        "rejects",
        "invalid",
        "error",
        "raises",
        "fails",
        "failure",
        "denied",
        "denies",
        "missing",
        "unparseable",
        "not_enough",
        "too_many",
        "empty",
        "wrong",
        "bad",
    }
)


def _is_test(node: ast.AST) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    """A test function. A TypeGuard so callers get the narrowed type, not a cast."""
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
        "test"
    )


def _tests(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if _is_test(n)]


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _calls(node: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def _asserts(node: ast.AST) -> list[ast.Assert]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Assert)]


def _exercises_failure(node: ast.AST) -> bool:
    """Whether this test reaches a failure path rather than only the happy one.

    Either it raises, or its name says it covers one. The name check exists because a test
    asserting that a detector reports a problem exercises a failure without pytest.raises,
    and flagging those suites was this rule's first false positive.
    """
    if any(_call_name(c) in FAILURE_MARKERS for c in _calls(node)):
        return True
    name = getattr(node, "name", "")
    return any(word in name for word in FAILURE_WORDS)


def rule_27_test_asserts_nothing(tree: ast.Module) -> list[Finding]:
    """A test with no assertion passes whatever the code does."""
    found: list[Finding] = []
    for test in _tests(tree):
        if _asserts(test) or _exercises_failure(test):
            continue
        # A test may delegate its assertion to a helper; a call to something named
        # check/verify/assert is taken as that, since the helper carries the assert.
        delegates = any(
            _call_name(c).startswith(("check", "verify", "assert", "expect")) for c in _calls(test)
        )
        if not delegates:
            found.append(
                Finding(
                    27,
                    test.name,
                    test.lineno,
                    BLOCK,
                    "test asserts nothing: it passes whatever the code does",
                )
            )
    return found


def rule_28_no_failure_case(tree: ast.Module) -> list[Finding]:
    """A suite of only happy paths has probably never seen the code fail.

    Judgment, not a block. Whether a module has a failure worth testing is a fact about the
    module, which this detector cannot see, and a module that raises nothing legitimately
    has no raises in its suite. Suites that assert a detector reports a problem also test
    failure without ever calling pytest.raises.
    """
    tests = _tests(tree)
    if len(tests) < MIN_SUITE_FOR_FAILURE_CASE or any(_exercises_failure(t) for t in tests):
        return []
    return [
        Finding(
            28,
            "<module>",
            tests[0].lineno,
            JUDGE,
            f"{len(tests)} tests and no pytest.raises anywhere: confirm this module has no "
            "failure worth testing, or add the one it is supposed to handle",
        )
    ]


def rule_29_weak_substring_assertion(tree: ast.Module) -> list[Finding]:
    """A short substring match passes against the wrong message as easily as the right one."""
    found: list[Finding] = []
    for test in _tests(tree):
        for node in ast.walk(test):
            if not isinstance(node, ast.Compare) or not node.ops:
                continue
            if not isinstance(node.ops[0], ast.In):
                continue
            left = node.left
            if (
                isinstance(left, ast.Constant)
                and isinstance(left.value, str)
                and len(left.value.strip()) < MIN_SUBSTRING
            ):
                found.append(
                    Finding(
                        29,
                        test.name,
                        node.lineno,
                        JUDGE,
                        f"assertion matches the substring {left.value!r}, which would also "
                        "pass against a wrong message; assert the whole message or a field",
                    )
                )
    return found


def rule_30_sleep_in_test(tree: ast.Module) -> list[Finding]:
    """A sleeping test is a flaky test with a timer attached."""
    return [
        Finding(
            30,
            "sleep",
            call.lineno,
            BLOCK,
            "sleep in a test: wait on the condition, or inject the clock",
        )
        for call in _calls(tree)
        if _call_name(call) == "sleep"
    ]


def rule_31_deep_import(tree: ast.Module) -> list[Finding]:
    """Tests cross the same seam callers do, or they test something callers cannot reach."""
    found: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        parts = node.module.split(".")
        private = [p for p in parts if p in ("lib", "internal", "_internal", "impl")]
        if private and node.level == 0:
            found.append(
                Finding(
                    31,
                    node.module,
                    node.lineno,
                    BLOCK,
                    "test reaches past the entry-point boundary into a private subpackage: "
                    "import the module that owns the public name",
                )
            )
    return found


def rule_32_more_mocks_than_assertions(tree: ast.Module) -> list[Finding]:
    """When the mocks outnumber the assertions the subject under test is the mock."""
    found: list[Finding] = []
    for test in _tests(tree):
        mocks = sum(1 for c in _calls(test) if _call_name(c) in MOCK_NAMES)
        checks = len(_asserts(test))
        if mocks > max(checks, 1):
            found.append(
                Finding(
                    32,
                    test.name,
                    test.lineno,
                    JUDGE,
                    f"{mocks} mocks against {checks} assertions: prefer a real collaborator, or "
                    "a fake that satisfies the seam",
                )
            )
    return found


def rule_33_asserts_on_the_mock(tree: ast.Module) -> list[Finding]:
    """Asserting a call happened tests the implementation, not the behaviour."""
    found: list[Finding] = []
    for test in _tests(tree):
        for call in _calls(test):
            if _call_name(call) in MOCK_ASSERTIONS:
                found.append(
                    Finding(
                        33,
                        test.name,
                        call.lineno,
                        JUDGE,
                        f"{_call_name(call)} asserts that a call happened, not that the "
                        "behaviour is right: assert on the result or the observable effect",
                    )
                )
    return found


def rule_36_name_says_and(tree: ast.Module) -> list[Finding]:
    """A test named for two things fails for two reasons."""
    return [
        Finding(
            36,
            test.name,
            test.lineno,
            JUDGE,
            "test name joins two things with 'and': if they are two behaviours, split "
            "it so a failure names the one that broke",
        )
        for test in _tests(tree)
        if "_and_" in test.name
    ]


RULES: Final = (
    rule_27_test_asserts_nothing,
    rule_28_no_failure_case,
    rule_29_weak_substring_assertion,
    rule_30_sleep_in_test,
    rule_31_deep_import,
    rule_32_more_mocks_than_assertions,
    rule_33_asserts_on_the_mock,
    rule_36_name_says_and,
)


def detect(source: str, path: Path) -> list[Finding]:
    """Return every finding in a test module, ordered by line.

    Raises SyntaxError if the source does not parse; callers decide whether an unparseable
    write is a failure or simply not yet their concern.
    """
    tree = ast.parse(source)
    findings = sorted((f for rule in RULES for f in rule(tree)), key=lambda f: (f.line, f.rule))
    log.debug("%s: %d findings across %d tests", path.as_posix(), len(findings), len(_tests(tree)))
    return findings


def is_test_file(path: Path) -> bool:
    """Whether this detector governs the path."""
    return path.suffix == ".py" and (
        path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or "tests" in path.as_posix().split("/")
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="+")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING, ERROR")
    args = parser.parse_args(argv)
    configure(level=args.log_level, log_file=None)

    blocked = False
    everything: list[Finding] = []
    for path in args.paths:
        if not is_test_file(path):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"cannot read {path}: {exc}", file=sys.stderr)
            return 2
        try:
            findings = detect(source, path)
        except SyntaxError as exc:
            print(f"{path} does not parse: {exc}", file=sys.stderr)
            return 2
        if findings and not args.json:
            print(f"{path.as_posix()}:")
            print(format_report(findings))
        everything.extend(findings)
        blocked = blocked or any(f.verdict == BLOCK for f in findings)

    if args.json:
        print(json.dumps([asdict(f) for f in everything], indent=2))
    elif not everything:
        print("no test anti-patterns detected")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
