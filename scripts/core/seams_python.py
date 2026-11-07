"""The Python front end for the seam finder: classes as ``ast`` sees them.

A seam is declared three ways in Python, and this module recognises all three: a base of
``Protocol``, a base of ``ABC`` or ``metaclass=ABCMeta``, or any method under
``@abstractmethod``. Only the first is structural. An ABC is satisfied by inheritance, and
a class that merely looks like one is a coincidence, not an adapter.

``__init__`` is never a seam method: a Protocol cannot meaningfully require a constructor,
and including it would make every class with a two-argument constructor "satisfy" a
two-argument seam. ``self`` and ``cls`` are dropped from parameters because the caller
never supplies them.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from core import seams

LANGUAGE: Final = "python"
SUFFIXES: Final = frozenset({".py"})

_PROTOCOL_BASES: Final = frozenset({"Protocol"})
_ABC_BASES: Final = frozenset({"ABC"})
_IGNORED_METHODS: Final = frozenset({"__init__", "__init_subclass__", "__class_getitem__"})
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def dotted(path: Path, root: Path) -> str:
    """A module's dotted name relative to the repository root, layout-independent."""
    relative = path.relative_to(root).with_suffix("")
    parts = [p for p in relative.parts if p != "__init__"]
    return ".".join(parts) if parts else relative.stem


def _base_name(node: ast.expr) -> str:
    """``motion.Planner`` -> ``Planner``; ``Protocol[T]`` -> ``Protocol``; else empty."""
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _decorated_with(node: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    return any(_base_name(d) == name for d in node.decorator_list)


def _params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    args = node.args
    names = [a.arg for a in (*args.posonlyargs, *args.args)]
    if names and not _decorated_with(node, "staticmethod"):
        names = names[1:]
    return (*names, *(a.arg for a in args.kwonlyargs))


def _methods(cls: ast.ClassDef) -> tuple[seams.Method, ...]:
    return tuple(
        seams.Method(m.name, _params(m))
        for m in cls.body
        if isinstance(m, _FUNCTIONS) and m.name not in _IGNORED_METHODS
    )


def _kind(cls: ast.ClassDef, bases: tuple[str, ...]) -> str:
    if set(bases) & _PROTOCOL_BASES:
        return seams.PROTOCOL
    abc_meta = any(k.arg == "metaclass" and _base_name(k.value) == "ABCMeta" for k in cls.keywords)
    abstract_method = any(
        isinstance(m, _FUNCTIONS) and _decorated_with(m, "abstractmethod") for m in cls.body
    )
    if set(bases) & _ABC_BASES or abc_meta or abstract_method:
        return seams.ABC
    return seams.CLASS


def _classes(body: Sequence[ast.stmt], prefix: str, path: str) -> list[seams.TypeDecl]:
    """Every class in a body, nested ones qualified by their outer class."""
    out: list[seams.TypeDecl] = []
    for node in body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = tuple(b for b in (_base_name(b) for b in node.bases) if b)
        kind = _kind(node, bases)
        qualified = f"{prefix}.{node.name}"
        out.append(
            seams.TypeDecl(
                qualified=qualified,
                language=LANGUAGE,
                kind=kind,
                path=path,
                line=node.lineno,
                bases=tuple(b for b in bases if b not in _PROTOCOL_BASES | _ABC_BASES),
                methods=_methods(node),
                structural=kind == seams.PROTOCOL,
            )
        )
        out += _classes(node.body, qualified, path)
    return out


def declarations_in(source: str, module: str, path: str) -> list[seams.TypeDecl]:
    """Every class declared in one module's source, or nothing when it does not parse."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    return _classes(tree.body, module, path)


class PythonFrontend:
    """Reads ``.py`` files with the standard library. Always available."""

    language = LANGUAGE
    suffixes = SUFFIXES

    def declarations(self, files: Sequence[Path], root: Path) -> list[seams.TypeDecl]:
        out: list[seams.TypeDecl] = []
        for path in files:
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            relative = path.relative_to(root).as_posix()
            out += declarations_in(source, dotted(path, root), relative)
        return out
