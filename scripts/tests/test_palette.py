"""The diagram palette must stay the shipped one, not a palette someone liked better.

Colour in these diagrams carries meaning - blue is a type, red is an error - so the choice is
an accessibility decision, not a taste decision. It was made once, by the data-viz reference
palette Claude Code ships, and measured by that skill's own validator. These tests hold the
values to that source so the next person to open the file in a design mood has to argue with
a failing test rather than with a comment.

The first palette here was hand-picked and failed the shipped validator on red against green
at OKLab delta-E 1.3 under simulated deuteranopia - the two colours that separated an error
from a success were, for those readers, the same colour. See docs/incidents.md 010.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from diagrams import PALETTE, find_dataviz, main

#: Every role the diagrams use, with the value from the shipped reference palette
#: (``dataviz/references/palette.md``). Light and dark are the two columns of that file;
#: status critical is fixed in both, which is the shipped rule for status colours.
SHIPPED_LIGHT: Final = {
    "plane": "#f9f9f7",  # Page plane
    "surface": "#fcfcfb",  # Chart surface
    "ink": "#0b0b0b",  # Primary ink
    "ink-2": "#52514e",  # Secondary ink
    "muted": "#898781",  # Muted (axis/labels)
    "axis": "#c3c2b7",  # Baseline / axis
    "series-1": "#2a78d6",  # Categorical slot 1, blue
    "critical": "#d03b3b",  # Status critical, never themed
}

SHIPPED_DARK: Final = {
    "plane": "#0d0d0d",
    "surface": "#1a1a19",
    "ink": "#ffffff",
    "ink-2": "#c3c2b7",
    "muted": "#898781",  # muted is mode-invariant in the shipped table
    "axis": "#383835",
    "series-1": "#3987e5",
    "critical": "#d03b3b",  # fixed: a status colour is never themed
}

_DECL: Final = re.compile(r"--([a-z0-9-]+)\s*:\s*(#[0-9a-f]{6})")


def _block(selector: str) -> dict[str, str]:
    """The custom properties declared under one selector in the palette."""
    start = PALETTE.index(selector)
    body = PALETTE[start + len(selector) : PALETTE.index("}", start)]
    return dict(_DECL.findall(body))


def test_the_light_roles_are_the_shipped_values() -> None:
    assert _block(":root {") == SHIPPED_LIGHT


def test_the_dark_roles_are_the_shipped_values() -> None:
    assert _block(':root:where(:not([data-theme="light"]))') == SHIPPED_DARK


def test_the_theme_toggle_declares_the_same_dark_values() -> None:
    """The shipped guidance wants dark under both scopes, and the two must not drift."""
    assert _block(':root[data-theme="dark"]') == SHIPPED_DARK


def test_a_status_colour_is_not_themed() -> None:
    """The shipped rule: status colours are fixed, so an error reads the same in both modes."""
    assert SHIPPED_LIGHT["critical"] == SHIPPED_DARK["critical"]


def test_no_colour_appears_that_is_not_a_declared_role() -> None:
    """A literal hex anywhere but a role declaration is a colour someone chose by hand."""
    declared = {hex_value for _, hex_value in _DECL.findall(PALETTE)}
    assert set(re.findall(r"#[0-9a-f]{6}", PALETTE)) == declared


def test_prose_uses_the_shipped_face() -> None:
    """The shipped palette says system sans and no serif. Title and caption are prose."""
    for rule in (".title", ".caption"):
        line = next(part for part in PALETTE.split("\n") if part.strip().startswith(rule))
        assert "system-ui" in line
        assert "serif" not in line.replace("sans-serif", "")


def test_identifiers_stay_in_mono() -> None:
    """The one documented departure: a node label is a name the reader has to grep for."""
    line = next(part for part in PALETTE.split("\n") if part.strip().startswith(".name"))
    assert "monospace" in line


# --- the skill is a prerequisite, not a preference -------------------------------------------


def test_the_skill_is_found_when_it_is_installed() -> None:
    """It ships with Claude Code, so a normal checkout finds it."""
    assert find_dataviz() is not None


def test_a_directory_without_the_reference_palette_does_not_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare folder of the right name proves nothing; the palette file is the evidence."""
    empty = tmp_path / "dataviz"
    empty.mkdir()
    monkeypatch.setenv("LLD_DATAVIZ", str(empty))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    assert find_dataviz() is None


def test_a_named_directory_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skill = tmp_path / "dataviz" / "references"
    skill.mkdir(parents=True)
    (skill / "palette.md").write_text("# Reference palette\n", encoding="utf-8")
    monkeypatch.setenv("LLD_DATAVIZ", str(tmp_path / "dataviz"))
    assert find_dataviz() == tmp_path / "dataviz"


def test_drawing_without_the_skill_refuses_and_says_how(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rule is enforced, not merely written down."""
    monkeypatch.delenv("LLD_DATAVIZ", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    code = main([str(Path(__file__).parent), "--out", str(tmp_path / "out")])
    assert code == 3
    assert "dataviz skill is required" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()
