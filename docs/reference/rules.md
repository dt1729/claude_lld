# Rules

Every numbered rule, the script that decides it, and where it runs. Enumerated from
`scripts/`, not from the prose. Numbers run 1 to 39. **32 have a detector**: 20 in
`detect_patterns.py`, 8 in `detect_tests.py`, and 35, 37, 38, 39 in one script each. Six are
review only (11, 16, 17, 18, 25, 26) and 34 was removed. `plugin.json` says "38 AST-checked
rules"; the code says 32. The reasoning, a good/bad pair and the fix for each live in
[skills/design-patterns/ANTI-PATTERNS.md](../../skills/design-patterns/ANTI-PATTERNS.md).

**Tier.** `block`: the AST decides it and no waiver clears it. `judge`: the shape is
suggestive, the author rules on it, and a row in the [waiver ledger](gate.md#the-waiver-ledger)
records the ruling. `review`: no reliable signature, so no script reports it.

**Runs in.** *gate*: the `PreToolUse` hook, on every write ([gate.md](gate.md)).
*pre-commit*: this repository's `.pre-commit-config.yaml`, and the
[enforcement template](enforcement.md). *CLI*: the script, run by hand or from a command.

## Structure: `detect_patterns.py`

Runs in: gate (files under `src/`), pre-commit hook `lld-anti-patterns`, CLI.

| # | Rule | Tier |
| --- | --- | --- |
| 1 | Global singleton accessor | block |
| 2 | Module-level mutable state | block |
| 3 | Import-time side effects | block for a bare call at module scope; judge for `insert`, `append`, `add_argument`, `use`, `filterwarnings`, and for a module-level assignment from a call not known to be pure |
| 4 | Inheriting from a concrete class you own | block |
| 5 | Inheritance depth greater than one | block |
| 6 | All-abstract ABC | block |
| 7 | Stateful mixin | block |
| 8 | Class with `__init__` plus one method | judge |
| 9 | All-staticmethod class | block |
| 10 | Pass-through factory or wrapper | judge |
| 11 | `Protocol` with a single implementation | review - needs cross-file resolution, which this detector does not do |
| 12 | Stringly-typed mode parameter | judge |
| 13 | Environment read below the composition root | block |
| 14 | Mutable value object crossing a seam: a `@dataclass` without `frozen=True` | judge - only in a root module, one level below `--src-root` |
| 15 | Barrel `__init__.py` | block - CLI and pre-commit only, because the gate skips `__init__.py` |
| 16 | Deep import into another package subfolder | your `.importlinter`, not this plugin |
| 17 | Logic inside an adapter | review |
| 18 | Exception type with no distinct caller response | review |

A **composition root** may read the environment, print and configure logging (rules 13, 19,
20). A module is one when it is named `main.py`, `cli.py`, `__main__.py`, `settings.py`,
`config.py`, `logsetup.py`, `logging_config.py`, `log_config.py` or `logconfig.py`, or when
it carries an `if __name__ == "__main__":` guard.

## Logging: `detect_patterns.py`

Same detector, same places.

| # | Rule | Tier |
| --- | --- | --- |
| 19 | `print` in a package module | block |
| 20 | Logging configured outside the composition root (`basicConfig`, `setLevel`, `addHandler`, `removeHandler`, `setFormatter`, `dictConfig`, `fileConfig`) | block |
| 21 | Eager f-string, `.format()` or `%` formatting in a log call | block |
| 22 | Logger named by a string literal | block |
| 23 | `log.error` / `log.critical` inside `except` without the traceback | block |
| 24 | Exception caught, logged and swallowed | judge |
| 25 | Log line with no subject | review |
| 26 | Secret or payload in a log line | review |

## Tests: `detect_tests.py`

Runs in: gate (any test file, any directory), pre-commit hook `lld-test-quality`, CLI.

| # | Rule | Tier |
| --- | --- | --- |
| 27 | Test that asserts nothing | block |
| 28 | Suite of five or more tests with no failure case | judge |
| 29 | Assertion on a substring shorter than four characters | judge |
| 30 | `sleep` in a test | block |
| 31 | Test importing past the entry-point boundary: an absolute import through a `lib`, `internal`, `_internal` or `impl` segment | block |
| 32 | More mocks than assertions | judge |
| 33 | Asserting that a call happened | judge |
| 34 | *Removed.* Counting assertion subjects flagged 32 sound tests and no unsound ones (incident 005) | - |
| 36 | Test name joining two things with `_and_` | judge |

A test calling `pytest.fail`, `raises`, `warns` or `xfail`, or one whose name says it covers
a failure, counts as asserting. That is why the stubs `scaffold_tests.py` writes pass rule 27.

## Obligations: `detect_gaps.py`

Runs in: CLI, and the `lld-contract-conformance` hook in the enforcement template. **Not in
the gate**: it reads the module and its suite together, and a write only ever shows one.

| # | Rule | Tier |
| --- | --- | --- |
| 35 | An obligation from the source with nothing in the suite covering it | block for a public name no test mentions, or a raised type no `pytest.raises` expects; judge for every guard boundary |

Obligations from the contract's Preconditions table are scaffolded as stubs but not checked
by rule 35.

## Contracts

| # | Rule | Script | Runs in | Tier |
| --- | --- | --- | --- | --- |
| 37 | Contract and module disagree about the interface | `conformance.py` | gate, when a contract exists | block for a promised name that is missing, a parameter list that differs (names, in order, keyword-only included), or a return annotation that disagrees; judge for a public name the contract never mentions |
| 38 | A derived block no longer matches the code | `derive.py` | gate, when the contract has derived blocks; `derive.py --check` | block |
| 39 | Projected docstring conditions no longer match the Preconditions table | `conditions.py` | `conditions.py --check` only | judge in the finding; `--check` still exits 1 |

Rule 37 compares against the first fenced block in the contract's `## Interface` section.
After `derive` has run, that is the derived block. Parameter annotations are parsed but not
compared: `def area(r: int)` in the contract against `def area(r: float)` in the module
passes. `conformance.py`'s docstring says otherwise; the code is what runs.

Rule 37 has no CLI. It runs only inside the gate, so a module edited outside Claude Code is
never checked against its contract until the next gated write.

**Value of 37-39.** A contract nobody checks drifts from its module and then misleads with
authority. 37 catches the hand-written interface lying; 38 catches the generated half going
stale; 39 catches the docstring conditions CrossHair reads going stale.

The gate skips "no derived block" findings: a contract without them is a migration state.
`derive.py --check` reports them and exits 1.

## Contract structure

Not numbered. `contracts.validate_contract` refuses a contract that is missing a required
section, leaves one empty or holding a placeholder (`TODO`, `TBD`, `...`, `<...>`,
`{{...}}`), has no valid `**Status:**`, or fails a per-section check. The gate runs it on new
modules. The full list is in [contracts.md](contracts.md#what-validation-refuses).

## Exit codes

Every detector CLI follows the same convention:

| Code | Meaning |
| --- | --- |
| 0 | nothing blocking (judge findings may still be printed) |
| 1 | at least one `block` finding, or `--check` found something stale |
| 2 | a file could not be read or does not parse, or the contract is missing; for `diagrams.py`, a label left the approved vocabulary |
| 3 | `diagrams.py` only: the `dataviz` skill was not found |
