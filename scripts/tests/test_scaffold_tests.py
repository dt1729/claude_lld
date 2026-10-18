"""Behaviour of the scaffolder: what it generates, and what it refuses to generate."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scaffold_tests import (
    module_import_path,
    render_sandbox,
    render_tests,
)
from scaffold_tests import test_path_for as suite_path_for  # pytest collects test_* names
from test_obligations import SQUARE

MODULE = Path("src/shapes/square.py")


def suite_for(source: str = SQUARE) -> str:
    return render_tests(MODULE, source)


def sandbox_for(source: str = SQUARE) -> str:
    return render_sandbox(MODULE, source)


# --- paths --------------------------------------------------------------------------------


def test_import_path_is_what_a_caller_would_write() -> None:
    assert module_import_path(MODULE) == "shapes.square"


def test_a_module_outside_src_keeps_its_full_path() -> None:
    assert module_import_path(Path("pkg/thing.py")) == "pkg.thing"


def test_the_suite_belongs_beside_the_module() -> None:
    assert suite_path_for(MODULE) == Path("src/shapes/tests/test_square.py")


# --- the generated suite --------------------------------------------------------------------


def test_the_skeleton_parses_into_a_module_of_stubs() -> None:
    tree = ast.parse(suite_for())
    assert [n for n in tree.body if isinstance(n, ast.FunctionDef)] != []


def test_a_stub_exists_for_every_obligation() -> None:
    tree = ast.parse(suite_for())
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert "test_raises_invalid_side_error" in names
    assert "test_square_area_m2_behaves_as_documented" in names


def test_every_stub_fails_so_none_passes_unwritten() -> None:
    tree = ast.parse(suite_for())
    stubs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert stubs
    for stub in stubs:
        assert "pytest.fail" in ast.unparse(stub)


def test_the_skeleton_imports_through_the_public_path() -> None:
    assert "from shapes.square import InvalidSideError, Square" in suite_for()


def test_no_assertion_is_generated() -> None:
    """A generated assertion is a shallow test with a passing grade."""
    body = suite_for()
    assert "assert " not in body


def test_a_module_with_no_public_surface_yields_no_stubs() -> None:
    tree = ast.parse(suite_for("def _helper() -> int:\n    return 1\n"))
    assert [n for n in tree.body if isinstance(n, ast.FunctionDef)] == []


# --- the generated sandbox --------------------------------------------------------------


def test_the_sandbox_parses_and_defines_its_entry_point() -> None:
    tree = ast.parse(sandbox_for())
    assert "main" in {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}


def test_the_sandbox_probes_either_side_of_the_guard() -> None:
    body = sandbox_for()
    assert '"side_m": 0.0' in body
    assert '"side_m": -1.0' in body


def test_the_sandbox_asserts_nothing() -> None:
    """It observes. The judgments belong in the suite beside it."""
    assert "assert " not in sandbox_for()


def test_the_sandbox_restores_the_working_directory() -> None:
    """Windows cannot delete a directory that is a live process's cwd."""
    assert "os.chdir(origin)" in sandbox_for()


def test_a_module_with_no_constructors_still_produces_a_runnable_sandbox() -> None:
    body = render_sandbox(MODULE, "def run() -> int:\n    return 1\n")
    ast.parse(body)
    assert "no public constructors" in body


# --- end to end ----------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Path:
    package = tmp_path / "src" / "shapes"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "square.py").write_text(SQUARE, encoding="utf-8")
    return tmp_path


def test_written_files_land_beside_the_module(project: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scaffold_tests.py"
    subprocess.run(
        [sys.executable, str(script), str(project / "src/shapes/square.py"), "--write"],
        check=True,
        capture_output=True,
        text=True,
        cwd=project,
    )
    assert (project / "src/shapes/tests/test_square.py").exists()
    assert (project / "src/shapes/tests/sandbox_square.py").exists()


def test_an_existing_suite_is_never_overwritten(project: Path) -> None:
    """A written test is someone's judgment, and the scaffolder has none."""
    suite = project / "src/shapes/tests/test_square.py"
    suite.parent.mkdir(parents=True)
    suite.write_text("# mine\n", encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "scaffold_tests.py"
    result = subprocess.run(
        [sys.executable, str(script), str(project / "src/shapes/square.py"), "--write"],
        check=True,
        capture_output=True,
        text=True,
        cwd=project,
    )
    assert suite.read_text(encoding="utf-8") == "# mine\n"
    assert "left alone" in result.stdout


def test_the_generated_suite_is_red_when_run(project: Path) -> None:
    """Red by construction is the whole point: a stub cannot pass unwritten."""
    script = Path(__file__).resolve().parents[1] / "scaffold_tests.py"
    subprocess.run(
        [sys.executable, str(script), str(project / "src/shapes/square.py"), "--write"],
        check=True,
        capture_output=True,
        text=True,
        cwd=project,
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "src/shapes/tests/test_square.py", "-q"],
        capture_output=True,
        text=True,
        cwd=project,
        check=False,
        env={**os.environ, "PYTHONPATH": str(project / "src")},
    )
    assert result.returncode != 0
    assert "5 failed" in result.stdout
