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
import logging
import sys
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

from findings import BLOCK, JUDGE, Finding, format_report
from logsetup import configure

log = logging.getLogger("lld.detect")

#: Calls that are cheap and pure, so a module-level assignment from one is not a side effect.
PURE_CALLS: Final = frozenset(
    {
        "TypeVar",
        "NewType",
        "namedtuple",
        "NamedTuple",
        "TypedDict",
        "Path",
        "frozenset",
        "field",
        "dataclass",
        "compile",
        "getLogger",
        "auto",
        "Enum",
        "Final",
        "cast",
        # Value constructors: a module-level constant built from one of these is data,
        # not work. Flagging them taught the first real run nothing.
        "array",
        "asarray",
        "zeros",
        "ones",
        "full",
        "arange",
        "linspace",
        "eye",
        "deque",
        "defaultdict",
        "Counter",
        "date",
        "timedelta",
    }
)


#: Bases whose contract is "subclass me", so inheriting from them is never the anti-pattern.
OPEN_BASES: Final = frozenset(
    {
        "ABC",
        "ABCMeta",
        "Protocol",
        "Enum",
        "IntEnum",
        "StrEnum",
        "Flag",
        "Exception",
        "BaseException",
        "NamedTuple",
        "TypedDict",
        "Generic",
        "object",
    }
)

#: Modules permitted to read the environment and configure logging: the composition root.
#: A module carrying an ``if __name__ == "__main__"`` guard also qualifies, by shape.
COMPOSITION_ROOTS: Final = frozenset(
    {
        "main.py",
        "cli.py",
        "__main__.py",
        "settings.py",
        "config.py",
        # Modules whose job is logging configuration, same category as settings.py.
        "logsetup.py",
        "logging_config.py",
        "log_config.py",
        "logconfig.py",
    }
)

#: Logger methods, used to recognise a log call without resolving the logger object.
LOG_METHODS: Final = frozenset(
    {"debug", "info", "warning", "warn", "error", "critical", "exception", "log"}
)

#: Configuration calls that belong to the application, never to a library module.
LOGGING_CONFIG_CALLS: Final = frozenset(
    {
        "basicConfig",
        "setLevel",
        "addHandler",
        "removeHandler",
        "setFormatter",
        "dictConfig",
        "fileConfig",
    }
)

#: Calls a more specific rule already reports. Rule 03 stays silent on them so one defect
#: produces one finding, not two.
CLAIMED_BY_OTHER_RULES: Final = frozenset({"print"}) | LOGGING_CONFIG_CALLS

#: Side effects at import that are near-universal in scripts. Still wrong when the module
#: is imported by anything, so they are reported - but as judgment, not a block.
IMPORT_TIME_IDIOMS: Final = frozenset({"insert", "append", "add_argument", "use", "filterwarnings"})

MUTATING_METHODS: Final = frozenset(
    {
        "append",
        "extend",
        "insert",
        "remove",
        "pop",
        "clear",
        "update",
        "add",
        "discard",
        "setdefault",
        "popitem",
        "sort",
    }
)


@dataclass(frozen=True, slots=True)
class FileContext:
    """What a rule needs to know about the file beyond its AST."""

    path: Path
    is_init: bool
    is_root_module: bool
    is_composition_root: bool


def has_main_guard(tree: ast.Module) -> bool:
    """Whether the module ends in ``if __name__ == "__main__":``.

    A module that is executable *is* an entry point, whatever it is called. Recognising it
    by shape rather than by filename means a script named for its job - detect_patterns.py,
    not main.py - is still allowed to print and to configure logging.
    """
    for node in tree.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        left = node.test.left
        if (
            isinstance(left, ast.Name)
            and left.id == "__name__"
            and any(
                isinstance(c, ast.Constant) and c.value == "__main__" for c in node.test.comparators
            )
        ):
            return True
    return False


def build_context(path: Path, src_root: str, *, executable: bool = False) -> FileContext:
    """Classify a path: package-root module, private subfolder module, or composition root."""
    parts = path.as_posix().split("/")
    depth_below_src = len(parts) - parts.index(src_root) - 2 if src_root in parts else 1
    return FileContext(
        path=path,
        is_init=path.name == "__init__.py",
        is_root_module=depth_below_src <= 1,
        is_composition_root=path.name in COMPOSITION_ROOTS or executable,
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
    body = [
        n
        for n in fn.body
        if not (
            isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        )
    ]
    if not body:
        return True
    return all(
        isinstance(n, ast.Pass)
        or (
            isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Constant)
            and n.value.value is Ellipsis
        )
        for n in body
    )


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _is_log_call(call: ast.Call) -> bool:
    """Whether this looks like a logger method call.

    Shape-based: any attribute call whose method is a logger method and whose receiver is
    named like a logger. Resolving the object would need cross-file analysis, and a
    convention check that is right almost always beats an analysis that is right rarely.
    """
    if not isinstance(call.func, ast.Attribute) or call.func.attr not in LOG_METHODS:
        return False
    receiver = call.func.value
    name = ""
    if isinstance(receiver, ast.Name):
        name = receiver.id
    elif isinstance(receiver, ast.Attribute):
        name = receiver.attr
    return name.lower() in ("log", "logger", "logging", "_log", "_logger", "self")


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


def rule_01_singleton_accessor(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """A classmethod handing back a cached class attribute, or a global assigned in a function."""
    found: list[Finding] = []
    for cls in _classes(tree):
        for fn in _methods(cls):
            if "classmethod" not in _decorator_names(fn):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Attribute):
                    base = node.value.value
                    if (
                        isinstance(base, ast.Name)
                        and base.id == "cls"
                        and node.value.attr.startswith("_")
                    ):
                        found.append(
                            Finding(
                                1,
                                f"{cls.name}.{fn.name}",
                                fn.lineno,
                                BLOCK,
                                "global singleton accessor: build one instance at the composition "
                                "root and inject it instead",
                            )
                        )
    for fn in _functions(tree):
        for node in ast.walk(fn):
            if isinstance(node, ast.Global):
                found.append(
                    Finding(
                        1,
                        fn.name,
                        node.lineno,
                        BLOCK,
                        f"assigns module global {', '.join(node.names)} from inside a function: "
                        "state the caller cannot own or replace",
                    )
                )
    return found


def rule_02_module_mutable_state(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """A module-level container that is written at runtime is a global with a nicer name."""
    candidates: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(
            node.value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
        ):
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
        Finding(
            2,
            name,
            line,
            BLOCK,
            "module-level mutable state is written at runtime: two configurations cannot "
            "coexist and test order becomes significant",
        )
        for name, line in sorted(candidates.items())
        if name in mutated
    ]


def rule_03_import_time_side_effects(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """Work at module scope surfaces failures as import errors, far from the cause."""
    found: list[Finding] = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            name = _call_name(node.value)
            if name in PURE_CALLS or name in CLAIMED_BY_OTHER_RULES:
                continue
            if name in IMPORT_TIME_IDIOMS:
                found.append(
                    Finding(
                        3,
                        name,
                        node.lineno,
                        JUDGE,
                        f"{name} at import time is a common script idiom but still a side "
                        "effect; move it into main() when this module is imported by anything",
                    )
                )
            else:
                found.append(
                    Finding(
                        3,
                        name or "<call>",
                        node.lineno,
                        BLOCK,
                        "call executed at import time: move it into a function the composition "
                        "root calls",
                    )
                )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
            name = _call_name(node.value)
            if name not in PURE_CALLS and name not in CLAIMED_BY_OTHER_RULES:
                found.append(
                    Finding(
                        3,
                        name or "<call>",
                        node.lineno,
                        JUDGE,
                        f"module-level assignment calls {name or 'a function'} at import time; "
                        "confirm it is pure and cheap",
                    )
                )
    return found


def _local_exception_types(local: dict[str, ast.ClassDef]) -> set[str]:
    """Classes in this file that transitively derive from Exception.

    An exception hierarchy is the one case where inheriting from a concrete class of your
    own is correct: it is how a caller chooses the granularity it catches at, and FORMAT.md
    requires it. Resolving only the immediate base missed this and blocked the very shape
    the guidance prescribes.
    """
    exceptions = {
        name
        for name, cls in local.items()
        if set(_base_names(cls)) & {"Exception", "BaseException"}
    }
    changed = True
    while changed:
        changed = False
        for name, cls in local.items():
            if name not in exceptions and set(_base_names(cls)) & exceptions:
                exceptions.add(name)
                changed = True
    return exceptions


def rule_04_05_inheritance(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """Inheriting from your own concrete class, and chains deeper than one level."""
    local: dict[str, ast.ClassDef] = {c.name: c for c in _classes(tree)}
    exception_types = _local_exception_types(local)
    found: list[Finding] = []
    for cls in _classes(tree):
        if cls.name in exception_types:
            continue  # an exception tree is a correct use of inheritance, at any depth
        for base_name in _base_names(cls):
            base = local.get(base_name)
            if base is None:
                continue
            base_is_abstract = bool(set(_base_names(base)) & {"ABC", "Protocol"}) or any(
                "abstractmethod" in _decorator_names(m) for m in _methods(base)
            )
            if not base_is_abstract and base_name not in OPEN_BASES:
                found.append(
                    Finding(
                        4,
                        cls.name,
                        cls.lineno,
                        BLOCK,
                        f"inherits from concrete class {base_name} defined in this file: hold an "
                        "instance and expose what you mean to expose",
                    )
                )
            if set(_base_names(base)) & set(local):
                found.append(
                    Finding(
                        5,
                        cls.name,
                        cls.lineno,
                        BLOCK,
                        f"inheritance depth > 1 ({cls.name} -> {base_name} -> ...): the middle "
                        "class is both a partial implementation and a variation",
                    )
                )
    return found


def rule_06_all_abstract_abc(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """An ABC with no shared implementation is a Protocol with extra coupling."""
    found: list[Finding] = []
    for cls in _classes(tree):
        if "ABC" not in _base_names(cls):
            continue
        methods = _methods(cls)
        if methods and all(_is_empty_body(m) for m in methods):
            found.append(
                Finding(
                    6,
                    cls.name,
                    cls.lineno,
                    BLOCK,
                    "every method is abstract: use typing.Protocol so implementers need not "
                    "import you",
                )
            )
    return found


def rule_07_stateful_mixin(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """A mixin holding state imposes the initialisation order mixins exist to avoid."""
    found: list[Finding] = []
    for cls in _classes(tree):
        if not cls.name.endswith("Mixin"):
            continue
        for fn in _methods(cls):
            if fn.name == "__init__" or _assigns_self(fn):
                found.append(
                    Finding(
                        7,
                        cls.name,
                        cls.lineno,
                        BLOCK,
                        "mixin holds state: make it a collaborator held as an attribute",
                    )
                )
                break
    return found


def rule_08_class_init_plus_one(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """Two methods, one of them __init__: usually a function with deferred arguments."""
    found: list[Finding] = []
    for cls in _classes(tree):
        methods = _methods(cls)
        names = {m.name for m in methods}
        is_dataclass = bool(_decorator_names(cls) & {"dataclass"})
        if (
            len(methods) == 2
            and "__init__" in names
            and not _class_attributes(cls)
            and not is_dataclass
        ):
            other = next(m for m in methods if m.name != "__init__")
            found.append(
                Finding(
                    8,
                    cls.name,
                    cls.lineno,
                    JUDGE,
                    f"class with only __init__ and {other.name}: a function unless this instance "
                    "is a seam that gets substituted, or holds state between calls",
                )
            )
    return found


def rule_09_all_staticmethod(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """A class of static methods is a module with extra syntax."""
    found: list[Finding] = []
    for cls in _classes(tree):
        methods = _methods(cls)
        if (
            methods
            and not _class_attributes(cls)
            and all("staticmethod" in _decorator_names(m) for m in methods)
        ):
            found.append(
                Finding(
                    9,
                    cls.name,
                    cls.lineno,
                    BLOCK,
                    "every method is static: use a module of functions",
                )
            )
    return found


def rule_10_pass_through(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """A function forwarding its arguments unchanged adds a name and hides nothing."""
    found: list[Finding] = []
    for fn in _functions(tree):
        body = [
            n
            for n in fn.body
            if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))
        ]
        if len(body) != 1:
            continue
        statement = body[0]
        if not isinstance(statement, ast.Return):
            continue
        value = statement.value
        if not isinstance(value, ast.Call):
            continue
        params = [
            a.arg for a in (*fn.args.args, *fn.args.kwonlyargs) if a.arg not in ("self", "cls")
        ]
        # A pass-through forwards every parameter and supplies nothing of its own, so every
        # argument must be a bare name and the names must match the parameters exactly.
        positional = [a.id for a in value.args if isinstance(a, ast.Name)]
        keyword = [kw.value.id for kw in value.keywords if isinstance(kw.value, ast.Name)]
        forwards_only = len(positional) == len(value.args) and len(keyword) == len(value.keywords)
        if params and forwards_only and sorted(positional + keyword) == sorted(params):
            found.append(
                Finding(
                    10,
                    fn.name,
                    fn.lineno,
                    JUDGE,
                    f"forwards every argument to {_call_name(value)} unchanged: delete it unless "
                    "it satisfies a seam or deliberately narrows a surface",
                )
            )
    return found


def rule_12_stringly_typed_mode(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """A str parameter branched on accepts values the type system cannot check."""
    found: list[Finding] = []
    for fn in _functions(tree):
        str_params = {
            a.arg
            for a in (*fn.args.args, *fn.args.kwonlyargs)
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
                found.append(
                    Finding(
                        12,
                        f"{fn.name}({param})",
                        fn.lineno,
                        JUDGE,
                        f"{param} is compared against {count} string literals: an Enum when the "
                        "set is closed, a Callable when callers may supply their own",
                    )
                )
    return found


def rule_13_env_below_root(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """An environment read in the middle of the call stack hides an input from every caller."""
    if ctx.is_composition_root:
        return []
    found: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "environ":
            found.append(
                Finding(
                    13,
                    "os.environ",
                    node.lineno,
                    BLOCK,
                    "environment read outside the composition root: read it once "
                    "into the frozen config and pass the config",
                )
            )
        elif isinstance(node, ast.Call) and _call_name(node) == "getenv":
            found.append(
                Finding(
                    13,
                    "os.getenv",
                    node.lineno,
                    BLOCK,
                    "environment read outside the composition root: read it once "
                    "into the frozen config and pass the config",
                )
            )
    return found


def rule_19_print_in_package(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """print is output that cannot be routed, filtered, levelled or switched off."""
    if ctx.is_composition_root:
        return []
    return [
        Finding(
            19,
            "print",
            node.lineno,
            BLOCK,
            "print in a package module: use logging.getLogger(__name__) and a level "
            "chosen by who must act",
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]


def rule_20_logging_configured_below_root(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """Configuration belongs to the application; a library only emits."""
    if ctx.is_composition_root:
        return []
    return [
        Finding(
            20,
            _call_name(node),
            node.lineno,
            BLOCK,
            f"{_call_name(node)} outside the composition root: a library emits records "
            "and lets the application decide where they go",
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) in LOGGING_CONFIG_CALLS
    ]


def rule_21_eager_log_formatting(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """Formatting eagerly costs work when disabled and destroys the aggregator grouping key."""
    found: list[Finding] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_log_call(node) and node.args):
            continue
        first = node.args[0]
        shape = ""
        if isinstance(first, ast.JoinedStr):
            shape = "f-string"
        elif isinstance(first, ast.Call) and _call_name(first) == "format":
            shape = ".format()"
        elif isinstance(first, ast.BinOp) and isinstance(first.op, ast.Mod):
            shape = "% formatting"
        if shape:
            found.append(
                Finding(
                    21,
                    _call_name(node),
                    node.lineno,
                    BLOCK,
                    f"{shape} in a log call: pass the format string and arguments separately, "
                    'as log.info("loaded %s", name)',
                )
            )
    return found


def rule_22_literal_logger_name(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """A hardcoded name decouples the logger from its module and breaks per-module levels."""
    if ctx.is_composition_root:
        return []
    return [
        Finding(
            22,
            "getLogger",
            node.lineno,
            BLOCK,
            "logger named by a string literal: use getLogger(__name__) so per-module "
            "configuration reaches it",
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _call_name(node) == "getLogger"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]


def rule_23_24_exception_handlers(tree: ast.Module, _ctx: FileContext) -> list[Finding]:
    """Logging an exception without its traceback, and logging one instead of handling it."""
    found: list[Finding] = []
    for handler in (n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)):
        log_calls = [n for n in ast.walk(handler) if isinstance(n, ast.Call) and _is_log_call(n)]
        if not log_calls:
            continue

        for call in log_calls:
            method = _call_name(call)
            carries_traceback = method == "exception" or any(
                kw.arg == "exc_info" for kw in call.keywords
            )
            if method in ("error", "critical") and not carries_traceback:
                found.append(
                    Finding(
                        23,
                        method,
                        call.lineno,
                        BLOCK,
                        "exception logged without its traceback: use log.exception(...) or "
                        "exc_info=True inside an except block",
                    )
                )

        body_without_logging = [
            stmt
            for stmt in handler.body
            if not (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Call)
                and _is_log_call(stmt.value)
            )
        ]
        recovers = any(
            isinstance(
                stmt, (ast.Raise, ast.Return, ast.Continue, ast.Break, ast.Assign, ast.AugAssign)
            )
            or (isinstance(stmt, ast.Expr) and not isinstance(stmt.value, ast.Constant))
            for stmt in body_without_logging
        )
        if not recovers:
            found.append(
                Finding(
                    24,
                    handler.name or "except",
                    handler.lineno,
                    JUDGE,
                    "exception caught, logged and swallowed: the caller is told it succeeded. "
                    "Recover explicitly or re-raise, unless this is a top-level boundary that "
                    "must not crash",
                )
            )
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
                found.append(
                    Finding(
                        14,
                        cls.name,
                        cls.lineno,
                        JUDGE,
                        "mutable dataclass in a public module: frozen=True unless this is an "
                        "accumulator owned by one module",
                    )
                )
    return found


def rule_15_barrel_init(tree: ast.Module, ctx: FileContext) -> list[Finding]:
    """Re-exporting a package makes every internal move a public change."""
    if not ctx.is_init:
        return []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return [
                Finding(
                    15,
                    "__init__.py",
                    node.lineno,
                    BLOCK,
                    "barrel __init__.py: keep it empty and let callers import the "
                    "module that owns the name",
                )
            ]
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            return [
                Finding(
                    15,
                    "__all__",
                    node.lineno,
                    BLOCK,
                    "barrel __init__.py: keep it empty and let callers import the "
                    "module that owns the name",
                )
            ]
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
    rule_19_print_in_package,
    rule_20_logging_configured_below_root,
    rule_21_eager_log_formatting,
    rule_22_literal_logger_name,
    rule_23_24_exception_handlers,
)


def detect(source: str, path: Path, src_root: str = "src") -> list[Finding]:
    """Return every finding in ``source``, ordered by line.

    Raises SyntaxError if the source does not parse; callers decide whether an unparseable
    write is a failure or simply not yet their concern.
    """
    tree = ast.parse(source)
    ctx = build_context(path, src_root, executable=has_main_guard(tree))
    findings = [f for rule in RULES for f in rule(tree, ctx)]
    findings = sorted(findings, key=lambda f: (f.line, f.rule))
    log.debug(
        "%s: %d findings across %d rules (root module: %s)",
        path.as_posix(),
        len(findings),
        len({f.rule for f in findings}),
        ctx.is_root_module,
    )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="+")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--src-root", default="src", help="directory name that roots packages")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING, ERROR")
    args = parser.parse_args(argv)

    configure(level=args.log_level, log_file=None)

    blocked = False
    everything: list[Finding] = []
    for path in args.paths:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"cannot read {path}: {exc}", file=sys.stderr)
            return 2
        try:
            findings = detect(source, path, args.src_root)
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
        print("no anti-patterns detected")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
