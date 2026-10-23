"""Where a program starts, which decides what every other analysis means.

Everything downstream hangs off this. ``Core``, ``dead`` and every feature set are defined
by what is reachable from an entry point, so an entry point missed is a whole subsystem
wrongly reported dead - the one error a tool that proposes deletions must not make.

So the rule here is **propose, never decide**. Every candidate carries the pattern that
found it, and the patterns are a lookup table rather than inference: a model guessing at
the base of a deterministic analysis makes the result irreproducible, and a dead-code set
that changes between runs cannot be acted on. The weird cases - a framework nobody wrote a
pattern for, a repo whose halves are in different languages - are answered once at
onboarding and written down, not re-derived on every sweep.

A library is the case that breaks the model rather than bending it. It has no ``main``:
every exported name is an entry point, so ``Reach`` becomes everything and ``dead`` becomes
empty. ``classify`` says which kind of repository this is so a caller can refuse to report
dead code in the one case where the question is meaningless.
"""

from __future__ import annotations

import ast
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: Decorators that hand a function to a framework, which then calls it. The call never
#: appears in the source, so without these every route and command reads as dead.
#:
#: ``fixture`` is deliberately absent. pytest does call a fixture, so it is an entry point
#: by the letter of the rule - but it is test scaffolding, and counting it as a feature put
#: five fixtures at the top of trackscope's feature list and filled the overlap table with
#: comparisons between them. Fixtures are tests.
FRAMEWORK_DECORATORS: Final = frozenset(
    {
        "route",
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "command",
        "group",
        "task",
        "callback",
        "app",
        "on_event",
        "websocket",
        # FastMCP, LangChain and friends: the framework calls the tool, nothing in the source
        # does. 253 of 886 definitions in one MCP server read as dead without this.
        "tool",
        "resource",
        "prompt",
    }
)

#: Constructors whose module-level instance a server process imports and serves. The module
#: body is the entry - ``app = FastAPI()`` followed by ``app.include_router(...)`` is run by
#: uvicorn from a string, and nothing in the source ever calls it.
APP_FACTORIES: Final = frozenset(
    {"FastAPI", "Flask", "Starlette", "FastMCP", "Celery", "Typer", "Quart", "Litestar", "Sanic"}
)

#: Directories whose modules a tool runs by convention, with no call anywhere in the source.
#: Alembic imports a migration and calls upgrade(); nothing references it, so without this
#: every migration in a repository reads as dead. Found on codesense-ai, where it was two of
#: the nineteen names reported unreachable - the other seventeen were genuinely unused.
TOOL_RUN_DIRS: Final = frozenset({"migrations", "versions", "alembic"})
TOOL_RUN_NAMES: Final = frozenset({"upgrade", "downgrade"})

APPLICATION: Final = "application"
LIBRARY: Final = "library"
MIXED: Final = "mixed"

#: Why a candidate is an entry point. Carried on the finding so a reader can disagree with
#: the reason rather than with the conclusion.
MAIN_GUARD: Final = "main-guard"
SERVED: Final = "served-app"
CONSOLE_SCRIPT: Final = "console-script"
TEST: Final = "test"
FRAMEWORK: Final = "framework-decorator"
TOOL_RUN: Final = "tool-invoked"
EXPORT: Final = "exported-name"


@dataclass(frozen=True, slots=True, order=True)
class EntryPoint:
    """One place execution can begin, and the pattern that says so."""

    qualified: str
    kind: str
    path: str
    line: int


def _decorator_name(node: ast.expr) -> str:
    """The bare name of a decorator, however it was spelled.

    ``@app.route("/")``, ``@route`` and ``@click.command()`` all reduce to one word, because
    the framework matters less than the fact that something else will do the calling.
    """
    while isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _has_main_guard(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
        ):
            return True
    return False


def _serves_app(tree: ast.Module) -> int:
    """Line of a module-level ``name = Framework()`` assignment, or 0."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in APP_FACTORIES:
                return node.lineno
    return 0


def _functions(tree: ast.Module) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Every function with the name a caller would use, methods qualified by their class."""
    out: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            out.extend(
                (f"{node.name}.{m.name}", m)
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return out


def _is_test(name: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A test function or a fixture. Both are the suite, neither is a feature."""
    leaf = name.rsplit(".", maxsplit=1)[-1]
    if leaf.startswith("test_") or name.startswith("test_"):
        return True
    return any(_decorator_name(d) == "fixture" for d in node.decorator_list)


def _console_scripts(root: Path) -> set[str]:
    """Names declared as executables in pyproject, which the packaging tool will call."""
    manifest = root / "pyproject.toml"
    if not manifest.is_file():
        return set()
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return set()
    scripts = data.get("project", {}).get("scripts", {})
    if not isinstance(scripts, dict):
        return set()
    # "pkg.module:function" is the packaging spelling of a qualified name.
    return {str(target).replace(":", ".") for target in scripts.values()}


def in_module(tree: ast.Module, module: str, path: str, declared: set[str]) -> list[EntryPoint]:
    """Every entry point one parsed module offers."""
    found: list[EntryPoint] = []
    if _has_main_guard(tree):
        found.append(EntryPoint(f"{module}.__main__", MAIN_GUARD, path, 1))
    elif line := _serves_app(tree):
        found.append(EntryPoint(f"{module}.__main__", SERVED, path, line))

    for name, node in _functions(tree):
        qualified = f"{module}.{name}"
        kind = ""
        if qualified in declared:
            kind = CONSOLE_SCRIPT
        elif _is_test(name, node):
            kind = TEST
        elif any(_decorator_name(d) in FRAMEWORK_DECORATORS for d in node.decorator_list):
            kind = FRAMEWORK
        elif name in TOOL_RUN_NAMES and TOOL_RUN_DIRS & set(path.split("/")):
            kind = TOOL_RUN
        if kind:
            found.append(EntryPoint(qualified, kind, path, node.lineno))
    return found


def classify(entries: list[EntryPoint], exported: int) -> str:
    """Whether reachability is meaningful here, or whether this is a library.

    A library has no ``main``: every exported name is a way in, so nothing is unreachable
    and a dead-code report is noise. Saying so is better than reporting an empty result and
    letting a reader conclude the code is clean.
    """
    runnable = [e for e in entries if e.kind in (MAIN_GUARD, CONSOLE_SCRIPT, FRAMEWORK, TOOL_RUN)]
    if not runnable:
        return LIBRARY
    return MIXED if exported > len(runnable) * 10 else APPLICATION
