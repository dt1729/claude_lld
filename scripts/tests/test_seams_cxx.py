"""Behaviour of the C and C++ front end: pure virtual classes and their subclasses, structs
of function pointers and the tables that fill them, and the honest answer when tree-sitter
is not there.

Every fixture is a fragment that would not compile alone - no includes, undeclared types -
because that is what a header looks like to a tool with no preprocessor, and the front end
has to read it anyway.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import seams, seams_cxx

grammar = pytest.importorskip("tree_sitter_cpp", reason="tree-sitter C++ grammar not installed")
pytest.importorskip("tree_sitter_c", reason="tree-sitter C grammar not installed")


def cpp(source: str, path: str = "a.hpp") -> list[seams.TypeDecl]:
    parse = seams_cxx._parser("cpp")
    assert not isinstance(parse, str), parse
    return seams_cxx.declarations_in(source, path, parse)


def c(source: str, path: str = "a.c") -> list[seams.TypeDecl]:
    parse = seams_cxx._parser("c")
    assert not isinstance(parse, str), parse
    return seams_cxx.declarations_in(source, path, parse)


def by_name(found: list[seams.Seam]) -> dict[str, seams.Seam]:
    return {s.decl.name: s for s in found}


PLANNER_HPP = """
namespace motion {
class Planner {
public:
    virtual ~Planner() = default;
    virtual bool plan(const State& start, const State& goal, double range) = 0;
    virtual void setSeed(int seed) {}
};
}
"""

OMPL_HPP = """
namespace motion {
class OmplPlanner final : public Planner {
public:
    explicit OmplPlanner(ompl::SpaceInformationPtr si) : si_(si) {}
    bool plan(const State& start, const State& goal, double range) override;
    void setSeed(int seed) override;
};
}
"""

OPS_C = """
struct dev_ops {
    int (*open)(struct dev *d, int flags);
    void (*close)(struct dev *d);
};
"""


# --- C++: pure virtual -----------------------------------------------------------------------


def test_a_class_with_a_pure_virtual_method_is_a_seam() -> None:
    (decl,) = cpp(PLANNER_HPP)
    assert decl.kind == seams.PURE_VIRTUAL
    assert decl.qualified == "motion::Planner"
    assert decl.line == 3


def test_constructors_destructors_and_operators_are_not_methods() -> None:
    extra = (
        "\nclass V { public: V(); ~V(); bool operator==(const V&) const; virtual void f() = 0; };"
    )
    planner, v = cpp(PLANNER_HPP + extra)
    assert [m.name for m in planner.methods] == ["plan", "setSeed"]
    assert [m.name for m in v.methods] == ["f"]


def test_parameters_are_named_through_references_and_pointers() -> None:
    (decl,) = cpp("class S { virtual int f(const State& a, char *b, int c, double) = 0; };")
    assert decl.methods == (seams.Method("f", ("a", "b", "c", "_")),)


def test_a_subclass_naming_the_seam_inherits_it() -> None:
    found = by_name(seams.match(cpp(PLANNER_HPP, "planner.hpp") + cpp(OMPL_HPP, "ompl.hpp")))
    assert [(i.qualified, i.how, i.path) for i in found["Planner"].implementers] == [
        ("motion::OmplPlanner", seams.INHERITS, "ompl.hpp")
    ]
    assert found["Planner"].cells == 4


def test_a_template_base_matches_by_its_name() -> None:
    src = "template <typename T> class Base { virtual T get(int i) = 0; };\nclass D : public Base<double>, private Log { T get(int i) override; };"
    found = by_name(seams.match(cpp(src)))
    assert [i.qualified for i in found["Base"].implementers] == ["D"]


def test_a_qualified_base_matches_by_its_last_component() -> None:
    src = "namespace a { class I { virtual void f(int x) = 0; }; }\nclass D : public a::I { void f(int x) override; };"
    found = by_name(seams.match(cpp(src)))
    assert [i.qualified for i in found["I"].implementers] == ["D"]


def test_virtual_without_pure_is_not_a_seam() -> None:
    (decl,) = cpp("class Widget { public: virtual void draw() {} virtual ~Widget() {} };")
    assert decl.kind == seams.CLASS


def test_an_abstract_subclass_is_not_an_adapter() -> None:
    src = "class A { virtual void f(int x) = 0; };\nclass B : public A { virtual void g() = 0; };\nclass C : public B { void f(int x) override; void g() override; };"
    found = by_name(seams.match(cpp(src)))
    assert [i.qualified for i in found["A"].implementers] == []
    assert [i.qualified for i in found["B"].implementers] == ["C"]


def test_a_nested_class_is_qualified_by_namespace_and_outer_class() -> None:
    src = "namespace n { namespace m { class O { class I { virtual void f() = 0; }; }; } }"
    assert [d.qualified for d in cpp(src)] == ["n::m::O", "n::m::O::I"]


def test_a_forward_declaration_is_not_a_declaration() -> None:
    assert cpp("class Planner;\nstruct Opaque;") == []


# --- C: function tables ------------------------------------------------------------------------


def test_a_struct_of_function_pointers_is_a_seam_with_named_parameters() -> None:
    (decl,) = c(OPS_C)
    assert decl.kind == seams.FUNCTION_TABLE
    assert decl.methods == (
        seams.Method("open", ("d", "flags")),
        seams.Method("close", ("d",)),
    )


def test_an_initialised_variable_of_the_struct_type_is_an_adapter() -> None:
    tables = "static const struct dev_ops usb_ops = { .open = usb_open, .close = usb_close };\nstruct dev_ops pci_ops = { pci_open, pci_close };"
    found = by_name(seams.match(c(OPS_C + tables)))
    assert [(i.qualified, i.how) for i in found["dev_ops"].implementers] == [
        ("usb_ops", seams.TABLE),
        ("pci_ops", seams.TABLE),
    ]
    assert found["dev_ops"].cells == 6


def test_a_typedef_alias_still_matches_the_table() -> None:
    src = "typedef struct io_ops { int (*read)(void *ctx, char *buf, int n); void (*close)(void *ctx); } io_ops_t;\nio_ops_t file_io = { file_read, file_close };"
    found = by_name(seams.match(c(src)))
    assert [i.qualified for i in found["io_ops"].implementers] == ["file_io"]


def test_a_struct_of_data_is_not_a_seam() -> None:
    (decl,) = c("struct point { int x; int y; };")
    assert decl.kind == seams.CLASS


def test_one_callback_among_data_fields_is_not_a_table() -> None:
    (decl,) = c("struct timer { int period_ms; const char *name; void (*on_fire)(void *ctx); };")
    assert decl.kind == seams.CLASS


def test_the_table_idiom_is_recognised_in_cpp_too() -> None:
    found = by_name(
        seams.match(cpp(OPS_C + "static const struct dev_ops x_ops = { .open = a, .close = b };"))
    )
    assert [i.how for i in found["dev_ops"].implementers] == [seams.TABLE]


# --- the parser's absence ----------------------------------------------------------------------


def test_a_missing_grammar_is_unavailable_with_the_install_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "tree_sitter_cpp", None)
    (tmp_path / "x.cpp").write_text("class X {};", encoding="utf-8")
    frontend = seams_cxx.CxxFrontend("cpp", seams_cxx.CPP_SUFFIXES)
    result = frontend.declarations([tmp_path / "x.cpp"], tmp_path)
    assert isinstance(result, seams.Unavailable)
    assert result.files == 1
    assert "pip install tree-sitter" in result.reason


def test_the_frontend_reads_files_relative_to_the_root(tmp_path: Path) -> None:
    (tmp_path / "inc").mkdir()
    (tmp_path / "inc" / "p.hpp").write_text(PLANNER_HPP, encoding="utf-8")
    frontend = seams_cxx.CxxFrontend("cpp", seams_cxx.CPP_SUFFIXES)
    result = frontend.declarations([tmp_path / "inc" / "p.hpp"], tmp_path)
    assert not isinstance(result, seams.Unavailable)
    assert [(d.qualified, d.path) for d in result] == [("motion::Planner", "inc/p.hpp")]
