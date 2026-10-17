"""Behaviour of the idempotent folder-guidance merge."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from merge_claude_md import manual_blocks, merge, merge_file

GENERATED = """# src/pkg

**Responsibility.** Turn frames into detections.

**May import.** stdlib

<!-- manual -->
<!-- /manual -->
"""

EXISTING = """# src/pkg

**Responsibility.** An older, wronger sentence.

**May import.** stdlib, numpy

<!-- manual -->
Note: the calibration cache is warmed by the deploy script, not by us.
<!-- /manual -->
"""


def test_generated_content_replaces_the_old_body() -> None:
    result = merge(GENERATED, EXISTING)
    assert "Turn frames into detections." in result
    assert "An older, wronger sentence." not in result


def test_manual_block_survives_regeneration() -> None:
    assert "warmed by the deploy script" in merge(GENERATED, EXISTING)


def test_merge_is_idempotent() -> None:
    """The property the whole design rests on: running it twice changes nothing."""
    once = merge(GENERATED, EXISTING)
    assert merge(GENERATED, once) == once


def test_first_run_with_no_existing_file_is_the_generated_content() -> None:
    assert merge(GENERATED, "") == GENERATED


def test_manual_block_with_no_slot_is_appended_not_dropped() -> None:
    generated_without_slot = "# src/pkg\n\n**Responsibility.** Something.\n"
    result = merge(generated_without_slot, EXISTING)
    assert "warmed by the deploy script" in result


def test_several_manual_blocks_are_matched_in_order() -> None:
    generated = "A\n<!-- manual -->\n<!-- /manual -->\nB\n<!-- manual -->\n<!-- /manual -->\n"
    existing = "A\n<!-- manual -->\nfirst\n<!-- /manual -->\nB\n<!-- manual -->\nsecond\n<!-- /manual -->\n"
    result = merge(generated, existing)
    assert result.index("first") < result.index("second")


def test_extra_generated_slots_keep_their_own_bodies() -> None:
    generated = "<!-- manual -->\nplaceholder\n<!-- /manual -->\n<!-- manual -->\nsecond slot\n<!-- /manual -->\n"
    existing = "<!-- manual -->\nkept\n<!-- /manual -->\n"
    result = merge(generated, existing)
    assert "kept" in result
    assert "second slot" in result


def test_manual_blocks_are_extracted_without_their_markers() -> None:
    assert manual_blocks(EXISTING) == [
        "\nNote: the calibration cache is warmed by the deploy script, not by us.\n"
    ]


def test_a_file_with_no_manual_markers_yields_none() -> None:
    assert manual_blocks("# plain\n") == []


# --- file-level behaviour ---------------------------------------------------------------


def test_merge_file_reports_a_change_on_first_write(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    _, changed = merge_file(target, GENERATED)
    assert changed


def test_merge_file_reports_no_change_when_already_current(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    target.write_text(GENERATED, encoding="utf-8")
    result, changed = merge_file(target, GENERATED)
    assert not changed
    assert result == GENERATED


def test_merge_file_preserves_manual_content_on_disk(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    target.write_text(EXISTING, encoding="utf-8")
    result, changed = merge_file(target, GENERATED)
    assert changed
    assert "warmed by the deploy script" in result
