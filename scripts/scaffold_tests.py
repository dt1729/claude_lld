"""Generate a test skeleton and a sandbox script from a module's AST.

Two outputs, both derived from the syntax tree rather than from a description of the code:

* **Test skeleton** - one failing stub per obligation. Red by construction, so a stub cannot
  pass unwritten, and each stub carries the fact in the source that demands it.
* **Sandbox script** - runs the module in a fresh subprocess under a temporary working
  directory, and reports what importing and constructing it actually does. This catches at
  runtime what the AST can only suspect: import-time work, a constructor that touches the
  filesystem, an import that takes a second.

What neither output does is write assertions. A generated ``assert result is not None``
passes the gate, raises the test count, and proves nothing - the shallow test this plugin
exists to prevent. The AST supplies the obligation; a reader supplies the judgment.

Usage:
    python scaffold_tests.py src/shapes/square.py            # print both
    python scaffold_tests.py src/shapes/square.py --write    # write them beside the module
    python scaffold_tests.py src/shapes/square.py --list     # obligations only
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

from contracts import Precondition, contract_path_for, parse_preconditions
from logsetup import configure
from obligations import Obligation, obligations, public_constructors

log = logging.getLogger("lld.scaffold")

#: Values worth trying against a constructor parameter in the sandbox. Not assertions -
#: the sandbox reports what happens, it does not decide what should.
PROBE_VALUES: Final = ("1.0", "0.0", "-1.0")


def module_import_path(module: Path, src_root: str = "src") -> str:
    """The dotted path a test should import, which is the path a caller would use."""
    parts = list(module.with_suffix("").as_posix().split("/"))
    if src_root in parts:
        parts = parts[parts.index(src_root) + 1 :]
    return ".".join(parts)


def test_path_for(module: Path) -> Path:
    """Where the suite for this module belongs: beside it, under tests/."""
    return module.parent / "tests" / f"test_{module.name}"


def read_preconditions(module: Path, src_root: str = "src") -> list[Precondition]:
    """The contract's Preconditions rows, or none when there is no contract to read."""
    contract = contract_path_for(module, src_root)
    if not contract.exists():
        return []
    return parse_preconditions(contract.read_text(encoding="utf-8"))


def render_tests(
    module: Path,
    source: str,
    src_root: str = "src",
    preconditions: list[Precondition] | None = None,
) -> str:
    """The test skeleton for a module, one failing stub per obligation.

    Obligations come from two places. The AST says what the module does; the contract's
    Preconditions table says what it promised to refuse, which the AST cannot see because a
    guard that was never written leaves no trace in the source.
    """
    owed = obligations(source, preconditions)
    dotted = module_import_path(module, src_root)
    names = sorted({o.target.split(".")[0] for o in owed if o.kind == "public-name"})
    raised = sorted({o.target for o in owed if o.kind == "raise"})

    imported = ", ".join(sorted(set(names + raised))) or "*"
    header = (
        f'"""Behaviour of {dotted}, exercised through its public interface.\n\n'
        f"Stubs generated from the module's AST by scaffold_tests.py: one per obligation the\n"
        f"source demands. Each fails until written, so none can pass unnoticed. Replace the\n"
        f"failure with an assertion a plausible bug would break - see the test-design skill.\n"
        f'"""\n\n'
        f"from __future__ import annotations\n\n"
        f"import pytest\n\n"
        f"from {dotted} import {imported}\n\n"
    )
    stubs = "\n\n".join(o.as_stub() for o in owed)
    return header + "\n" + stubs


def render_sandbox(module: Path, source: str, src_root: str = "src") -> str:
    """A script that runs the module in isolation and reports what it actually does.

    Answers at runtime what the AST can only suspect, and what a unit test in an already
    warm process cannot see: whether importing has side effects, whether a constructor
    reaches outside, and how long either takes.

    The probes are data rather than generated code, so the script stays readable and a
    person can add a case by writing one tuple.
    """
    dotted = module_import_path(module, src_root)
    probes: list[str] = []
    for name, fields in public_constructors(source):
        if not fields:
            probes.append(f'    ("{name}", {{}}),')
            continue
        for value in PROBE_VALUES:
            args = ", ".join(f'"{field}": {value}' for field in fields)
            probes.append(f'    ("{name}", {{{args}}}),')
    probe_block = "\n".join(probes) or "    # no public constructors to probe"

    return f'''"""Sandbox for {dotted}: what does this module do when nobody is watching?

Generated from the module's AST by scaffold_tests.py. Run it directly:

    python -m {dotted.rsplit(".", 1)[0]}.tests.sandbox_{module.stem}

It imports the module in a fresh process under a temporary working directory, then builds
each public type with values either side of its guards. It asserts nothing. It reports:
import duration, files touched, and what each construction did, so a person can see whether
the module behaves when it is alone - which no unit test in a warm process can show.

Add a probe by writing a tuple. Do not add assertions: this is an observation, and the
judgments belong in the suite beside it.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

MODULE = "{dotted}"

#: (public name, constructor keyword arguments). Values straddle the guards in the source.
PROBES: list[tuple[str, dict[str, Any]]] = [
{probe_block}
]

#: An import slower than this is doing work at module scope.
SLOW_IMPORT_MS = 100.0


def probe(module: Any, name: str, kwargs: dict[str, Any]) -> None:
    """Build one thing and report what happened, including how it failed."""
    label = f"{{name}}({{', '.join(f'{{k}}={{v!r}}' for k, v in kwargs.items())}})"
    target = getattr(module, name, None)
    if target is None:
        print(f"  {{label:<36}} missing from the module")
        return
    start = time.perf_counter()
    try:
        result = target(**kwargs)
    except Exception as exc:  # noqa: BLE001 - a sandbox reports every failure
        print(f"  {{label:<36}} raised {{type(exc).__name__}}: {{exc}}")
        return
    elapsed = (time.perf_counter() - start) * 1000
    print(f"  {{label:<36}} -> {{result!r}}  ({{elapsed:.2f}} ms)")


def main() -> int:
    origin = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            run_probes(Path(tmp))
        finally:
            # Windows cannot remove a directory that is some process's cwd, and this
            # process just made it one.
            os.chdir(origin)
    return 0


def run_probes(tmp: Path) -> None:
    """Import and construct, with the working directory inside the sandbox."""
    os.chdir(tmp)
    before = set(Path(tmp).iterdir())

    start = time.perf_counter()
    module = importlib.import_module(MODULE)
    import_ms = (time.perf_counter() - start) * 1000
    print(f"import {{MODULE}}: {{import_ms:.2f}} ms")
    if import_ms > SLOW_IMPORT_MS:
        print("  slow: something is happening at module scope")

    print("constructions:")
    for name, kwargs in PROBES:
        probe(module, name, kwargs)

    touched = sorted(p.name for p in set(Path(tmp).iterdir()) - before)
    print(f"files written: {{touched}}" if touched else "files written: none")


if __name__ == "__main__":
    sys.exit(main())
'''


def _report(owed: Sequence[Obligation]) -> str:
    if not owed:
        return "no obligations: the module exposes nothing and raises nothing"
    lines = [f"{len(owed)} obligations from the AST:"]
    lines += [
        f"  line {o.line:>3}  [{o.kind:<11}] {o.target:<28} -> {o.suggested_name}" for o in owed
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path, help="the source module to scaffold tests for")
    parser.add_argument("--src-root", default="src")
    parser.add_argument("--write", action="store_true", help="write the files, never overwrite")
    parser.add_argument("--list", action="store_true", help="print obligations only")
    parser.add_argument("--log-level", default=None)
    args = parser.parse_args(argv)
    configure(level=args.log_level, log_file=None)

    try:
        source = args.module.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read {args.module}: {exc}", file=sys.stderr)
        return 2
    rows = read_preconditions(args.module, args.src_root)
    try:
        owed = obligations(source, rows)
    except SyntaxError as exc:
        print(f"{args.module} does not parse: {exc}", file=sys.stderr)
        return 2

    if args.list:
        print(_report(owed))
        return 0

    tests = render_tests(args.module, source, args.src_root, rows)
    sandbox = render_sandbox(args.module, source, args.src_root)

    if not args.write:
        print(_report(owed))
        print("\n--- test skeleton ---\n")
        print(tests)
        print("\n--- sandbox ---\n")
        print(sandbox)
        return 0

    target = test_path_for(args.module)
    sandbox_target = target.parent / f"sandbox_{args.module.stem}.py"
    target.parent.mkdir(parents=True, exist_ok=True)

    # Never overwrite: a written test is someone's judgment, and this script has none.
    for path, content in ((target, tests), (sandbox_target, sandbox)):
        if path.exists():
            print(f"{path.as_posix()} exists, left alone")
            continue
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.as_posix()}")
    log.info("%d obligations scaffolded for %s", len(owed), args.module.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
