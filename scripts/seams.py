"""Every seam in a repository and who stands behind it, in Python, C and C++.

Rule 11 says a Protocol with one implementation is a hypothetical seam. Nothing ever
checked it. This lists the seams, their adapters, and the number of parameter-adapter
cells each one owes, which is the measurement a seam matrix needs before it is worth
building.

Usage:
    python seams.py .                  # human report
    python seams.py /path/to/repo --json
    python seams.py . --min 2          # only seams with two or more adapters

Exit status is 1 when a language present in the repository could not be read, because a
count of zero produced by a missing parser is not a count.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import seams, seams_cxx, seams_python
from logsetup import configure

log = logging.getLogger("lld.seams")


def all_frontends() -> list[seams.Frontend]:
    return [seams_python.PythonFrontend(), *seams_cxx.frontends()]


def _seam_lines(seam: seams.Seam) -> list[str]:
    d = seam.decl
    lines = [
        f"  {d.kind:14s} {d.qualified:44s} {d.path}:{d.line}"
        f"   {len(d.methods)} methods, {d.params} params, {seam.cells} cells"
    ]
    lines += [f"    {i.how:12s} {i.qualified:44s} {i.path}:{i.line}" for i in seam.implementers]
    return lines


def report(result: seams.Survey, minimum: int) -> str:
    """The human report: seams grouped by how many adapters they have."""
    shown = [s for s in result.seams if len(s.implementers) >= minimum]
    real = [s for s in result.seams if len(s.implementers) >= 2]
    lines = [
        f"seams: {len(result.seams)}   with two or more adapters: {len(real)}"
        f"   cells owed by those: {sum(s.cells for s in real)}",
        "files: " + ", ".join(f"{lang} {n}" for lang, n in sorted(result.files.items())),
    ]
    groups = (
        ("two or more adapters", [s for s in shown if len(s.implementers) >= 2]),
        (
            "one adapter (a hypothetical seam, rule 11)",
            [s for s in shown if len(s.implementers) == 1],
        ),
        ("no adapter", [s for s in shown if not s.implementers]),
    )
    for heading, group in groups:
        if group:
            lines += ["", f"{heading}:"]
            for seam in group:
                lines += _seam_lines(seam)
    if result.unavailable:
        lines += ["", "not analysed:"]
        lines += [f"  {u.language:6s} {u.files:4d} files  {u.reason}" for u in result.unavailable]
    return "\n".join(lines)


def as_json(result: seams.Survey) -> dict[str, Any]:
    return {
        "files": result.files,
        "seams": [
            {
                "qualified": s.decl.qualified,
                "kind": s.decl.kind,
                "language": s.decl.language,
                "path": s.decl.path,
                "line": s.decl.line,
                "methods": [{"name": m.name, "params": list(m.params)} for m in s.decl.methods],
                "cells": s.cells,
                "implementers": [
                    {"qualified": i.qualified, "how": i.how, "path": i.path, "line": i.line}
                    for i in s.implementers
                ],
            }
            for s in result.seams
        ],
        "unavailable": [
            {"language": u.language, "files": u.files, "reason": u.reason}
            for u in result.unavailable
        ],
    }


def main(
    argv: Sequence[str] | None = None, frontends: Sequence[seams.Frontend] | None = None
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=None)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--min", type=int, default=0, help="show seams with at least N adapters")
    parser.add_argument("--log-level", default=None)
    args = parser.parse_args(argv)
    configure(level=args.log_level, log_file=None)

    root = (args.root or Path.cwd()).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    result = seams.survey(root, frontends if frontends is not None else all_frontends())
    log.info(
        "surveyed %s: %d seams, %d unavailable languages, files %s",
        root,
        len(result.seams),
        len(result.unavailable),
        result.files,
    )
    for u in result.unavailable:
        log.warning("%s not analysed (%d files): %s", u.language, u.files, u.reason)

    print(json.dumps(as_json(result), indent=2) if args.json else report(result, args.min))
    return 1 if result.incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
