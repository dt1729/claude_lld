# Detectors

The scripts that read code and report findings. The gate imports them; each with a CLI can
also be run by hand or from pre-commit. Rule numbers and tiers: [rules.md](rules.md).

All share one value type, `findings.Finding(rule, name, line, verdict, message)`, where
`verdict` is `block` or `judge`. Text reports group blocking findings first:

```
BLOCKING (1):
  line 24: [19] print - print in a package module: use logging.getLogger(__name__) and a level chosen by who must act
NEEDS JUDGMENT (1):
  line 27: [08] Tiler - class with only __init__ and tile: a function unless this instance is a seam that gets substituted, or holds state between calls
```

| Script | Reads | Rules | CLI |
| --- | --- | --- | --- |
| `detect_patterns.py` | one source file | 1-10, 12-15, 19-24 | yes |
| `detect_tests.py` | one test file | 27-33, 36 | yes |
| `detect_gaps.py` | a module and `tests/test_<module>.py` beside it | 35 | yes |
| `conformance.py` | a contract and its module | 37 | no; used by the gate |
| `obligations.py` | a module, and optionally Preconditions rows | none; produces obligations | no; used by `scaffold_tests.py` and `detect_gaps.py` |
| `findings.py` | - | - | no; the shared type and report format |

To run these at commit time in your own repository, copy the
[enforcement templates](enforcement.md); two of the four files need editing first.

## detect_patterns.py

Structure and logging anti-patterns, file-local: no import graph, no cross-file resolution.

```
python scripts/detect_patterns.py <path> [<path> ...] [--json] [--src-root src] [--log-level LEVEL]
```

Prints `no anti-patterns detected` when clean. Exit 1 on any `block` finding. A module's
position decides some rules: `src/pkg/mod.py` is a root (public) module, `src/pkg/sub/mod.py`
is private, and a path with no `--src-root` segment counts as root. A composition root is
allowed to print, read the environment and configure logging.

**When.** On a file the gate does not cover - anything outside `src/`, or a legacy module
before you edit it, to see every `block` finding the first edit will trip over.

## detect_tests.py

Test-quality rules. Skips any path that is not a test file (`test_*.py`, `*_test.py`, or a
`tests/` segment).

```
python scripts/detect_tests.py <path> [<path> ...] [--json] [--log-level LEVEL]
```

## detect_gaps.py

Rule 35: an obligation from the source that the suite does not meet. Looks for the suite at
`<module dir>/tests/test_<module>.py`; a missing suite means every obligation is a gap.
Skips arguments that are themselves tests.

```
python scripts/detect_gaps.py <module> [<module> ...] [--json] [--src-root src] [--log-level LEVEL]
```

```
src/shapes/square.py (suite: src/shapes/tests/test_square.py):
BLOCKING (5):
  line 8: [35] InvalidSideError - InvalidSideError is public, so a caller can reach it and a test must too. Nothing in the suite covers it; scaffold_tests.py will write the stub (test_invalid_side_error_behaves_as_documented).
  ...
NEEDS JUDGMENT (1):
  line 20: [35] side_m at and just below 0 - InvalidSideError is raised when side_m is at and just below 0; the value either side of that threshold is where off-by-one lives. Confirm a test uses the value either side of it; the AST cannot see which value a test passed.
```

**When.** After filling the stubs `scaffold-tests` wrote, and in pre-commit. The gate cannot
run it: a write shows one file, and this needs two.

"Covers" is deliberately weak: a public name is covered when every part of it is mentioned
somewhere in the suite; a raise is covered when a `pytest.raises` names its type. It answers
whether anyone thought about the obligation, not whether the line ran. Run coverage as well.

## conformance.py

Rule 37. Parses the first fenced block in the contract's `## Interface` section, which may
hold three forms:

```python
def run(source: FrameSource, cfg: Settings) -> Iterator[Detection]
Square(side_m: float)
  .area_m2 -> float
```

A `def` line, a `Class(args)` line, and an indented `.member -> type` belonging to the class
above it. Anything else is skipped as prose. Declarations are matched to definitions by name,
in any order; each parameter list must match exactly, by name and order, keyword-only
included. Return types must match where both sides give one. Parameter annotations are not
compared, despite the module docstring saying they are. A class is compared against its
`__init__`, or its annotated fields when it has none.

## obligations.py

What a module's suite owes: `public-name`, `raise`, `boundary` from the AST, and
`precondition` from each `reject` row of the contract. Contract obligations come first,
numbered by table row. A boundary is recorded only for a raise directly inside an
`if <single comparison against a number>:`.

## Other scripts

| Script | Role |
| --- | --- |
| `require_contract.py` | the gate - [gate.md](gate.md) |
| `contracts.py` | contract path, validation, Preconditions parsing, `verdict_counts`, waiver ledger |
| `derive.py`, `conditions.py`, `scaffold_tests.py`, `diagrams.py`, `sweep.py`, `merge_claude_md.py` | the commands - [commands.md](commands.md) |
| `ste.py` | the ASD-STE100 subset the diagram labels are held to |
| `logsetup.py` | the `lld` logger tree: stderr and file, never stdout |
| `core/` | the sweep's entry points, call graph, reach sets and clones - [sweep.md](sweep.md) |
| `make_banner.py`, `make_demo.py`, `make_flow.py` | regenerate `docs/assets/`; all need Pillow, and the demo and flow also need headless Chrome and ffmpeg |
