"""The C and C++ front end for the seam finder, on tree-sitter.

C++ declares a seam as a class with at least one pure virtual method; an adapter names it
in a base clause. C declares one as a struct of function pointers - a vtable by hand - and
an adapter is a variable of that type with an initializer. C++ code carries both idioms,
so both are recognised in every file, under whichever grammar the suffix selects.

Only the grammar is needed, not a compiler. That is the choice this module makes and its
limit: there is no preprocessing, no template instantiation and no overload resolution. A
class hidden behind a macro is not seen; a base named through a ``using`` alias is matched
by the alias, not the target. tree-sitter recovers from errors, so a header that does not
compile in isolation - most of them - still yields its classes.

tree-sitter is not part of the plugin's dependency set; it is the first third-party parser
the plugin has needed. When it or a grammar is missing the front end returns
:class:`~core.seams.Unavailable` with the install command, and the caller reports that
rather than a count of zero.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Final

from core import seams

C_SUFFIXES: Final = frozenset({".c", ".h"})
CPP_SUFFIXES: Final = frozenset({".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".ipp", ".inl"})

_INSTALL: Final = "pip install tree-sitter tree-sitter-c tree-sitter-cpp"
_CLASS_NODES: Final = frozenset({"class_specifier", "struct_specifier"})
_SCOPE_NODES: Final = frozenset(
    {"namespace_definition", "declaration_list", "template_declaration", "linkage_specification"}
)
_DECLARATOR_WRAPPERS: Final = frozenset(
    {
        "pointer_declarator",
        "reference_declarator",
        "parenthesized_declarator",
        "array_declarator",
        "attributed_declarator",
    }
)
_NAME_NODES: Final = frozenset(
    {"identifier", "field_identifier", "type_identifier", "qualified_identifier"}
)


@dataclass(slots=True)
class _Found:
    """What one file yielded: its types, and typedef aliases to apply afterwards."""

    decls: list[seams.TypeDecl]
    aliases: dict[str, str]


def _text(node: Any, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _named(node: Any) -> Iterator[Any]:
    return (c for c in node.children if c.is_named)


def _innermost_name(node: Any, source: bytes) -> str:
    """The identifier at the bottom of a declarator chain: ``(*open)`` -> ``open``."""
    while node is not None and node.type in _DECLARATOR_WRAPPERS:
        node = next(_named(node), None)
    if node is None:
        return ""
    if node.type == "qualified_identifier":
        return _text(node, source).rsplit("::", 1)[-1]
    return _text(node, source) if node.type in _NAME_NODES else ""


def _params(parameter_list: Any, source: bytes) -> tuple[str, ...]:
    """Parameter names; an unnamed parameter is ``_`` so arity is preserved."""
    names: list[str] = []
    for p in _named(parameter_list):
        if not p.type.endswith("parameter_declaration"):
            continue
        declarator = p.child_by_field_name("declarator")
        names.append(_innermost_name(declarator, source) or "_")
    return tuple(names)


def _simple_type_name(node: Any, source: bytes) -> str:
    """``public Planner<double>`` -> ``Planner``; ``ns::Base`` -> ``Base``."""
    if node.type == "template_type":
        inner = node.child_by_field_name("name")
        return _text(inner, source) if inner is not None else ""
    if node.type in _NAME_NODES:
        return _text(node, source).rsplit("::", 1)[-1]
    if node.type in _CLASS_NODES:
        inner = node.child_by_field_name("name")
        return _text(inner, source) if inner is not None else ""
    return ""


def _bases(class_node: Any, source: bytes) -> tuple[str, ...]:
    clause = next((c for c in _named(class_node) if c.type == "base_class_clause"), None)
    if clause is None:
        return ()
    return tuple(n for n in (_simple_type_name(c, source) for c in _named(clause)) if n)


def _function_declarator(member: Any) -> Any:
    declarator = member.child_by_field_name("declarator")
    while declarator is not None and declarator.type in _DECLARATOR_WRAPPERS:
        declarator = next(_named(declarator), None)
    return (
        declarator if declarator is not None and declarator.type == "function_declarator" else None
    )


def _is_function_pointer(member: Any) -> bool:
    fn = _function_declarator(member)
    return (
        fn is not None and fn.child_by_field_name("declarator").type == "parenthesized_declarator"
    )


def _is_pure_virtual(member: Any, source: bytes) -> bool:
    if member.type != "field_declaration":
        return False
    default = member.child_by_field_name("default_value")
    return (
        default is not None
        and _text(default, source) == "0"
        and _function_declarator(member) is not None
    )


def _method(member: Any, class_name: str, source: bytes) -> seams.Method | None:
    """A member function or function-pointer field, or None for anything else."""
    if member.type not in {"field_declaration", "function_definition", "declaration"}:
        return None
    fn = _function_declarator(member)
    if fn is None:
        return None
    name = _innermost_name(fn.child_by_field_name("declarator"), source)
    if not name or name == class_name or name.startswith(("~", "operator")):
        return None
    return seams.Method(name, _params(fn.child_by_field_name("parameters"), source))


def _class_kind(body: Any, members: list[Any], source: bytes) -> str:
    """Pure virtual anywhere makes a seam; a body of function pointers makes a table."""
    if any(_is_pure_virtual(m, source) for m in members):
        return seams.PURE_VIRTUAL
    fields = [m for m in members if m.type == "field_declaration"]
    pointers = [m for m in fields if _is_function_pointer(m)]
    if pointers and (len(pointers) >= 2 or len(pointers) == len(fields)):
        return seams.FUNCTION_TABLE
    del body
    return seams.CLASS


def _class(node: Any, prefix: str, path: str, source: bytes) -> list[seams.TypeDecl]:
    name_node = node.child_by_field_name("name")
    body = node.child_by_field_name("body")
    if name_node is None or body is None:
        return []
    name = _text(name_node, source).rsplit("::", 1)[-1]
    qualified = f"{prefix}::{name}" if prefix else name
    members = list(_named(body))
    methods = tuple(m for m in (_method(m, name, source) for m in members) if m is not None)
    decl = seams.TypeDecl(
        qualified=qualified,
        language="cpp",
        kind=_class_kind(body, members, source),
        path=path,
        line=node.start_point[0] + 1,
        bases=_bases(node, source),
        methods=methods,
    )
    nested = [n for n in (_nested_class(m) for m in members) if n is not None]
    return [decl, *(d for n in nested for d in _class(n, qualified, path, source))]


def _nested_class(member: Any) -> Any:
    """A class declared inside a class body, which the grammar wraps in a field declaration."""
    if member.type in _CLASS_NODES:
        return member
    inner = member.child_by_field_name("type") if member.type == "field_declaration" else None
    if inner is not None and inner.type in _CLASS_NODES and inner.child_by_field_name("body"):
        return inner
    return None


def _table_instance(node: Any, prefix: str, path: str, source: bytes) -> seams.TypeDecl | None:
    """``static const struct ops usb_ops = { ... };`` - an adapter to a function table."""
    type_node = node.child_by_field_name("type")
    if type_node is None:
        return None
    struct = _simple_type_name(type_node, source)
    if not struct:
        return None
    for init in (c for c in _named(node) if c.type == "init_declarator"):
        value = init.child_by_field_name("value")
        if value is None or value.type != "initializer_list":
            continue
        name = _innermost_name(init.child_by_field_name("declarator"), source)
        fields = tuple(
            seams.Method(_text(d, source).lstrip("."), ())
            for pair in _named(value)
            if pair.type == "initializer_pair"
            for d in [pair.child_by_field_name("designator")]
            if d is not None
        )
        return seams.TypeDecl(
            qualified=f"{prefix}::{name}" if prefix else name,
            language="cpp",
            kind=seams.TABLE_INSTANCE,
            path=path,
            line=node.start_point[0] + 1,
            bases=(struct,),
            methods=fields,
        )
    return None


def _walk(node: Any, prefix: str, path: str, source: bytes, found: _Found) -> None:
    for child in _named(node):
        if child.type in _CLASS_NODES and child.child_by_field_name("body") is not None:
            found.decls.extend(_class(child, prefix, path, source))
        elif child.type == "type_definition":
            _typedef(child, prefix, path, source, found)
        elif child.type == "declaration":
            instance = _table_instance(child, prefix, path, source)
            if instance is not None:
                found.decls.append(instance)
            elif child.child_by_field_name("type") is not None:
                _walk(child, prefix, path, source, found)
        elif child.type == "namespace_definition":
            name = child.child_by_field_name("name")
            inner = _text(name, source) if name is not None else ""
            scope = f"{prefix}::{inner}" if prefix and inner else prefix or inner
            _walk(child, scope, path, source, found)
        elif child.type in _SCOPE_NODES:
            _walk(child, prefix, path, source, found)


def _typedef(node: Any, prefix: str, path: str, source: bytes, found: _Found) -> None:
    """``typedef struct io_ops {...} io_ops_t;`` declares the struct and names an alias."""
    type_node = node.child_by_field_name("type")
    alias = node.child_by_field_name("declarator")
    if type_node is None or type_node.type not in _CLASS_NODES:
        return
    struct = _simple_type_name(type_node, source)
    if type_node.child_by_field_name("body") is not None:
        found.decls.extend(_class(type_node, prefix, path, source))
    if alias is not None and alias.type == "type_identifier" and struct:
        found.aliases[struct] = _text(alias, source)


def _apply_aliases(found: _Found) -> list[seams.TypeDecl]:
    if not found.aliases:
        return found.decls
    return [
        seams.TypeDecl(
            d.qualified,
            d.language,
            d.kind,
            d.path,
            d.line,
            d.bases,
            d.methods,
            (*d.aliases, found.aliases[d.name]) if d.name in found.aliases else d.aliases,
            d.structural,
        )
        for d in found.decls
    ]


def declarations_in(source: str, path: str, parse: Callable[[bytes], Any]) -> list[seams.TypeDecl]:
    """Every class, table struct and table instance in one file's source."""
    raw = source.encode("utf-8")
    found = _Found([], {})
    _walk(parse(raw).root_node, "", path, raw, found)
    return _apply_aliases(found)


def _optional(name: str) -> ModuleType | None:
    """An installed module, or None. Resolved on demand so the import is never a crash."""
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _parser(grammar: str) -> Callable[[bytes], Any] | str:
    """A parse function for the grammar, or the reason none could be built."""
    tree_sitter = _optional("tree_sitter")
    module = _optional(f"tree_sitter_{grammar}")
    if tree_sitter is None:
        return f"tree-sitter is not installed: {_INSTALL}"
    if module is None:
        return f"tree-sitter-{grammar} is not installed: {_INSTALL}"
    parser = tree_sitter.Parser(tree_sitter.Language(module.language()))
    parse: Callable[[bytes], Any] = parser.parse
    return parse


class CxxFrontend:
    """Reads C or C++ with the tree-sitter grammar named at construction."""

    def __init__(self, grammar: str, suffixes: frozenset[str]) -> None:
        self.language = grammar
        self.suffixes = suffixes

    def declarations(
        self, files: Sequence[Path], root: Path
    ) -> list[seams.TypeDecl] | seams.Unavailable:
        parse = _parser(self.language)
        if isinstance(parse, str):
            return seams.Unavailable(self.language, len(files), parse)
        out: list[seams.TypeDecl] = []
        for path in files:
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            out += declarations_in(source, path.relative_to(root).as_posix(), parse)
        return out


def frontends() -> list[CxxFrontend]:
    return [CxxFrontend("c", C_SUFFIXES), CxxFrontend("cpp", CPP_SUFFIXES)]
