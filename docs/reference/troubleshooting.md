# Troubleshooting

Every refusal and error message the scripts can print, what causes it, and the fix. Copied
from `scripts/` at 0.7.0; `<...>` marks the part that varies. For a walkthrough by symptom
("the gate never refuses anything"), see [the guide](../guide/troubleshooting.md).

## The gate refused a write

The refusal text is the `permissionDecisionReason` the model sees. The same decision is one
line in `.lld/gate.log`.

### `No contract for <path>.`

A **new** `.py` file under a `src/` segment, and `docs/contracts/<dotted.path>.md` does not
exist. Write the contract ([contracts.md](contracts.md)), then repeat the write. The path in
the message is the one to create; it is resolved against the session's working directory.

Only new files need one. If the file already existed on disk, this message cannot appear.

### `The contract at <path> does not validate:`

Followed by one line per problem. Each, and its fix:

| Line | Fix |
| --- | --- |
| `missing section: ## <name>` | add the `## <name>` heading. All nine are required: Responsibility, Interface, Preconditions, Seam, Dependencies, Errors, Observability, Tests, Deletion test |
| `section is empty or still a placeholder: ## <name>` | the body is empty, or a line is only `TODO`, `TBD`, `...`, `<...>` or `{{...}}`. Write the content |
| `missing **Status:** line` | add `**Status:** draft` |
| `Status must be one of ['accepted', 'draft', 'superseded'], got '<x>'` | use one of those three |
| `## Interface has no signature in a code block` | put the signatures in a fenced block |
| `## Dependencies has no 'May import' line` | add `- **May import:** ...` |
| `## Errors needs a table, or the sentence 'No error modes.'` | one or the other |
| `## Observability names no level; say what is logged at INFO and what raises it, or state 'No logging.'` | name a level (`debug`, `info`, `warning`, `error`), or write `No logging.` |
| `## Preconditions needs a table, or the sentence 'No preconditions.'` | one or the other |
| `## Preconditions has a table with no rows; use 'No preconditions.' instead` | add rows, or replace the table with the sentence |
| `## Preconditions row for '<param>' names no verdict; use one of reject, clamp, propagate` | the third cell must contain one of the three words |
| `## Tests lists <n> behaviours; at least 3 are required` | three or more `-` or `*` bullets |

Validation runs only on the first write of a new module. An **existing** module whose
contract does not validate is not refused for it; rules 37 and 38 still read whatever the
contract says.

### `These anti-patterns are decided by the AST and cannot be waived:`

One or more `block` findings, each as `line <n>: [<rule>] <name> - <message>`. No waiver
clears these. Change the code, or for rules 37 and 38, the contract. The rule number indexes
[rules.md](rules.md); the reasoning and the fix are in
[ANTI-PATTERNS.md](../../skills/design-patterns/ANTI-PATTERNS.md).

The **whole resulting file** is checked, not your diff. A one-line edit to a legacy module is
refused for a `block` finding anywhere in it. See every finding first:

```
python <plugin>/scripts/detect_patterns.py <file>
```

Rule 37 and 38 lines, which name the contract rather than a code shape:

| Message | Cause | Fix |
| --- | --- | --- |
| `the contract promises <name>, which the module does not define` | the Interface block lists a name the write does not define | write every promised name in one write; `...` bodies are fine |
| `<name>: parameters are [<actual>], contract promises [<declared>]` | names, order, or keyword-only parameters differ | make them match; edit the contract first if the contract is wrong |
| `<name>: returns <x>, contract promises <y>` | return annotations differ | same |
| `<Class> is constructed with [<actual>], contract promises [<declared>]` | `__init__` parameters (or dataclass fields) differ from `Class(...)` in the contract | same |
| `the contract promises <Class>.<member>, which the module does not expose; ...` | a `.member` line under a class names nothing the class has | add it, or remove the line |
| `<Class>.<member> is <x>, contract promises <y>` | the member's return type differs | same |
| `the derived block in ## <section> no longer matches the code; regenerate it` | rule 38: the contract has `<!-- derived -->` blocks and this write changes a public signature, an import, an importer or a raise | see below |

### Rule 38 refuses a deliberate interface change

`derive` reads the file on disk, which the refused write has not changed, so running it does
not help. Either edit the derived block by
hand to what the new code will produce, repeat the write, then confirm with
`derive.py <module> --check`; or make the change with the gate off (`LLD_GATE=off claude`),
run `/lld-seed:derive`, and restart with it on. A limitation of 0.7.0. Deriving only after the
interface has settled avoids most of it.

### `These shapes need your judgment. Fix them, or record why they stand:`

`judge` findings with no waiver. Fix the code, or append the row the message prints to
`docs/contracts/_waivers.md` and repeat the write:

```markdown
| src/shapes/circle.py | 8 | 2026-10-29 | the instance is the seam tests substitute |
```

The path must match the message exactly. The rule is a bare number. A row that does not
parse is ignored silently, so a waiver that "does not work" is usually a malformed row: four
cells, rule as digits, path relative to the project root. Ledger format:
[gate.md](gate.md#the-waiver-ledger).

A public name the contract never mentions is rule 37 at `judge`: document it in the
Interface block, make it private, or waive 37 for the module.

### `<path> already carries <n> waivers. Repeated exceptions on one module are evidence about the module. Redesign it rather than adding another.`

Appended to a refusal when the module has three or more waiver rows. It does not block on
its own; the refusal it is attached to does.

### `A test that cannot fail does not test anything:`

A write to a test file (`test_*.py`, `*_test.py`, or under a `tests/` segment, anywhere in
the project) with a `block` test finding: rule 27 (asserts nothing), 30 (`sleep`) or 31
(imports through `lib`/`internal`/`_internal`/`impl`). Test `judge` findings are listed
under `Also worth a look, not blocking:` and never refuse a write.

A test counts as asserting if it has an `assert`, calls `raises`/`warns`/`fail`/`xfail`,
calls a helper named `check*`/`verify*`/`assert*`/`expect*`, or has a failure word in its
name (`rejects`, `invalid`, `error`, `missing`, ...).

## The gate allowed something it should not have

It stands aside, by design, when:

| Condition | Log line |
| --- | --- |
| `LLD_GATE=off` in the environment Claude Code started with | none - it exits before configuring logging |
| the path has no `src` segment, or is excluded (`__init__.py`, `conftest.py`, `setup.py`; a `tests`, `test`, `scripts`, `migrations`, `_generated` or `generated` segment) | `allow <tool> <path>: outside the gate's scope` |
| the resulting content does not parse | `allow <path>: content does not parse (<reason>)` |
| the edit could not be applied (non-string `old_string`/`new_string`) | `allow <tool> <path>: resulting content could not be determined` |
| reading the file, contract or ledger raised `OSError` | `WARNING ... standing aside, the gate could not run: <error>` |
| stdin was not JSON | none |

No `.lld/gate.log` at all means the hook never ran: Claude Code was not restarted after
installing the plugin, or `python` is not on the `PATH` (the hook calls `python`, not
`python3`). If `lld: cannot open log file <path>: <error>` appears on stderr, the gate ran
but could not write the log; set `LLD_LOG_FILE` to a writable path.

## Command and script errors

| Script | Message | Exit | Cause and fix |
| --- | --- | --- | --- |
| `derive.py`, `conditions.py` | `no contract at docs/contracts/<x>.md` | 2 | run from the project root; pass `--src-root` if packages are not under `src/` |
| `derive.py`, `conditions.py` | a `FileNotFoundError` traceback | 1 | the contract exists but the module path does not; neither script catches it |
| `derive.py --check` | `<contract>: ## <section> has no derived block; run the derive command to add one` | 1 | never derived. Run `derive.py <module>`. The gate ignores this case; `--check` does not |
| `derive.py --check` | `<contract>: the derived block in ## <section> no longer matches the code; regenerate it` | 1 | the code moved; run `derive.py <module>` |
| `conditions.py --check` | `<module>:<line>: <func>: the generated conditions no longer match the contract. Has [...], the contract says [...]. Regenerate rather than edit.` | 1 | rule 39. Run `conditions.py <module> --write` |
| `conditions.py` | the whole module printed to stdout | 0 | intended: without `--write` it previews. Add `--write` |
| `conditions.py` | `<module>: already current`, but no conditions appear | 0 | each function needs a docstring, and each `propagate` condition must parse as Python; prose rows and `clamp` rows emit nothing |
| `scaffold_tests.py` | `cannot read <module>: <error>` | 2 | the module must exist on disk; write the interface first |
| `scaffold_tests.py` | `<module> does not parse: <error>` | 2 | fix the syntax |
| `scaffold_tests.py --write` | `<path> exists, left alone` | 0 | intended: it never overwrites. Delete the file to regenerate it |
| `scaffold_tests.py` | `no obligations: the module exposes nothing and raises nothing` | 0 | nothing public; check the module is the one you meant |
| sandbox | `ModuleNotFoundError` | 1 | it imports by dotted name. `cd src && python -m <pkg>.tests.sandbox_<module>`, or install the package. `commands/scaffold-tests.md` shows a direct `python <path>` run, which fails this way |
| `detect_gaps.py` | `BLOCKING` lines for every public name | 1 | the suite is not at `<module dir>/tests/test_<module>.py`, so it reads as empty |
| `detect_tests.py` | `no test anti-patterns detected` on a file you expected findings for | 0 | paths that are not test files are skipped silently |
| `detect_patterns.py`, `detect_tests.py`, `detect_gaps.py` | `cannot read <path>` / `<path> does not parse` | 2 | as stated |
| `diagrams.py` | `the dataviz skill is required and was not found.` | 3 | set `LLD_DATAVIZ=/path/to/dataviz`; the directory must contain `references/palette.md`. Also searched: `~/.claude/skills/dataviz`, and `<tmp>/claude/bundled-skills/*/*/dataviz` |
| `diagrams.py` | `labels or captions left the approved subset:` | 2 | a generated label or caption failed the `ste.py` vocabulary check, and nothing is written. The report names the label; report it with the package that triggered it |
| `diagrams.py --check` | `<path>: stale, regenerate it` | 1 | run it without `--check` |
| `sweep.py` | `not a directory: <root>` / `no Python files under <root>` | 2 | as stated |
| `merge_claude_md.py` | `cannot read <generated>` | 2 | the temporary file was not written |

## The sweep's numbers look wrong

They often are, in known ways. Before believing a dead figure, confirm the entry points:
a script with no `if __name__` guard, code a framework dispatches, and a library's public
API all read as dead. A helper under five statements is never reported as a clone. The full
list, and a three-file repository that reproduces both failures:
[sweep.md](sweep.md#before-a-verdict).
