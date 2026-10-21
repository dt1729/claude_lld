"""Generate the factual half of a contract from the code, so it cannot drift.

A contract has two kinds of sentence. Some are facts about the module - its public
signatures, what it imports and who imports it, what it raises. Those are in the syntax tree
already, and a human retyping them is a copy that goes stale the first time the code moves.
The rest is judgment - why the seam is there, what was rejected, what a caller should do
about an error - and no parser will ever produce it.

This module writes the first kind. Everything it emits sits between ``<!-- derived -->`` and
``<!-- /derived -->`` markers, and everything outside those markers is left exactly as the
author wrote it. Two modes follow: regenerate the blocks, or check whether they are current.

The limit is worth stating where it will be read. The syntax tree sees what is written
literally: a dynamic import, a re-export, a raise inside a helper this module calls are all
invisible here. Each generated block says so, because a block that silently under-reports is
the same lie in a smaller font.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from contracts import contract_path_for
from findings import BLOCK, Finding

OPEN: Final = "<!-- derived -->"
CLOSE: Final = "<!-- /derived -->"

#: Rule number for a derived block that no longer matches the code.
RULE: Final = 38

#: The sections this module owns. Everything else in a contract is the author's.
DERIVED_SECTIONS: Final = ("Interface", "Dependencies", "Errors")

_BLOCK: Final = re.compile(re.escape(OPEN) + r".*?" + re.escape(CLOSE), re.DOTALL)
_HEADING: Final = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

_NOTE: Final = (
    "_Generated from the source. Dynamic imports, re-exports and raises inside helpers "
    "are not visible here._"
)


@dataclass(frozen=True, slots=True)
class ModuleFacts:
    """What the syntax tree says about one module."""

    dotted: str
    signatures: list[str]
    imports: list[str]
    importers: list[str]
    raises: list[str]


def dotted_name(module: Path, src_root: str = "src") -> str:
    """The import path a caller would write for this module."""
    parts = list(module.with_suffix("").as_posix().split("/"))
    if src_root in parts:
        parts = parts[parts.index(src_root) + 1 :]
    return ".".join(parts)


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """One public callable, rendered as the declaration a caller reads."""
    args = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"def {node.name}({args}){returns}"


def _class_signature(node: ast.ClassDef) -> list[str]:
    """A public class: how it is constructed, then each public member."""
    init = next(
        (
            m
            for m in node.body
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == "__init__"
        ),
        None,
    )
    if init is not None:
        params = [
            f"{a.arg}: {ast.unparse(a.annotation)}" if a.annotation else a.arg
            for a in (*init.args.args, *init.args.kwonlyargs)
            if a.arg != "self"
        ]
    else:
        params = [
            f"{s.target.id}: {ast.unparse(s.annotation)}"
            for s in node.body
            if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
        ]
    lines = [f"{node.name}({', '.join(params)})"]
    for member in node.body:
        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if member.name.startswith("_"):
                continue
            returns = f" -> {ast.unparse(member.returns)}" if member.returns else ""
            lines.append(f"  .{member.name}{returns}")
    return lines


def _internal_imports(tree: ast.Module, package_root: str) -> list[str]:
    """Modules this one imports from inside the package, deduplicated and sorted."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.split(".")[0] == package_root:
                found.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == package_root:
                    found.add(alias.name)
    return sorted(found)


def _external_imports(tree: ast.Module, package_root: str) -> list[str]:
    """Top-level packages imported from outside, so stdlib-only is visible as a claim."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            head = node.module.split(".")[0]
            if head != package_root:
                found.add(head)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                head = alias.name.split(".")[0]
                if head != package_root:
                    found.add(head)
    return sorted(found)


def _raised(tree: ast.Module) -> list[str]:
    """Exception types this module raises literally."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        exc = node.exc
        if isinstance(exc, ast.Call):
            exc = exc.func
        if isinstance(exc, ast.Name):
            found.add(exc.id)
        elif isinstance(exc, ast.Attribute):
            found.add(exc.attr)
    return sorted(found)


def import_graph(src_root: Path, package_root: str) -> dict[str, set[str]]:
    """Every internal module mapped to the internal modules it imports.

    Built once and reversed to answer "imported by", which no single file can answer and
    which is the line the pixibot audit found wrong in ten contracts.
    """
    graph: dict[str, set[str]] = {}
    for path in sorted(src_root.rglob("*.py")):
        if path.name == "__init__.py" or "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        graph[dotted_name(path, src_root.name)] = set(_internal_imports(tree, package_root))
    return graph


def facts_for(
    source: str, module: Path, graph: dict[str, set[str]], src_root: str = "src"
) -> ModuleFacts:
    """Read every derivable fact about one module."""
    tree = ast.parse(source)
    dotted = dotted_name(module, src_root)
    package_root = dotted.split(".")[0]

    signatures: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(
            "_"
        ):
            signatures.append(_signature(node))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            signatures.extend(_class_signature(node))

    external = _external_imports(tree, package_root)
    internal = _internal_imports(tree, package_root)
    importers = sorted(name for name, targets in graph.items() if dotted in targets)
    return ModuleFacts(dotted, signatures, internal + external, importers, _raised(tree))


def render(section: str, facts: ModuleFacts) -> str:
    """The derived block for one section, markers included."""
    if section == "Interface":
        body = "```python\n" + "\n".join(facts.signatures or ["# nothing public"]) + "\n```"
    elif section == "Dependencies":
        imports = ", ".join(facts.imports) or "nothing"
        importers = ", ".join(facts.importers) or "nothing in this package"
        body = f"- **May import:** {imports}\n- **Imported by:** {importers}"
    elif section == "Errors":
        if facts.raises:
            rows = "\n".join(f"| `{name}` | |" for name in facts.raises)
            body = f"| Type | Raised when |\n| --- | --- |\n{rows}"
        else:
            body = "No error modes."
    else:
        raise ValueError(f"{section} is not derived")
    return f"{OPEN}\n{body}\n\n{_NOTE}\n{CLOSE}"


def _section_span(contract: str, section: str) -> tuple[int, int] | None:
    """Where one section's body starts and ends in the contract."""
    headings = list(_HEADING.finditer(contract))
    for index, match in enumerate(headings):
        if match.group(1).strip().lower() != section.lower():
            continue
        start = match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(contract)
        return start, end
    return None


def apply(contract: str, facts: ModuleFacts) -> str:
    """Rewrite every derived block, leaving the author's prose untouched.

    A section with no block yet gets one at the top of its body, so an existing contract
    adopts the mechanism without being rewritten.
    """
    out = contract
    for section in DERIVED_SECTIONS:
        span = _section_span(out, section)
        if span is None:
            continue
        start, end = span
        body = out[start:end]
        block = render(section, facts)
        body = (
            _BLOCK.sub(block, body, count=1)
            if _BLOCK.search(body)
            else ("\n\n" + block + "\n" + body.lstrip("\n"))
        )
        out = out[:start] + body + out[end:]
    return out


def stale(contract: str, facts: ModuleFacts) -> list[Finding]:
    """Derived blocks that no longer match the code.

    Reported rather than silently fixed: a stale block means the code moved, and the author
    should see which fact changed before the prose beside it is trusted again.
    """
    found: list[Finding] = []
    for section in DERIVED_SECTIONS:
        span = _section_span(contract, section)
        if span is None:
            continue
        body = contract[span[0] : span[1]]
        current = _BLOCK.search(body)
        if current is None:
            found.append(
                Finding(
                    RULE,
                    section,
                    0,
                    BLOCK,
                    f"## {section} has no derived block; run the derive command to add one",
                )
            )
        elif current.group(0).strip() != render(section, facts).strip():
            found.append(
                Finding(
                    RULE,
                    section,
                    0,
                    BLOCK,
                    f"the derived block in ## {section} no longer matches the code; regenerate it",
                )
            )
    return found


def main(argv: list[str] | None = None) -> int:
    """Rewrite or check the derived blocks of one module's contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path)
    parser.add_argument("--src-root", default="src")
    parser.add_argument("--check", action="store_true", help="fail if a block is stale")
    args = parser.parse_args(argv)

    contract = contract_path_for(args.module, args.src_root)
    if not contract.exists():
        print(f"no contract at {contract.as_posix()}", file=sys.stderr)
        return 2

    source = args.module.read_text(encoding="utf-8")
    root = Path(args.src_root)
    parts = args.module.as_posix().split("/")
    package_root = parts[parts.index(args.src_root) + 1] if args.src_root in parts else ""
    graph = import_graph(root, package_root) if root.is_dir() and package_root else {}
    facts = facts_for(source, args.module, graph, args.src_root)
    text = contract.read_text(encoding="utf-8")

    if args.check:
        problems = stale(text, facts)
        for finding in problems:
            print(f"{contract.as_posix()}: {finding.message}")
        if not problems:
            print(f"{contract.as_posix()}: derived blocks are current")
        return 1 if problems else 0

    updated = apply(text, facts)
    if updated == text:
        print(f"{contract.as_posix()}: unchanged")
        return 0
    contract.write_text(updated, encoding="utf-8")
    print(f"{contract.as_posix()}: derived blocks regenerated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
