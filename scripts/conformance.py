"""Rule 37: does the module still match the interface its contract promises?

A contract's Interface block is a schema, in the sense the Berkeley function-calling
evaluation uses the word: a declaration that a caller is entitled to rely on. Until now the
plugin checked only that the block existed. A contract could promise ``.perimeter_m -> float``
while the module exposed nothing of the kind, and every gate stayed green.

That is the worse failure mode. A contract nobody checks drifts from its module silently,
and then misleads with authority - the reader trusts it precisely because it is written down.

The comparison is structural and needs no execution: declared names must exist, parameters
must match by name, annotations must match where both sides give one, and a public name the
contract never mentions is either undocumented or should not be public. Matching is
order-independent and all-or-nothing, which is the shape the function-calling evaluations
use for the same reason: the order a schema lists things in carries no meaning.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from findings import BLOCK, JUDGE, Finding

#: The fenced block inside the contract's Interface section.
_INTERFACE_SECTION: Final = re.compile(
    r"^##\s+Interface\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL
)
_FENCE: Final = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)

#: `Square(side_m: float)` - a class and the arguments it is constructed with.
_CONSTRUCTOR: Final = re.compile(r"^(?P<name>[A-Z]\w*)\((?P<params>.*)\)\s*$")

#: `.area_m2 -> float` - a member of the class declared above it.
_MEMBER: Final = re.compile(r"^\.(?P<name>\w+)\s*(?:->\s*(?P<returns>.+?))?\s*$")

RULE: Final = 37


@dataclass(frozen=True, slots=True)
class Declared:
    """One name the contract promises, and what it promises about it."""

    name: str
    owner: str = ""
    params: list[str] = field(default_factory=list)
    annotations: dict[str, str] = field(default_factory=dict)
    returns: str = ""

    @property
    def qualified(self) -> str:
        return f"{self.owner}.{self.name}" if self.owner else self.name


def interface_block(contract: str) -> str:
    """The code inside the contract's Interface section, or empty when there is none."""
    section = _INTERFACE_SECTION.search(contract)
    if section is None:
        return ""
    fence = _FENCE.search(section.group(1))
    return fence.group(1).strip() if fence else ""


def _parse_signature(line: str) -> Declared | None:
    """A `def name(...) -> ...` line, parsed by making it legal Python first."""
    try:
        tree = ast.parse(line.rstrip().rstrip(":") + ": ...")
    except SyntaxError:
        return None
    node = tree.body[0] if tree.body else None
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    # Keyword-only arguments live in a separate list; dropping them meant a contract
    # promising `*, strict: bool` was silently never checked.
    args = [a for a in (*node.args.args, *node.args.kwonlyargs) if a.arg not in ("self", "cls")]
    return Declared(
        name=node.name,
        params=[a.arg for a in args],
        annotations={a.arg: ast.unparse(a.annotation) for a in args if a.annotation},
        returns=ast.unparse(node.returns) if node.returns else "",
    )


def _parse_constructor(line: str) -> Declared | None:
    match = _CONSTRUCTOR.match(line.strip())
    if match is None:
        return None
    parsed = _parse_signature(f"def __init__({match.group('params')})")
    if parsed is None:
        return None
    return Declared(
        name=match.group("name"),
        params=parsed.params,
        annotations=parsed.annotations,
    )


def declarations(contract: str) -> list[Declared]:
    """Every name the contract's Interface block promises.

    Three forms are understood, which are the three the contract format uses: a `def` line,
    a `Class(args)` line, and an indented `.member -> type` line belonging to the class
    above it. Anything else is prose and is skipped rather than guessed at.
    """
    block = interface_block(contract)
    out: list[Declared] = []
    owner = ""
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        member = _MEMBER.match(line)
        if member is not None and owner:
            out.append(
                Declared(
                    name=member.group("name"),
                    owner=owner,
                    returns=(member.group("returns") or "").strip(),
                )
            )
            continue

        if line.startswith(("def ", "async def ")):
            parsed = _parse_signature(line)
            if parsed is not None:
                out.append(parsed)
                owner = ""
            continue

        constructor = _parse_constructor(line)
        if constructor is not None:
            out.append(constructor)
            owner = constructor.name
    return out


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        n.name: n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")
    }


def _module_classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {
        n.name: n for n in tree.body if isinstance(n, ast.ClassDef) and not n.name.startswith("_")
    }


def _class_members(cls: ast.ClassDef) -> dict[str, str]:
    """Public members of a class, mapped to their declared return or field type."""
    members: dict[str, str] = {}
    for node in cls.body:
        # One condition per branch with `continue`, not a hoisted boolean: assigning the
        # isinstance result to a name loses the type narrowing mypy needs.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(
            "_"
        ):
            members[node.name] = ast.unparse(node.returns) if node.returns else ""
            continue
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and not node.target.id.startswith("_")
        ):
            members[node.target.id] = ast.unparse(node.annotation)
    return members


def _constructor_params(cls: ast.ClassDef) -> list[str]:
    """What the class is actually constructed with: an explicit __init__, else its fields."""
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__":
            return [a.arg for a in (*node.args.args, *node.args.kwonlyargs) if a.arg != "self"]
    return [
        node.target.id
        for node in cls.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    ]


def _check_function(declared: Declared, found: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Where a declared function and the real one disagree."""
    problems: list[str] = []
    actual = [
        a.arg for a in (*found.args.args, *found.args.kwonlyargs) if a.arg not in ("self", "cls")
    ]
    if declared.params != actual:
        problems.append(
            f"parameters are {actual or 'none'}, contract promises {declared.params or 'none'}"
        )
    real_returns = ast.unparse(found.returns) if found.returns else ""
    if declared.returns and real_returns and declared.returns != real_returns:
        problems.append(f"returns {real_returns}, contract promises {declared.returns}")
    return problems


def _check_member(item: Declared, classes: dict[str, ast.ClassDef]) -> list[Finding]:
    """A `.member -> type` promise against the class that is supposed to carry it."""
    cls = classes.get(item.owner)
    members = _class_members(cls) if cls is not None else {}
    if cls is None or item.name not in members:
        return [
            Finding(
                RULE,
                item.qualified,
                0,
                BLOCK,
                f"the contract promises {item.qualified}, which the module does not expose; "
                "the contract is describing code that is not there",
            )
        ]
    if item.returns and members[item.name] and item.returns != members[item.name]:
        return [
            Finding(
                RULE,
                item.qualified,
                cls.lineno,
                BLOCK,
                f"{item.qualified} is {members[item.name]}, contract promises {item.returns}",
            )
        ]
    return []


def _check_top_level(
    item: Declared,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
) -> list[Finding]:
    """A promised function or class against the module."""
    if item.name in functions:
        node = functions[item.name]
        return [
            Finding(RULE, item.name, node.lineno, BLOCK, f"{item.name}: {problem}")
            for problem in _check_function(item, node)
        ]
    if item.name in classes:
        actual = _constructor_params(classes[item.name])
        if item.params != actual:
            return [
                Finding(
                    RULE,
                    item.name,
                    classes[item.name].lineno,
                    BLOCK,
                    f"{item.name} is constructed with {actual or 'no arguments'}, contract "
                    f"promises {item.params or 'none'}",
                )
            ]
        return []
    return [
        Finding(
            RULE,
            item.name,
            0,
            BLOCK,
            f"the contract promises {item.name}, which the module does not define",
        )
    ]


def _undocumented(
    promised: set[str],
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: dict[str, ast.ClassDef],
) -> list[Finding]:
    """Public names the contract never mentions, which are promises nobody wrote down."""
    found: list[Finding] = []
    for name in sorted((set(functions) | set(classes)) - promised):
        node = functions.get(name) or classes[name]
        found.append(
            Finding(
                RULE,
                name,
                node.lineno,
                JUDGE,
                f"{name} is public but the contract never mentions it: document it, or make it "
                "private so it is not a promise",
            )
        )
    return found


def conformance(contract: str, source: str) -> list[Finding]:
    """Where the module and its contract disagree, ordered by the line in the module.

    Raises SyntaxError if the module does not parse.
    """
    declared = declarations(contract)
    if not declared:
        return []

    tree = ast.parse(source)
    functions = _module_functions(tree)
    classes = _module_classes(tree)

    found: list[Finding] = []
    promised: set[str] = set()
    for item in declared:
        if item.owner:
            promised.add(item.owner)
            found += _check_member(item, classes)
        else:
            promised.add(item.name)
            found += _check_top_level(item, functions, classes)

    found += _undocumented(promised, functions, classes)
    return sorted(found, key=lambda f: (f.line, f.name))


def contract_path_for(module: Path, src_root: str = "src") -> Path:
    """Where this module's contract lives. Mirrors contracts.contract_path_for."""
    parts = list(module.with_suffix("").as_posix().split("/"))
    if src_root in parts:
        parts = parts[parts.index(src_root) + 1 :]
    return Path("docs/contracts") / f"{'.'.join(parts)}.md"
