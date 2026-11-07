"""Behaviour of the seam finder: what counts as a seam, who counts as behind it, and what
the finder says when it cannot read a language.

The cases that matter are the ones where a cheap answer is wrong: a Protocol matched by a
class that merely has a ``close()``, an ABC "satisfied" by shape, an abstract class counted
as an adapter of its parent, and a repository whose C++ went unread and reported as having
no seams.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import seams as cli
from core import seams, seams_python


def decls(**modules: str) -> list[seams.TypeDecl]:
    out: list[seams.TypeDecl] = []
    for name, src in modules.items():
        out += seams_python.declarations_in(src, name, f"{name}.py")
    return out


def by_name(found: list[seams.Seam]) -> dict[str, seams.Seam]:
    return {s.decl.name: s for s in found}


PLANNER = """
from typing import Protocol

class Planner(Protocol):
    def plan(self, start, goal, range_m: float) -> bool: ...
    def set_seed(self, seed: int) -> None: ...
"""

OMPL = """
from motion.seam import Planner

class OmplPlanner(Planner):
    def __init__(self, backend):
        self.backend = backend
    def plan(self, start, goal, range_m):
        return self.backend.solve(start, goal, range_m)
    def set_seed(self, seed):
        self.backend.seed = seed
"""

FAKE = """
class FakePlanner:
    def plan(self, s, g, r):
        return True
    def set_seed(self, seed):
        pass
"""


# --- declaring a seam -----------------------------------------------------------------------


def test_a_protocol_is_a_seam_and_an_abc_is_a_seam() -> None:
    found = decls(
        a="from typing import Protocol\nclass P(Protocol):\n    def f(self, x): ...\n",
        b="from abc import ABC\nclass B(ABC):\n    def f(self, x): ...\n",
    )
    assert {(d.name, d.kind) for d in found} == {("P", seams.PROTOCOL), ("B", seams.ABC)}


def test_an_abstractmethod_alone_declares_a_seam() -> None:
    found = decls(a="import abc\nclass B:\n    @abc.abstractmethod\n    def f(self, x): ...\n")
    assert found[0].kind == seams.ABC


def test_a_metaclass_of_abcmeta_declares_a_seam() -> None:
    found = decls(a="from abc import ABCMeta\nclass B(metaclass=ABCMeta):\n    def f(self): ...\n")
    assert found[0].kind == seams.ABC


def test_a_plain_class_is_not_a_seam() -> None:
    found = decls(a="class C:\n    def f(self, x): ...\n")
    assert found[0].kind == seams.CLASS
    assert seams.match(found) == []


def test_self_and_init_are_not_part_of_the_interface() -> None:
    found = decls(
        a="from typing import Protocol\nclass P(Protocol):\n    def __init__(self, a, b): ...\n"
        "    def f(self, x, /, y, *, z): ...\n    @staticmethod\n    def g(a): ...\n"
    )
    assert found[0].methods == (seams.Method("f", ("x", "y", "z")), seams.Method("g", ("a",)))
    assert found[0].params == 4


def test_a_nested_class_is_qualified_by_its_outer_class() -> None:
    found = decls(pkg="class Outer:\n    class Inner:\n        def f(self): ...\n")
    assert [d.qualified for d in found] == ["pkg.Outer", "pkg.Outer.Inner"]


# --- who stands behind it -------------------------------------------------------------------


def test_an_adapter_naming_the_seam_as_a_base_inherits_it() -> None:
    found = by_name(seams.match(decls(seam=PLANNER, ompl=OMPL)))
    assert [(i.qualified, i.how) for i in found["Planner"].implementers] == [
        ("ompl.OmplPlanner", seams.INHERITS)
    ]


def test_a_class_with_every_method_satisfies_a_protocol_by_shape() -> None:
    found = by_name(seams.match(decls(seam=PLANNER, fake=FAKE)))
    assert [(i.qualified, i.how) for i in found["Planner"].implementers] == [
        ("fake.FakePlanner", seams.STRUCTURAL)
    ]


def test_a_class_missing_one_method_does_not_satisfy_it() -> None:
    partial = "class Half:\n    def plan(self, s, g, r):\n        return True\n"
    found = by_name(seams.match(decls(seam=PLANNER, half=partial)))
    assert found["Planner"].implementers == ()


def test_a_class_with_the_wrong_arity_does_not_satisfy_it() -> None:
    wrong = "class Wrong:\n    def plan(self, s, g):\n        pass\n    def set_seed(self, seed):\n        pass\n"
    found = by_name(seams.match(decls(seam=PLANNER, wrong=wrong)))
    assert found["Planner"].implementers == ()


def test_an_abc_is_never_satisfied_by_shape() -> None:
    """A class that happens to look like an ABC is a coincidence, not an adapter."""
    abc = "from abc import ABC, abstractmethod\nclass Sink(ABC):\n    @abstractmethod\n    def write(self, data, flush): ...\n"
    shape = "class File:\n    def write(self, data, flush):\n        pass\n"
    found = by_name(seams.match(decls(seam=abc, f=shape)))
    assert found["Sink"].implementers == ()


def test_a_single_parameterless_method_is_too_cheap_to_match_by_shape() -> None:
    """``close()`` matches half a codebase; a match that cheap says nothing about design."""
    closable = "from typing import Protocol\nclass Closable(Protocol):\n    def close(self): ...\n"
    anything = "class Conn:\n    def close(self):\n        pass\n"
    explicit = "from x import Closable\nclass Sock(Closable):\n    def close(self):\n        pass\n"
    found = by_name(seams.match(decls(seam=closable, a=anything, b=explicit)))
    assert [i.qualified for i in found["Closable"].implementers] == ["b.Sock"]


def test_an_abstract_class_is_not_an_adapter_of_its_parent() -> None:
    base = "from abc import ABC, abstractmethod\nclass Base(ABC):\n    @abstractmethod\n    def f(self, x): ...\n"
    mid = "from abc import abstractmethod\nfrom b import Base\nclass Mid(Base):\n    @abstractmethod\n    def g(self): ...\n"
    leaf = "from m import Mid\nclass Leaf(Mid):\n    def f(self, x):\n        pass\n    def g(self):\n        pass\n"
    found = by_name(seams.match(decls(b=base, m=mid, leaf=leaf)))
    assert [i.qualified for i in found["Base"].implementers] == []
    assert [i.qualified for i in found["Mid"].implementers] == ["leaf.Leaf"]


def test_cells_are_parameters_times_adapters() -> None:
    found = by_name(seams.match(decls(seam=PLANNER, ompl=OMPL, fake=FAKE)))
    assert found["Planner"].decl.params == 4
    assert found["Planner"].cells == 8


def test_match_order_is_stable_by_path_and_line() -> None:
    found = seams.match(decls(z=PLANNER, a=PLANNER))
    assert [s.decl.path for s in found] == ["a.py", "z.py"]


def test_a_module_that_does_not_parse_yields_nothing() -> None:
    assert seams_python.declarations_in("class (:", "m", "m.py") == []


# --- the survey and the report ---------------------------------------------------------------


def plant(root: Path, files: dict[str, str]) -> Path:
    for name, src in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(src, encoding="utf-8")
    return root


class Blind:
    """A front end for a language with no parser installed."""

    language = "cpp"
    suffixes = frozenset({".cpp"})

    def declarations(self, files: Sequence[Path], root: Path) -> seams.Unavailable:
        del root
        return seams.Unavailable(self.language, len(files), "no parser")


def test_survey_skips_virtual_environments(tmp_path: Path) -> None:
    root = plant(tmp_path, {"pkg/seam.py": PLANNER, ".venv/lib/x.py": PLANNER})
    result = seams.survey(root, [seams_python.PythonFrontend()])
    assert [s.decl.qualified for s in result.seams] == ["pkg.seam.Planner"]
    assert result.files == {"python": 1}


def test_a_missing_parser_is_reported_not_counted_as_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plant(tmp_path, {"a.py": PLANNER, "b.cpp": "class X {};"})
    status = cli.main([str(root)], frontends=[seams_python.PythonFrontend(), Blind()])
    out = capsys.readouterr().out
    assert status == 1
    assert "not analysed:" in out
    assert "cpp " in out
    assert "no parser" in out


def test_a_missing_parser_for_an_absent_language_is_not_a_failure(tmp_path: Path) -> None:
    root = plant(tmp_path, {"a.py": PLANNER})
    status = cli.main([str(root)], frontends=[seams_python.PythonFrontend(), Blind()])
    assert status == 0


def test_the_report_groups_seams_by_adapter_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plant(
        tmp_path,
        {
            "motion/seam.py": PLANNER,
            "motion/ompl.py": OMPL,
            "tests/fake.py": FAKE,
            "io/sink.py": "from abc import ABC\nclass Sink(ABC):\n    def write(self, d): ...\n",
        },
    )
    status = cli.main([str(root)], frontends=[seams_python.PythonFrontend()])
    out = capsys.readouterr().out
    assert status == 0
    assert out.startswith("seams: 2   with two or more adapters: 1   cells owed by those: 8")
    assert "two or more adapters:" in out
    assert "no adapter:" in out
    assert "motion.ompl.OmplPlanner" in out
    assert "tests.fake.FakePlanner" in out


def test_json_carries_the_lists_behind_the_numbers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plant(tmp_path, {"seam.py": PLANNER, "ompl.py": OMPL})
    cli.main([str(root), "--json"], frontends=[seams_python.PythonFrontend()])
    data = json.loads(capsys.readouterr().out)
    assert data["files"] == {"python": 2}
    (seam,) = data["seams"]
    assert seam["qualified"] == "seam.Planner"
    assert seam["cells"] == 4
    assert seam["implementers"] == [
        {"qualified": "ompl.OmplPlanner", "how": "inherits", "path": "ompl.py", "line": 4}
    ]
    assert data["unavailable"] == []


def test_min_hides_seams_with_fewer_adapters(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plant(tmp_path, {"seam.py": PLANNER, "ompl.py": OMPL})
    cli.main([str(root), "--min", "2"], frontends=[seams_python.PythonFrontend()])
    out = capsys.readouterr().out
    assert "seam.Planner" not in out
    assert out.startswith("seams: 1")
