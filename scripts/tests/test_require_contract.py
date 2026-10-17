"""Behaviour of the PreToolUse gate, exercised through evaluate()."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from require_contract import count_public_names, evaluate, in_scope, resulting_source
from test_contracts import VALID as VALID_CONTRACT

CLEAN_MODULE = '''"""Turn raw frames into scored detections."""


def run(threshold: float) -> float:
    return threshold * 2
'''

BLOCKING_MODULE = '''"""Pool."""


class Pool:
    _instance = None

    @classmethod
    def instance(cls) -> "Pool":
        return cls._instance
'''

JUDGE_MODULE = '''"""Report."""


class ReportGenerator:
    def __init__(self, run: int) -> None:
        self._run = run

    def generate(self) -> str:
        return str(self._run)
'''


def decision(result: dict[str, Any]) -> str:
    return str(result["hookSpecificOutput"]["permissionDecision"])


def reason(result: dict[str, Any]) -> str:
    return str(result["hookSpecificOutput"].get("permissionDecisionReason", ""))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "docs" / "contracts").mkdir(parents=True)
    return tmp_path


def write_payload(project: Path, relative: str, content: str) -> dict[str, Any]:
    return {
        "tool_name": "Write",
        "cwd": str(project),
        "tool_input": {"file_path": str(project / relative), "content": content},
    }


def add_contract(project: Path, name: str, text: str = VALID_CONTRACT) -> None:
    (project / "docs" / "contracts" / name).write_text(text, encoding="utf-8")


# --- scope ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "src/pkg/tests/test_thing.py",
        "src/pkg/conftest.py",
        "src/pkg/__init__.py",
        "scripts/tool.py",
        "src/pkg/notes.md",
        "docs/thing.py",
    ],
)
def test_paths_outside_the_gate_are_allowed(path: str) -> None:
    assert not in_scope(Path(path), "src")


def test_a_package_module_is_in_scope() -> None:
    assert in_scope(Path("src/pkg/thing.py"), "src")


def test_out_of_scope_write_is_allowed(project: Path) -> None:
    payload = write_payload(project, "scripts/tool.py", BLOCKING_MODULE)
    assert decision(evaluate(payload, project)) == "allow"


def test_a_tool_the_gate_does_not_watch_is_allowed(project: Path) -> None:
    payload = {"tool_name": "Read", "cwd": str(project), "tool_input": {"file_path": "x.py"}}
    assert decision(evaluate(payload, project)) == "allow"


# --- new modules need a contract --------------------------------------------------------


def test_new_module_without_a_contract_is_denied(project: Path) -> None:
    result = evaluate(write_payload(project, "src/pkg/thing.py", CLEAN_MODULE), project)
    assert decision(result) == "deny"
    assert "No contract" in reason(result)
    assert "docs/contracts/pkg.thing.md" in reason(result)


def test_new_module_with_an_invalid_contract_is_denied_with_the_errors(project: Path) -> None:
    add_contract(project, "pkg.thing.md", "# Contract: pkg.thing\n\n**Status:** draft\n")
    result = evaluate(write_payload(project, "src/pkg/thing.py", CLEAN_MODULE), project)
    assert decision(result) == "deny"
    assert "missing section: ## Responsibility" in reason(result)


def test_new_module_with_a_valid_contract_and_clean_code_is_allowed(project: Path) -> None:
    add_contract(project, "pkg.thing.md")
    assert (
        decision(evaluate(write_payload(project, "src/pkg/thing.py", CLEAN_MODULE), project))
        == "allow"
    )


def test_editing_an_existing_module_needs_no_contract(project: Path) -> None:
    """The gate catches modules born undesigned; it does not obstruct redesign."""
    target = project / "src" / "pkg" / "thing.py"
    target.write_text(CLEAN_MODULE, encoding="utf-8")
    payload = {
        "tool_name": "Edit",
        "cwd": str(project),
        "tool_input": {
            "file_path": str(target),
            "old_string": "threshold * 2",
            "new_string": "threshold * 3",
        },
    }
    assert decision(evaluate(payload, project)) == "allow"


# --- anti-pattern tiers -----------------------------------------------------------------


def test_blocking_finding_is_denied_and_says_it_cannot_be_waived(project: Path) -> None:
    add_contract(project, "pkg.thing.md")
    result = evaluate(write_payload(project, "src/pkg/thing.py", BLOCKING_MODULE), project)
    assert decision(result) == "deny"
    assert "cannot be waived" in reason(result)


def test_judge_finding_is_denied_with_waiver_instructions(project: Path) -> None:
    add_contract(project, "pkg.thing.md")
    result = evaluate(write_payload(project, "src/pkg/thing.py", JUDGE_MODULE), project)
    assert decision(result) == "deny"
    assert "need your judgment" in reason(result)
    assert "_waivers.md" in reason(result)


def test_recorded_waiver_lets_a_judge_finding_through(project: Path) -> None:
    add_contract(project, "pkg.thing.md")
    (project / "docs" / "contracts" / "_waivers.md").write_text(
        "| path | rule | date | reason |\n| --- | --- | --- | --- |\n"
        "| src/pkg/thing.py | 8 | 2026-10-17 | the instance is a seam, substituted in tests |\n",
        encoding="utf-8",
    )
    assert (
        decision(evaluate(write_payload(project, "src/pkg/thing.py", JUDGE_MODULE), project))
        == "allow"
    )


def test_a_waiver_does_not_excuse_a_blocking_finding(project: Path) -> None:
    add_contract(project, "pkg.thing.md")
    (project / "docs" / "contracts" / "_waivers.md").write_text(
        "| src/pkg/thing.py | 1 | 2026-10-17 | we like globals |\n",
        encoding="utf-8",
    )
    assert (
        decision(evaluate(write_payload(project, "src/pkg/thing.py", BLOCKING_MODULE), project))
        == "deny"
    )


def test_accumulated_waivers_are_called_out(project: Path) -> None:
    add_contract(project, "pkg.thing.md")
    rows = "".join(f"| src/pkg/thing.py | {rule} | 2026-10-17 | reason |\n" for rule in (2, 3, 10))
    (project / "docs" / "contracts" / "_waivers.md").write_text(rows, encoding="utf-8")
    result = evaluate(write_payload(project, "src/pkg/thing.py", JUDGE_MODULE), project)
    assert "already carries 3 waivers" in reason(result)


# --- resulting source -------------------------------------------------------------------


def test_edit_applies_one_replacement_by_default() -> None:
    assert resulting_source("Edit", {"old_string": "a", "new_string": "b"}, "aa") == "ba"


def test_edit_applies_all_replacements_when_asked() -> None:
    edit = {"old_string": "a", "new_string": "b", "replace_all": True}
    assert resulting_source("Edit", edit, "aa") == "bb"


def test_multiedit_applies_edits_in_order() -> None:
    edits = {
        "edits": [
            {"old_string": "a", "new_string": "b"},
            {"old_string": "b", "new_string": "c"},
        ]
    }
    assert resulting_source("MultiEdit", edits, "a") == "c"


def test_malformed_edit_yields_no_source() -> None:
    assert resulting_source("Edit", {"old_string": 3}, "a") is None


def test_unparseable_result_is_allowed_rather_than_guessed_at(project: Path) -> None:
    add_contract(project, "pkg.thing.md")
    assert (
        decision(evaluate(write_payload(project, "src/pkg/thing.py", "def broken(:\n"), project))
        == "allow"
    )


# --- depth cross-check ------------------------------------------------------------------


def test_public_names_are_counted_for_the_depth_check() -> None:
    src = "def a() -> None: ...\ndef _b() -> None: ...\nclass C: ...\n"
    assert count_public_names(src) == 2


def test_unparseable_source_counts_no_public_names() -> None:
    assert count_public_names("def broken(:") == 0


def test_junior_contract_is_refused_for_a_wide_new_module(project: Path) -> None:
    add_contract(
        project, "pkg.thing.md", VALID_CONTRACT.replace("**Depth:** senior", "**Depth:** junior")
    )
    wide = "".join(f"def f{i}() -> None:\n    pass\n\n\n" for i in range(4))
    result = evaluate(write_payload(project, "src/pkg/thing.py", wide), project)
    assert decision(result) == "deny"
    assert "junior" in reason(result)
