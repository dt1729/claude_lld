"""Seams and the adapters behind them, found across a repository in any supported language.

A seam is where behaviour can be swapped without editing the caller: a ``Protocol`` or ABC
in Python, a class with pure virtual methods in C++, a struct of function pointers in C.
An adapter is a concrete thing satisfying it. The question this module answers is the one
rule 11 was written for and never implemented: for every seam, who stands behind it, and
how many of them are there?

The answer is the input to a seam matrix. A seam with two adapters and five parameters
owes ten cells, each a claim that one adapter honours one parameter in its backend's terms.
This module counts the cells; it does not judge them. That is deliberate: what a backend
does with a value is not in any syntax tree.

**Division of labour.** Each language has a front end that reads source and emits
:class:`TypeDecl` records in one vocabulary: a name, the bases it names, the methods it
declares with their parameter names, and whether it was *declared* as an interface. The
matching below is language-neutral. It never sees a syntax tree, so a new language is one
front end and no change here.

**What matching resolves.** An adapter that names the seam as a base. In Python, also one
that defines every method of a ``Protocol`` with the same arity, because that is what a
Protocol means. In C, a variable of the table's struct type with an initializer.

**What it cannot resolve, and the direction it errs.** Bases match by simple name, so two
seams called ``Planner`` in different namespaces share their adapters: over-reporting.
Structural matching ignores parameter names and types, and is refused for a seam with one
parameterless method, because ``close()`` matches half a codebase. A registered virtual
subclass (``ABC.register``), a template parameter used as a concept, or a factory that
returns a different class per platform are invisible: under-reporting. Both directions are
stated here rather than averaged, in the convention the call graph set.

**A parser that is not installed is a result, not an absence.** The C and C++ front ends
need tree-sitter. When it is missing they return :class:`Unavailable`, the report prints it
under its own heading, and the exit status is non-zero. A sweep that printed zero seams for
a C++ repository because it could not read C++ would be green on nothing, which is the
failure incident 001 recorded.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

#: How an adapter came to stand behind a seam.
INHERITS: Final = "inherits"
STRUCTURAL: Final = "structural"
TABLE: Final = "table"

#: Kinds a front end may assign. Abstract kinds declare a seam; the others are candidates.
PROTOCOL: Final = "protocol"
ABC: Final = "abc"
PURE_VIRTUAL: Final = "pure-virtual"
FUNCTION_TABLE: Final = "function-table"
CLASS: Final = "class"
TABLE_INSTANCE: Final = "table"

ABSTRACT_KINDS: Final = frozenset({PROTOCOL, ABC, PURE_VIRTUAL, FUNCTION_TABLE})

#: Directories that are never the program under study. Mirrors the sweep's list; the two
#: are kept separate so that ``core`` never imports a script.
SKIP: Final = frozenset(
    {".git", ".venv", "venv", "__pycache__", "node_modules", ".tox", "build", "dist", ".mypy_cache"}
)


@dataclass(frozen=True, slots=True)
class Method:
    """One callable member: its name and the parameters a caller supplies."""

    name: str
    params: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TypeDecl:
    """A named type as a front end read it, in the vocabulary matching understands.

    ``bases`` are the names written in the declaration, reduced to their last component
    with qualifiers and template arguments removed. ``aliases`` are other names the same
    type answers to - a C ``typedef`` - so a base written as the alias still matches.
    ``structural`` says adapters may satisfy this seam by shape alone; only a Python
    ``Protocol`` sets it.
    """

    qualified: str
    language: str
    kind: str
    path: str
    line: int
    bases: tuple[str, ...] = ()
    methods: tuple[Method, ...] = ()
    aliases: tuple[str, ...] = ()
    structural: bool = False

    @property
    def name(self) -> str:
        return self.qualified.rsplit(".", 1)[-1].rsplit("::", 1)[-1]

    @property
    def abstract(self) -> bool:
        return self.kind in ABSTRACT_KINDS

    @property
    def params(self) -> int:
        return sum(len(m.params) for m in self.methods)


@dataclass(frozen=True, slots=True)
class Implementer:
    """One adapter behind a seam, and how it was matched."""

    qualified: str
    path: str
    line: int
    how: str


@dataclass(frozen=True, slots=True)
class Seam:
    """A declared interface and everything found standing behind it."""

    decl: TypeDecl
    implementers: tuple[Implementer, ...]

    @property
    def cells(self) -> int:
        """Parameter-adapter pairs: the obligations a seam matrix would owe."""
        return self.decl.params * len(self.implementers)


@dataclass(frozen=True, slots=True)
class Unavailable:
    """A language present in the repository that no front end could read."""

    language: str
    files: int
    reason: str


class Frontend(Protocol):
    """What a language must supply. The matcher asks for nothing else."""

    language: str
    suffixes: frozenset[str]

    def declarations(self, files: Sequence[Path], root: Path) -> list[TypeDecl] | Unavailable: ...


@dataclass(slots=True)
class Survey:
    """Everything a run of the finder produced, including what it could not read."""

    seams: list[Seam] = field(default_factory=list)
    unavailable: list[Unavailable] = field(default_factory=list)
    files: dict[str, int] = field(default_factory=dict)

    @property
    def incomplete(self) -> bool:
        return any(u.files for u in self.unavailable)


# --- matching -------------------------------------------------------------------------------


def _by_name(decl: TypeDecl) -> tuple[str, ...]:
    return (decl.name, *decl.aliases)


def _inherits(candidate: TypeDecl, seam: TypeDecl) -> bool:
    return bool(set(candidate.bases) & set(_by_name(seam)))


def _structurally_satisfies(candidate: TypeDecl, seam: TypeDecl) -> bool:
    """Every seam method present with the same arity - and the seam worth matching.

    A single parameterless method is refused: ``close()`` or ``run()`` would match most of
    a codebase, and a match that cheap says nothing about design.
    """
    if not seam.structural or candidate.language != seam.language:
        return False
    if len(seam.methods) < 2 and seam.params == 0:
        return False
    offered = {m.name: len(m.params) for m in candidate.methods}
    return all(offered.get(m.name) == len(m.params) for m in seam.methods)


def _how(candidate: TypeDecl, seam: TypeDecl) -> str | None:
    if candidate.abstract:
        return None
    if candidate.kind == TABLE_INSTANCE:
        return TABLE if _inherits(candidate, seam) else None
    if _inherits(candidate, seam):
        return INHERITS
    if _structurally_satisfies(candidate, seam):
        return STRUCTURAL
    return None


def match(declarations: Iterable[TypeDecl]) -> list[Seam]:
    """Every declared seam, with the adapters found behind it, in a stable order.

    A seam with no methods is still a seam - a marker ``Protocol`` exists - but it owes no
    cells, and a candidate can only inherit it, never satisfy it by shape.
    """
    decls = sorted(declarations, key=lambda d: (d.path, d.line, d.qualified))
    seams = [d for d in decls if d.abstract]
    out: list[Seam] = []
    for seam in seams:
        found = tuple(
            Implementer(c.qualified, c.path, c.line, how)
            for c in decls
            if c is not seam and (how := _how(c, seam)) is not None
        )
        out.append(Seam(seam, found))
    return out


# --- discovery ------------------------------------------------------------------------------


def source_files(root: Path, suffixes: frozenset[str]) -> list[Path]:
    """Every file under ``root`` with one of the suffixes, outside the skipped directories."""
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix in suffixes and not (SKIP & set(p.relative_to(root).parts))
    )


def survey(root: Path, frontends: Sequence[Frontend]) -> Survey:
    """Run every front end over the repository and match what they found."""
    result = Survey()
    declarations: list[TypeDecl] = []
    for frontend in frontends:
        files = source_files(root, frontend.suffixes)
        result.files[frontend.language] = len(files)
        if not files:
            continue
        found = frontend.declarations(files, root)
        if isinstance(found, Unavailable):
            result.unavailable.append(found)
            continue
        declarations += found
    result.seams = match(declarations)
    return result
