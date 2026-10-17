"""Merge generated folder guidance over an existing file, preserving hand-written sections.

Regeneration must never destroy what a person wrote, or nobody will run it twice. Anything
between ``<!-- manual -->`` and ``<!-- /manual -->`` in the existing file survives; the rest
is replaced by the freshly generated content.

The merge is idempotent: merging a result again changes nothing. That property is the whole
contract, and it has a test.

Usage:
    python merge_claude_md.py <target> --generated <file>   # writes target
    python merge_claude_md.py <target> --generated <file> --stdout
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final

MANUAL_OPEN: Final = "<!-- manual -->"
MANUAL_CLOSE: Final = "<!-- /manual -->"

_MANUAL_BLOCK: Final = re.compile(
    re.escape(MANUAL_OPEN) + r"(?P<body>.*?)" + re.escape(MANUAL_CLOSE),
    re.DOTALL,
)


def manual_blocks(text: str) -> list[str]:
    """The hand-written bodies in ``text``, in order, without their markers."""
    return [match.group("body") for match in _MANUAL_BLOCK.finditer(text)]


def merge(generated: str, existing: str) -> str:
    """Return ``generated`` with the manual blocks of ``existing`` carried over.

    Blocks are matched positionally: the nth manual region of the generated file receives
    the nth preserved body. Preserved blocks with no slot are appended, so content is never
    dropped on the floor when a template loses a section.
    """
    preserved = manual_blocks(existing)
    if not preserved:
        return generated

    index = 0

    def take(_match: re.Match[str]) -> str:
        nonlocal index
        body = preserved[index] if index < len(preserved) else _match.group("body")
        index += 1
        return f"{MANUAL_OPEN}{body}{MANUAL_CLOSE}"

    merged = _MANUAL_BLOCK.sub(take, generated)

    leftover = preserved[index:]
    if leftover:
        tail = "\n\n".join(f"{MANUAL_OPEN}{body}{MANUAL_CLOSE}" for body in leftover)
        merged = f"{merged.rstrip()}\n\n{tail}\n"
    return merged


def merge_file(target: Path, generated: str) -> tuple[str, bool]:
    """Merge against ``target`` on disk. Returns the result and whether it differs."""
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    result = merge(generated, existing)
    return result, result != existing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="the CLAUDE.md to create or update")
    parser.add_argument("--generated", type=Path, required=True, help="freshly generated content")
    parser.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = parser.parse_args(argv)

    try:
        generated = args.generated.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read {args.generated}: {exc}", file=sys.stderr)
        return 2

    result, changed = merge_file(args.target, generated)
    if args.stdout:
        print(result, end="")
        return 0

    if changed:
        args.target.parent.mkdir(parents=True, exist_ok=True)
        args.target.write_text(result, encoding="utf-8")
    print(f"{'updated' if changed else 'unchanged'} {args.target.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
