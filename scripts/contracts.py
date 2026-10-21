"""Contract location, structural validation, and the waiver ledger.

Pure functions over text: nothing here touches the filesystem or the hook protocol, so the
rules are testable without fixtures. The adapter in ``require_contract.py`` supplies the
bytes and acts on the verdict.

Structure is all that is validated. A contract that passes and says nothing is a failure of
the author, which is why the required sections ask for specifics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CONTRACT_DIR: Final = "docs/contracts"
WAIVER_FILE: Final = "docs/contracts/_waivers.md"

REQUIRED_SECTIONS: Final = (
    "Responsibility",
    "Interface",
    "Preconditions",
    "Seam",
    "Dependencies",
    "Errors",
    "Observability",
    "Tests",
    "Deletion test",
)

VALID_STATUS: Final = frozenset({"draft", "accepted", "superseded"})
LOG_LEVELS: Final = ("debug", "info", "warning", "error")
MIN_TEST_BEHAVIOURS: Final = 3

#: What a module does when a parameter arrives outside its stated range. Exactly three
#: answers, because the design question is which one - not whether to think about it.
#:
#: ``propagate`` is deliberately available. A function called per frame should not
#: revalidate what its caller guarantees, and forcing a guard everywhere would teach authors
#: to write one that does nothing. The point is that the choice is recorded.
VALID_VERDICTS: Final = ("reject", "clamp", "propagate")

NO_PRECONDITIONS: Final = "No preconditions."

#: Placeholder text that means a section was templated and never filled.
PLACEHOLDER: Final = re.compile(r"^(TODO|TBD|\.\.\.|<[^>]+>|\{\{[^}]+\}\})\s*$", re.MULTILINE)

_HEADING: Final = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_PRECONDITION_ROW: Final = re.compile(
    r"^\|\s*(?P<parameter>[^|]+?)\s*\|\s*(?P<must_satisfy>[^|]+?)\s*\|\s*(?P<verdict>[^|]+?)\s*\|\s*$",
    re.MULTILINE,
)
_HEADER_CELL: Final = frozenset({"parameter", "param", "---", ":---", "---:", ":---:"})
_WAIVER_ROW: Final = re.compile(
    r"^\|\s*(?P<path>[^|]+?)\s*\|\s*(?P<rule>\d+)\s*\|\s*(?P<date>[^|]*?)\s*\|\s*(?P<reason>[^|]+?)\s*\|\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class Waiver:
    """One recorded judgment that an anti-pattern finding does not apply here."""

    path: str
    rule: int
    date: str
    reason: str


@dataclass(frozen=True, slots=True)
class Precondition:
    """One parameter, what it must satisfy, and what happens when it does not."""

    parameter: str
    must_satisfy: str
    verdict: str


def contract_path_for(module_path: Path, src_root: str = "src") -> Path:
    """Map a module to its contract: src/detection/pipeline.py -> detection.pipeline.md.

    A path outside ``src_root`` is mapped from its full dotted form, so the function is
    total rather than raising on inputs the caller has already decided to check.
    """
    parts = list(module_path.with_suffix("").as_posix().split("/"))
    if src_root in parts:
        parts = parts[parts.index(src_root) + 1 :]
    return Path(CONTRACT_DIR) / f"{'.'.join(parts)}.md"


def _sections(text: str) -> dict[str, str]:
    """Split a contract into heading -> body. Headings are compared case-insensitively."""
    matches = list(_HEADING.finditer(text))
    out: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[match.group(1).strip().lower()] = text[match.end() : end].strip()
    return out


def _field(text: str, name: str) -> str | None:
    match = re.search(rf"^\*\*{name}:\*\*\s*(\S+)", text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip().lower() if match else None


def _check_sections_present(sections: dict[str, str]) -> list[str]:
    """Every required heading exists and carries something other than a placeholder."""
    errors: list[str] = []
    for required in REQUIRED_SECTIONS:
        body = sections.get(required.lower())
        if body is None:
            errors.append(f"missing section: ## {required}")
        elif not body or PLACEHOLDER.search(body):
            errors.append(f"section is empty or still a placeholder: ## {required}")
    return errors


def _check_header_fields(text: str) -> list[str]:
    """The header fields a contract must carry.

    Depth (junior/senior/principal) used to live here. It came from a model-tier budget and
    said nothing about the module, so it was a label an author assigned to their own work
    and nobody could check. Removed rather than kept as decoration.
    """
    status = _field(text, "Status")
    if status is None:
        return ["missing **Status:** line"]
    if status not in VALID_STATUS:
        return [f"Status must be one of {sorted(VALID_STATUS)}, got {status!r}"]
    return []


def _strip_markup(cell: str) -> str:
    """A table cell as its words: backticks and bold are formatting, not content."""
    return cell.replace("`", "").replace("**", "").strip()


def parse_preconditions(text: str) -> list[Precondition]:
    """Read the Preconditions table out of a contract.

    Rows that do not parse are skipped rather than guessed at, the same rule the waiver
    ledger follows. A verdict cell may carry prose after the verb - ``**reject** - ValueError
    naming the value`` - so the verdict is the recognised word in it, not the whole cell.
    """
    body = _sections(text).get("preconditions", "")
    found: list[Precondition] = []
    for match in _PRECONDITION_ROW.finditer(body):
        parameter = _strip_markup(match.group("parameter"))
        if parameter.lower() in _HEADER_CELL or set(parameter) <= {"-", ":"}:
            continue
        cell = _strip_markup(match.group("verdict")).lower()
        verdict = next((v for v in VALID_VERDICTS if v in cell), "")
        found.append(
            Precondition(
                parameter=parameter,
                must_satisfy=_strip_markup(match.group("must_satisfy")),
                verdict=verdict,
            )
        )
    return found


def verdict_counts(preconditions: list[Precondition]) -> dict[str, int]:
    """How many parameters got each answer.

    A repository whose every row says ``propagate`` has turned the section into a formality,
    which is the same signal the waiver ledger gives when one module keeps accumulating
    judgments. Counting it is what makes that visible.
    """
    return {
        verdict: sum(1 for p in preconditions if p.verdict == verdict) for verdict in VALID_VERDICTS
    }


def _check_preconditions(sections: dict[str, str]) -> list[str]:
    """The section is a table of verdicts, or an explicit statement that there are none."""
    body = sections.get("preconditions", "")
    if not body or NO_PRECONDITIONS.lower() in body.lower():
        return []
    if "|" not in body:
        return [f"## Preconditions needs a table, or the sentence '{NO_PRECONDITIONS}'"]

    rows = parse_preconditions(f"## Preconditions\n{body}")
    if not rows:
        return [f"## Preconditions has a table with no rows; use '{NO_PRECONDITIONS}' instead"]
    return [
        f"## Preconditions row for {row.parameter!r} names no verdict; "
        f"use one of {', '.join(VALID_VERDICTS)}"
        for row in rows
        if not row.verdict
    ]


def _check_section_content(sections: dict[str, str]) -> list[str]:
    """What each section must actually contain, beyond being non-empty."""
    errors: list[str] = []

    interface = sections.get("interface", "")
    if interface and "```" not in interface:
        errors.append("## Interface has no signature in a code block")

    dependencies = sections.get("dependencies", "")
    if dependencies and "may import" not in dependencies.lower():
        errors.append("## Dependencies has no 'May import' line")

    errors_section = sections.get("errors", "").lower()
    if errors_section and "|" not in errors_section and "no error modes" not in errors_section:
        errors.append("## Errors needs a table, or the sentence 'No error modes.'")

    observability = sections.get("observability", "").lower()
    if (
        observability
        and "no logging" not in observability
        and not any(level in observability for level in LOG_LEVELS)
    ):
        errors.append(
            "## Observability names no level; say what is logged at INFO and what "
            "raises it, or state 'No logging.'"
        )
    return errors


def validate_contract(text: str) -> list[str]:
    """Return the reasons this contract is unusable. Empty means it validates."""
    sections = _sections(text)
    errors = [
        *_check_sections_present(sections),
        *_check_header_fields(text),
        *_check_section_content(sections),
        *_check_preconditions(sections),
    ]

    tests = sections.get("tests", "")
    if tests:
        bullets = [ln for ln in tests.splitlines() if ln.lstrip().startswith(("-", "*"))]
        if len(bullets) < MIN_TEST_BEHAVIOURS:
            errors.append(
                f"## Tests lists {len(bullets)} behaviours; at least "
                f"{MIN_TEST_BEHAVIOURS} are required"
            )

    return errors


def parse_waivers(text: str) -> list[Waiver]:
    """Read the waiver ledger. Rows that do not parse are ignored, not guessed at."""
    waivers: list[Waiver] = []
    for match in _WAIVER_ROW.finditer(text):
        path = match.group("path")
        if path.lower() in ("path", "---", ":---"):
            continue
        waivers.append(
            Waiver(
                path=path,
                rule=int(match.group("rule")),
                date=match.group("date"),
                reason=match.group("reason"),
            )
        )
    return waivers


def is_waived(waivers: list[Waiver], module_path: Path, rule: int) -> bool:
    """Whether a recorded judgment covers this finding."""
    target = module_path.as_posix()
    return any(w.rule == rule and w.path == target for w in waivers)


def waiver_count(waivers: list[Waiver], module_path: Path) -> int:
    """How many judgments this module has already accumulated.

    Repeated waivers on one module are evidence the module, not the rule, is the problem.
    """
    target = module_path.as_posix()
    return sum(1 for w in waivers if w.path == target)


def waiver_row(module_path: Path, rule: int, date: str, reason: str) -> str:
    """Render a ledger row, so the format has one definition rather than one per writer."""
    return f"| {module_path.as_posix()} | {rule} | {date} | {reason} |"
