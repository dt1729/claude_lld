"""Detect anti-patterns in a single Python source file.

Implements the detectable entries of skills/design-patterns/ANTI-PATTERNS.md. Each rule
returns findings with a verdict: ``block`` when the AST decides the case, ``judge`` when the
shape is suggestive but not proof and a model must rule on it with the evidence in hand.

Deliberately file-local: no cross-file resolution, no import graph. Rules needing those
(single-implementation Protocol, deep imports) are left to import-linter and review, because
a detector that is wrong about half its cases trains people to ignore it.

Usage:
    python detect_patterns.py <path> [--json] [--src-root src]
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

BLOCK: Final = "block"
JUDGE: Final = "judge"

#: Calls that are cheap and pure, so a module-level assignment from one is not a side effect.
PURE_CALLS: Final = frozenset({
    "TypeVar", "NewType", "namedtuple", "NamedTuple", "TypedDict", "Path", "frozenset",
    "field", "dataclass", "compile", "getLogger", "auto", "Enum", "Final", "cast",
})

#: Bases whose contract is "subclass me", so inheriting from them is never the anti-pattern.
OPEN_BASES: Final = frozenset({
    "ABC", "ABCMeta", "Protocol", "Enum", "IntEnum", "StrEnum", "Flag", "Exception",
    "BaseException", "NamedTuple", "TypedDict", "Generic", "object",
})

#: Modules permitted to read the environment: the composition root.
COMPOSITION_ROOTS: Final = frozenset({"main.py", "cli.py", "__main__.py", "settings.py", "config.py"})

MUTATING_METHODS: Final = frozenset({
    "append", "extend", "insert", "remove", "pop", "clear", "update", "add",
    "discard", "setdefault", "popitem", "sort",
})


@dataclass(frozen=True, slots=True)
class Finding:
    """One detected anti-pattern occurrence."""

    rule: int
    name: str
    line: int
    verdict: str
    message: str


@dataclass(frozen=True, slots=True)
class FileContext:
    """What a rule needs to know about the file beyond its AST."""

    path: Path
    is_init: bool
    is_root_module: bool
    is_composition_root: bool


def build_context(path: Path, src_root: str) -> FileContext:
    """Classify a path: package-root module, private subfolder module, or composition root."""
    parts = path.as_posix().split("/")
    depth_below_src = len(parts) - parts.index(src_root) - 2 if src_root in parts else 1
    return FileContext(
        path=path,
        is_init=path.name == "__init__.py",
        is_root_module=depth_below_src <= 1,
        is_composition_root=path.name in COMPOSITION_ROOTS,
    )


# --- helpers ----------------------------------------------------------------------------

def _methods(cls: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _class_attributes(cls: ast.ClassDef) -> list[ast.stmt]:
    return [n for n in cls.body if isinstance(n, (ast.Assign, ast.AnnAssign))]


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _base_names(cls: ast.ClassDef) -> list[str]:
    out: list[str] = []
    for base in cls.bases:
        if isinstance(base, ast.Name):
            out.append(base.id)
        elif isinstance(base, ast.Attribute):
            out.append(base.attr)
        elif isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name):
            out.append(base.value.id)
    return out


def _is_empty_body(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = [n for n in fn.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    if not body:
        return True
    return all(
        isinstance(n, ast.Pass)
        or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and n.value.value is Ellipsis)
        for n in body
    )


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _assigns_self(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        ):
            return True
    return False


def _classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            yield node


def _functions(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Top-level functions and methods, which is where these shapes matter."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


# --- rules ------------------------------------------------------------------------------

def rule_01_singleton_accessor(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """A classmethod handing back a cached class attribute, or a global assigned in a function."""
    found: list[Finding] = []
    for cls in _classes(tree):
        for fn in _methods(cls):
            if "classmethod" not in _decorator_names(fn):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Attribute):
                    base = node.value.value
                    if isinstance(base, ast.Name) and base.id == "cls" and node.value.attr.startswith("_"):
                        found.append(Finding(
                            1, f"{cls.name}.{fn.name}", fn.lineno, BLOCK,
                            "global singleton accessor: build one instance at the composition "
                            "root and inject it instead",
                        ))
    for fn in _functions(tree):
        for node in ast.walk(fn):
            if isinstance(node, ast.Global):
                found.append(Finding(
                    1, fn.name, node.lineno, BLOCK,
                    f"assigns module global {', '.join(node.names)} from inside a function: "
                    "state the caller cannot own or replace",
                ))
    return found


def rule_02_module_mutable_state(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """A module-level container that is written at runtime is a global with a nicer name."""
    candidates: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    candidates[target.id] = node.lineno
    if not candidates:
        return []

    mutated: set[str] = set()
    for child in ast.walk(tree):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in MUTATING_METHODS
            and isinstance(child.func.value, ast.Name)
        ):
            mutated.add(child.func.value.id)
        elif (
            isinstance(child, ast.Subscript)
            and isinstance(child.ctx, ast.Store)
            and isinstance(child.value, ast.Name)
        ):
            mutated.add(child.value.id)
        elif isinstance(child, ast.AugAssign) and isinstance(child.target, ast.Name):
            mutated.add(child.target.id)

    return [
        Finding(2, name, line, BLOCK,
                "module-level mutable state is written at runtime: two configurations cannot "
                "coexist and test order becomes significant")
        for name, line in sorted(candidates.items()) if name in mutated
    ]


def rule_03_import_time_side_effects(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """Work at module scope surfaces failures as import errors, far from the cause."""
    found: list[Finding] = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            name = _call_name(node.value)
            if name not in PURE_CALLS:
                found.append(Finding(
                    3, name or "<call>", node.lineno, BLOCK,
                    "call executed at import time: move it into a function the composition "
                    "root calls",
                ))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
            name = _call_name(node.value)
            if name not in PURE_CALLS:
                found.append(Finding(
                    3, name or "<call>", node.lineno, JUDGE,
                    f"module-level assignment calls {name or 'a function'} at import time; "
                    "confirm it is pure and cheap",
                ))
    return found


def rule_04_05_inheritance(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """Inheriting from your own concrete class, and chains deeper than one level."""
    local: dict[str, ast.ClassDef] = {c.name: c for c in _classes(tree)}
    found: list[Finding] = []
    for cls in _classes(tree):
        for base_name in _base_names(cls):
            base = local.get(base_name)
            if base is None:
                continue
            base_is_abstract = bool(set(_base_names(base)) & {"ABC", "Protocol"}) or any(
                "abstractmethod" in _decorator_names(m) for m in _methods(base)
            )
            if not base_is_abstract and base_name not in OPEN_BASES:
                found.append(Finding(
                    4, cls.name, cls.lineno, BLOCK,
                    f"inherits from concrete class {base_name} defined in this file: hold an "
                    "instance and expose what you mean to expose",
                ))
            if set(_base_names(base)) & set(local):
                found.append(Finding(
                    5, cls.name, cls.lineno, BLOCK,
                    f"inheritance depth > 1 ({cls.name} -> {base_name} -> ...): the middle "
                    "class is both a partial implementation and a variation",
                ))
    return found


def rule_06_all_abstract_abc(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """An ABC with no shared implementation is a Protocol with extra coupling."""
    found: list[Finding] = []
    for cls in _classes(tree):
        if "ABC" not in _base_names(cls):
            continue
        methods = _methods(cls)
        if methods and all(_is_empty_body(m) for m in methods):
            found.append(Finding(
                6, cls.name, cls.lineno, BLOCK,
                "every method is abstract: use typing.Protocol so implementers need not "
                "import you",
            ))
    return found


def rule_07_stateful_mixin(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """A mixin holding state imposes the initialisation order mixins exist to avoid."""
    found: list[Finding] = []
    for cls in _classes(tree):
        if not cls.name.endswith("Mixin"):
            continue
        for fn in _methods(cls):
            if fn.name == "__init__" or _assigns_self(fn):
                found.append(Finding(
                    7, cls.name, cls.lineno, BLOCK,
                    "mixin holds state: make it a collaborator held as an attribute",
                ))
                break
    return found


def rule_08_class_init_plus_one(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """Two methods, one of them __init__: usually a function with deferred arguments."""
    found: list[Finding] = []
    for cls in _classes(tree):
        methods = _methods(cls)
        names = {m.name for m in methods}
        is_dataclass = bool(_decorator_names(cls) & {"dataclass"})
        if len(methods) == 2 and "__init__" in names and not _class_attributes(cls) and not is_dataclass:
            other = next(m for m in methods if m.name != "__init__")
            found.append(Finding(
                8, cls.name, cls.lineno, JUDGE,
                f"class with only __init__ and {other.name}: a function unless this instance "
                "is a seam that gets substituted, or holds state between calls",
            ))
    return found


def rule_09_all_staticmethod(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """A class of static methods is a module with extra syntax."""
    found: list[Finding] = []
    for cls in _classes(tree):
        methods = _methods(cls)
        if methods and not _class_attributes(cls) and all(
            "staticmethod" in _decorator_names(m) for m in methods
        ):
            found.append(Finding(
                9, cls.name, cls.lineno, BLOCK,
                "every method is static: use a module of functions",
            ))
    return found


def rule_10_pass_through(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """A function forwarding its arguments unchanged adds a name and hides nothing."""
    found: list[Finding] = []
    for fn in _functions(tree):
        body = [n for n in fn.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        if len(body) != 1:
            continue
        statement = body[0]
        if not isinstance(statement, ast.Return):
            continue
        value = statement.value
        if not isinstance(value, ast.Call):
            continue
        params = [a.arg for a in (*fn.args.args, *fn.args.kwonlyargs) if a.arg not in ("self", "cls")]
        # A pass-through forwards every parameter and supplies nothing of its own, so every
        # argument must be a bare name and the names must match the parameters exactly.
        positional = [a.id for a in value.args if isinstance(a, ast.Name)]
        keyword = [kw.value.id for kw in value.keywords if isinstance(kw.value, ast.Name)]
        forwards_only = len(positional) == len(value.args) and len(keyword) == len(value.keywords)
        if params and forwards_only and sorted(positional + keyword) == sorted(params):
            found.append(Finding(
                10, fn.name, fn.lineno, JUDGE,
                f"forwards every argument to {_call_name(value)} unchanged: delete it unless "
                "it satisfies a seam or deliberately narrows a surface",
            ))
    return found


def rule_12_stringly_typed_mode(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """A str parameter branched on accepts values the type system cannot check."""
    found: list[Finding] = []
    for fn in _functions(tree):
        str_params = {
            a.arg for a in (*fn.args.args, *fn.args.kwonlyargs)
            if isinstance(a.annotation, ast.Name) and a.annotation.id == "str"
        }
        if not str_params:
            continue
        compared: dict[str, int] = {}
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)):
                continue
            compares_literal = any(
                isinstance(c, ast.Constant) and isinstance(c.value, str) for c in node.comparators
            )
            if node.left.id in str_params and compares_literal:
                compared[node.left.id] = compared.get(node.left.id, 0) + 1
        for param, count in sorted(compared.items()):
            if count >= 2:
                found.append(Finding(
                    12, f"{fn.name}({param})", fn.lineno, JUDGE,
                    f"{param} is compared against {count} string literals: an Enum when the "
                    "set is closed, a Callable when callers may supply their own",
                ))
    return found


def rule_13_env_below_root(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """An environment read in the middle of the call stack hides an input from every caller."""
    if ctx.is_composition_root:
        return []
    found: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "environ":
            found.append(Finding(13, "os.environ", node.lineno, BLOCK,
                                 "environment read outside the composition root: read it once "
                                 "into the frozen config and pass the config"))
        elif isinstance(node, ast.Call) and _call_name(node) == "getenv":
            found.append(Finding(13, "os.getenv", node.lineno, BLOCK,
                                 "environment read outside the composition root: read it once "
                                 "into the frozen config and pass the config"))
    return found


def rule_14_mutable_value_object(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """A non-frozen dataclass on a public surface makes every holder a potential writer."""
    if not ctx.is_root_module:
        return []
    found: list[Finding] = []
    for cls in _classes(tree):
        for dec in cls.decorator_list:
            is_dc = (isinstance(dec, ast.Name) and dec.id == "dataclass") or (
                isinstance(dec, ast.Call) and _call_name(dec) == "dataclass"
            )
            if not is_dc:
                continue
            frozen = isinstance(dec, ast.Call) and any(
                kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in dec.keywords
            )
            if not frozen:
                found.append(Finding(
                    14, cls.name, cls.lineno, JUDGE,
                    "mutable dataclass in a public module: frozen=True unless this is an "
                    "accumulator owned by one module",
                ))
    return found


def rule_15_barrel_init(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """Re-exporting a package makes every internal move a public change."""
    if not ctx.is_init:
        return []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return [Finding(15, "__init__.py", node.lineno, BLOCK,
                            "barrel __init__.py: keep it empty and let callers import the "
                            "module that owns the name")]
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            return [Finding(15, "__all__", node.lineno, BLOCK,
                            "barrel __init__.py: keep it empty and let callers import the "
                            "module that owns the name")]
    return []


RULES: Final = (
    rule_01_singleton_accessor,
    rule_02_module_mutable_state,
    rule_03_import_time_side_effects,
    rule_04_05_inheritance,
    rule_06_all_abstract_abc,
    rule_07_stateful_mixin,
    rule_08_class_init_plus_one,
    rule_09_all_staticmethod,
    rule_10_pass_through,
    rule_12_stringly_typed_mode,
    rule_13_env_below_root,
    rule_14_mutable_value_object,
    rule_15_barrel_init,
)


def detect(source: str, path: Path, src_root: str = "src") -> list[Finding]:
    """Return every finding in ``source``, ordered by line.

    Raises SyntaxError if the source does not parse; callers decide whether an unparseable
    write is a failure or simply not yet their concern.
    """
    tree = ast.parse(source)
    ctx = build_context(path, src_root)
    findings = [f for rule in RULES for f in rule(tree, ctx)]
    return sorted(findings, key=lambda f: (f.line, f.rule))


def format_report(findings: Sequence[Finding]) -> str:
    """Human-readable report, grouped by verdict so the blocking ones read first."""
    if not findings:
        return "no anti-patterns detected"
    lines: list[str] = []
    for verdict, header in ((BLOCK, "BLOCKING"), (JUDGE, "NEEDS JUDGMENT")):
        group = [f for f in findings if f.verdict == verdict]
        if not group:
            continue
        lines.append(f"{header} ({len(group)}):")
        lines.extend(f"  line {f.line}: [{f.rule:02d}] {f.name} - {f.message}" for f in group)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--src-root", default="src", help="directory name that roots packages")
    args = parser.parse_args(argv)

    try:
        source = args.path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read {args.path}: {exc}", file=sys.stderr)
        return 2
    try:
        findings = detect(source, args.path, args.src_root)
    except SyntaxError as exc:
        print(f"{args.path} does not parse: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        print(format_report(findings))
    return 1 if any(f.verdict == BLOCK for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
