"""PreToolUse gate: refuse implementation writes that skipped the design step.

Reads a Claude Code hook payload on stdin and emits a permission decision on stdout. The
hook does not decide whether a change is worth designing; it decides whether the question
was answered. Three outcomes:

* **allow** - the path is out of scope, or a contract covers it and nothing blocks.
* **deny, not waivable** - a new module with no valid contract, or an anti-pattern the AST
  decides (ANTI-PATTERNS.md ``block`` tier).
* **deny, waivable** - a ``judge`` tier finding with no recorded judgment. The model either
  fixes the code or writes a waiver row and repeats the write.

Set ``LLD_GATE=off`` to disable it for a session. That is visible in the environment rather
than silent, which is the point: a gate nobody can see being bypassed is worse than none.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

from contracts import (
    WAIVER_FILE,
    contract_path_for,
    is_waived,
    parse_waivers,
    validate_contract,
    waiver_count,
    waiver_row,
)
from detect_patterns import BLOCK, JUDGE, detect
from logsetup import configure, log_path

log = logging.getLogger("lld.gate")

WATCHED_TOOLS: Final = frozenset({"Write", "Edit", "MultiEdit"})

#: Paths that carry no contract: tests, tooling, and anything generated.
EXCLUDED_PARTS: Final = frozenset({"tests", "test", "scripts", "migrations", "_generated", "generated"})
EXCLUDED_NAMES: Final = frozenset({"conftest.py", "setup.py", "__init__.py"})

#: Waivers on one module beyond this are evidence about the module, not the rule.
WAIVER_LIMIT: Final = 3


def _allow() -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def in_scope(path: Path, src_root: str) -> bool:
    """Whether the gate governs this path at all."""
    parts = path.as_posix().split("/")
    if path.suffix != ".py" or src_root not in parts:
        return False
    if path.name in EXCLUDED_NAMES:
        return False
    return not (set(parts) & EXCLUDED_PARTS)


def resulting_source(tool: str, tool_input: dict[str, Any], current: str) -> str | None:
    """The file content this call would produce, or None when it cannot be determined."""
    if tool == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None
    if tool == "Edit":
        old, new = tool_input.get("old_string"), tool_input.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        return current.replace(old, new, -1 if tool_input.get("replace_all") else 1)
    if tool == "MultiEdit":
        edits = tool_input.get("edits")
        if not isinstance(edits, list):
            return None
        out = current
        for edit in edits:
            old, new = edit.get("old_string"), edit.get("new_string")
            if not isinstance(old, str) or not isinstance(new, str):
                return None
            out = out.replace(old, new, -1 if edit.get("replace_all") else 1)
        return out
    return None


def count_public_names(source: str) -> int:
    """Top-level names a caller can reach, used to cross-check a declared depth."""
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    return sum(
        1 for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
    )


def _missing_contract_message(module: Path, contract: Path, errors: list[str]) -> str:
    if not errors:
        head = f"No contract for {module.as_posix()}."
    else:
        head = f"The contract at {contract.as_posix()} does not validate:\n" + "\n".join(
            f"  - {e}" for e in errors
        )
    return (
        f"{head}\n\n"
        f"This is a new module, so the design step has not happened yet. Write "
        f"{contract.as_posix()} following the new-module skill (step 2), then repeat this "
        f"write. Fill Responsibility, Interface, Seam, Dependencies, Errors, Tests and "
        f"Deletion test; if the Deletion test answer is 'nothing', do not create the module."
    )


def _findings_message(module: Path, blocking: list[Any], judging: list[Any], waivers: int) -> str:
    lines: list[str] = []
    if blocking:
        lines.append("These anti-patterns are decided by the AST and cannot be waived:")
        lines += [f"  line {f.line}: [{f.rule:02d}] {f.name} - {f.message}" for f in blocking]
    if judging:
        if lines:
            lines.append("")
        lines.append("These shapes need your judgment. Fix them, or record why they stand:")
        lines += [f"  line {f.line}: [{f.rule:02d}] {f.name} - {f.message}" for f in judging]
        lines.append("")
        lines.append(
            f"To record a judgment, append a row to {WAIVER_FILE} using the format "
            f"`| path | rule | date | reason |`, for example:"
        )
        example = judging[0]
        lines.append(f"  {waiver_row(module, example.rule, date.today().isoformat(), 'why this stands')}")
        lines.append("The reason is read by a human later, so make it one you would defend.")
    if waivers >= WAIVER_LIMIT:
        lines.append("")
        lines.append(
            f"{module.as_posix()} already carries {waivers} waivers. Repeated exceptions on "
            "one module are evidence about the module. Redesign it rather than adding another."
        )
    return "\n".join(lines)


def evaluate(payload: dict[str, Any], project_dir: Path, src_root: str = "src") -> dict[str, Any]:
    """Decide one tool call. Pure apart from reading the file, contract and ledger."""
    started = time.perf_counter()
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    raw_path = tool_input.get("file_path")
    if tool not in WATCHED_TOOLS or not isinstance(raw_path, str):
        log.debug("allow: %s is not a watched write", tool or "<no tool>")
        return _allow()

    absolute = Path(raw_path)
    try:
        module = absolute.relative_to(project_dir)
    except ValueError:
        module = absolute
    if not in_scope(module, src_root):
        log.info("allow %s %s: outside the gate's scope", tool, module.as_posix())
        return _allow()

    existed = absolute.exists()
    current = absolute.read_text(encoding="utf-8") if existed else ""
    source = resulting_source(tool, tool_input, current)
    if source is None:
        log.info("allow %s %s: resulting content could not be determined", tool, module.as_posix())
        return _allow()

    log.info("checking %s %s (%s)", tool, module.as_posix(), "existing" if existed else "new module")

    contract = project_dir / contract_path_for(module, src_root)
    contract_text = contract.read_text(encoding="utf-8") if contract.exists() else ""
    public_names = count_public_names(source)
    errors = validate_contract(contract_text, public_names=public_names) if contract_text else []
    log.debug(
        "contract %s: %s, %d public names, %d validation errors",
        contract_path_for(module, src_root).as_posix(),
        "present" if contract_text else "absent", public_names, len(errors),
    )

    if not existed and (not contract_text or errors):
        log.info(
            "deny %s: new module, contract %s (%.0f ms)",
            module.as_posix(), "invalid" if errors else "missing",
            (time.perf_counter() - started) * 1000,
        )
        return _deny(_missing_contract_message(module, contract_path_for(module, src_root), errors))

    try:
        findings = detect(source, module, src_root)
    except SyntaxError as exc:
        log.info("allow %s: content does not parse (%s)", module.as_posix(), exc.msg)
        return _allow()

    waiver_path = project_dir / WAIVER_FILE
    waivers = parse_waivers(waiver_path.read_text(encoding="utf-8")) if waiver_path.exists() else []

    blocking = [f for f in findings if f.verdict == BLOCK]
    waived = [f for f in findings if f.verdict == JUDGE and is_waived(waivers, module, f.rule)]
    judging = [f for f in findings if f.verdict == JUDGE and not is_waived(waivers, module, f.rule)]
    for finding in waived:
        log.info("rule %02d on %s stands: a judgment is recorded", finding.rule, module.as_posix())

    elapsed_ms = (time.perf_counter() - started) * 1000
    if not blocking and not judging:
        log.info("allow %s: %d findings, all cleared (%.0f ms)", module.as_posix(), len(findings), elapsed_ms)
        return _allow()

    log.info(
        "deny %s: %d blocking, %d awaiting judgment - rules %s (%.0f ms)",
        module.as_posix(), len(blocking), len(judging),
        sorted({f.rule for f in (*blocking, *judging)}), elapsed_ms,
    )
    return _deny(_findings_message(module, blocking, judging, waiver_count(waivers, module)))


def main() -> int:
    # Composition root: every environment read happens here and nowhere below it.
    gate_off = os.environ.get("LLD_GATE", "").lower() == "off"
    level = os.environ.get("LLD_LOG_LEVEL")
    log_file_override = os.environ.get("LLD_LOG_FILE")

    if gate_off:
        print(json.dumps(_allow()))
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps(_allow()))
        return 0

    project_dir = Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    configure(level=level, log_file=log_path(project_dir, log_file_override))

    try:
        decision = evaluate(payload, project_dir)
    except OSError as exc:
        # A gate that crashes must not block the session; report and stand aside.
        log.warning("standing aside, the gate could not run: %s", exc)
        print(json.dumps(_allow()))
        return 0
    print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
