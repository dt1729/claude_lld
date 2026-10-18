"""The finding type shared by every detector, and how a set of findings reads.

Extracted when the test detector arrived: two modules needed the same value type, and the
alternative was defining it twice or having one import the other for a type it does not
otherwise use. Neither detector depends on the other now; both depend on this.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

#: The AST decides it. Not waivable.
BLOCK: Final = "block"

#: The shape is suggestive but not proof. A model rules on it with the evidence in hand.
JUDGE: Final = "judge"


@dataclass(frozen=True, slots=True)
class Finding:
    """One detected anti-pattern occurrence."""

    rule: int
    name: str
    line: int
    verdict: str
    message: str


def format_report(findings: Sequence[Finding]) -> str:
    """Human-readable report, grouped by verdict so the blocking ones read first."""
    if not findings:
        return "no anti-patterns detected"
    lines: list[str] = []
    for verdict, header in ((BLOCK, "BLOCKING"), (JUDGE, "NEEDS JUDGMENT")):
        group = [f for f in findings if f.verdict == verdict]
        if not group:
            continue
        lines.append(f"{header} ({len(group)}):")
        lines.extend(f"  line {f.line}: [{f.rule:02d}] {f.name} - {f.message}" for f in group)
    return "\n".join(lines)
