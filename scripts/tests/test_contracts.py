"""Behaviour of contract location, validation and the waiver ledger."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts import (
    Waiver,
    contract_path_for,
    is_waived,
    parse_waivers,
    validate_contract,
    waiver_count,
    waiver_row,
)

VALID = """# Contract: detection.pipeline

**Status:** accepted
**Depth:** senior

## Responsibility

Turn raw frames into scored detections.

## Interface

```python
def run(source: FrameSource, cfg: Settings) -> Iterator[Detection]
```

Yields in frame order. Calibration is read once at first next().

## Seam

FrameSource is the seam; VideoFile and RtspCamera both exist.

## Dependencies

- **May import:** detection.calibration, stdlib
- **Imported by:** cli

## Errors

| Type | Raised when | Caller response |
| --- | --- | --- |
| CalibrationMissingError | no calibration | prompt the operator |

## Observability

- **INFO** run.complete: run id, frame count, duration.
- Never logged: the frame payload.

## Tests

- yields one detection per frame above threshold
- drops detections below threshold
- raises CalibrationMissingError for an unknown device

## Deletion test

Ordering and calibration caching would reappear in cli and benchmark.
"""


def without(section: str) -> str:
    """The valid contract with one section's body emptied, to test one rule at a time."""
    lines = VALID.splitlines(keepends=True)
    out, skipping = [], False
    for line in lines:
        if line.startswith("## "):
            skipping = line.strip() == f"## {section}"
        if skipping and not line.startswith("## "):
            continue
        out.append(line)
    return "".join(out)


# --- contract_path_for ------------------------------------------------------------------


def test_module_maps_to_dotted_contract_path() -> None:
    assert contract_path_for(Path("src/detection/pipeline.py")) == Path(
        "docs/contracts/detection.pipeline.md"
    )


def test_subfolder_module_keeps_full_dotted_path() -> None:
    assert contract_path_for(Path("src/detection/lib/nms.py")) == Path(
        "docs/contracts/detection.lib.nms.md"
    )


def test_path_outside_src_root_still_maps() -> None:
    """Total rather than raising: the caller has already decided the path is in scope."""
    assert contract_path_for(Path("pkg/thing.py")) == Path("docs/contracts/pkg.thing.md")


# --- validate_contract ------------------------------------------------------------------


def test_complete_contract_validates() -> None:
    assert validate_contract(VALID) == []


def test_missing_section_is_reported() -> None:
    text = VALID.replace(
        "## Deletion test\n\nOrdering and calibration caching would reappear in cli and benchmark.\n",
        "",
    )
    assert any("Deletion test" in e for e in validate_contract(text))


def test_empty_section_is_reported() -> None:
    assert any("Seam" in e for e in validate_contract(without("Seam")))


def test_placeholder_section_is_reported() -> None:
    text = VALID.replace("FrameSource is the seam; VideoFile and RtspCamera both exist.", "TODO")
    assert any("Seam" in e for e in validate_contract(text))


def test_interface_without_a_code_block_is_reported() -> None:
    text = VALID.replace(
        "```python\ndef run(source: FrameSource, cfg: Settings) -> Iterator[Detection]\n```",
        "run takes a source",
    )
    assert any("code block" in e for e in validate_contract(text))


def test_dependencies_without_may_import_is_reported() -> None:
    text = VALID.replace("- **May import:** detection.calibration, stdlib", "- stuff")
    assert any("May import" in e for e in validate_contract(text))


def test_two_test_bullets_is_not_enough() -> None:
    text = VALID.replace("- raises CalibrationMissingError for an unknown device\n", "")
    assert any("at least 3" in e for e in validate_contract(text))


def test_errors_section_accepts_the_explicit_none_sentence() -> None:
    text = VALID.replace(
        "| Type | Raised when | Caller response |\n| --- | --- | --- |\n"
        "| CalibrationMissingError | no calibration | prompt the operator |",
        "No error modes.",
    )
    assert validate_contract(text) == []


def test_unknown_status_is_reported() -> None:
    assert any(
        "Status" in e
        for e in validate_contract(VALID.replace("**Status:** accepted", "**Status:** wip"))
    )


def test_junior_depth_is_refused_for_a_wide_module() -> None:
    """The loophole a self-assessed depth would leave open."""
    text = VALID.replace("**Depth:** senior", "**Depth:** junior")
    assert any("junior" in e for e in validate_contract(text, public_names=5))


def test_junior_depth_is_allowed_for_a_narrow_module() -> None:
    text = VALID.replace("**Depth:** senior", "**Depth:** junior")
    assert validate_contract(text, public_names=1) == []


def test_missing_observability_section_is_reported() -> None:
    text = VALID.replace(
        "## Observability\n\n"
        "- **INFO** run.complete: run id, frame count, duration.\n"
        "- Never logged: the frame payload.\n\n",
        "",
    )
    assert any("Observability" in e for e in validate_contract(text))


def test_observability_naming_no_level_is_reported() -> None:
    """A section that says something was considered, without saying what, is not an answer."""
    text = VALID.replace(
        "- **INFO** run.complete: run id, frame count, duration.", "- we log some things"
    )
    assert any("names no level" in e for e in validate_contract(text))


def test_observability_accepts_the_explicit_none_sentence() -> None:
    text = VALID.replace(
        "- **INFO** run.complete: run id, frame count, duration.\n"
        "- Never logged: the frame payload.",
        "No logging.",
    )
    assert validate_contract(text) == []


# --- waivers ----------------------------------------------------------------------------

LEDGER = """# Waivers

| path | rule | date | reason |
| --- | --- | --- | --- |
| src/pkg/thing.py | 8 | 2026-10-17 | the instance is a seam, substituted in tests |
| src/pkg/other.py | 14 | 2026-10-17 | accumulator owned by one module |
"""


def test_ledger_rows_parse_and_skip_the_header() -> None:
    waivers = parse_waivers(LEDGER)
    assert [(w.path, w.rule) for w in waivers] == [
        ("src/pkg/thing.py", 8),
        ("src/pkg/other.py", 14),
    ]


def test_matching_waiver_is_found() -> None:
    assert is_waived(parse_waivers(LEDGER), Path("src/pkg/thing.py"), 8)


def test_waiver_does_not_cover_a_different_rule() -> None:
    assert not is_waived(parse_waivers(LEDGER), Path("src/pkg/thing.py"), 10)


def test_waiver_does_not_cover_a_different_module() -> None:
    assert not is_waived(parse_waivers(LEDGER), Path("src/pkg/elsewhere.py"), 8)


def test_unparseable_rows_are_ignored_not_guessed_at() -> None:
    assert parse_waivers("| missing | columns |\nnot a row at all\n") == []


def test_waiver_count_is_per_module() -> None:
    assert waiver_count(parse_waivers(LEDGER), Path("src/pkg/thing.py")) == 1


def test_waiver_row_round_trips_through_the_parser() -> None:
    row = waiver_row(Path("src/pkg/thing.py"), 12, "2026-10-17", "closed set, enum lands next week")
    assert parse_waivers(f"{row}\n") == [
        Waiver("src/pkg/thing.py", 12, "2026-10-17", "closed set, enum lands next week")
    ]
