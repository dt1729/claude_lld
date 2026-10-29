# Commands

Seven slash commands. Each is a prompt in `commands/` that tells the model which script to
run and how to read the result; the scripts live in `scripts/` and run without Claude Code
too. Inside Claude Code the plugin directory is `${CLAUDE_PLUGIN_ROOT}`. Outside it, use a
clone of this repository.

Run every script **from the project root**: contracts are found at `docs/contracts/`
relative to the current directory. Every script takes `--log-level` except `derive.py` and
`conditions.py`.

| Command | Argument | Script | Writes |
| --- | --- | --- | --- |
| [`scaffold-tests`](#scaffold-tests) | `<module path>` | `scaffold_tests.py`, `detect_gaps.py` | `tests/test_<m>.py`, `tests/sandbox_<m>.py` |
| [`conditions`](#conditions) | `<module path>` | `conditions.py` | the module's docstrings, with `--write` |
| [`derive`](#derive) | `<module path> [--check]` | `derive.py` | the module's contract |
| [`diagram`](#diagram) | `<package path>` | `diagrams.py` | `docs/diagrams/*.svg` |
| [`scaffold-guidance`](#scaffold-guidance) | `[path]` | `merge_claude_md.py` | a folder `CLAUDE.md` |
| [`sweep`](#sweep) | `<repo root>` | `sweep.py` | nothing |
| [`propose`](#propose) | `<owner/repo> [pr\|issue]` | `sweep.py`, `git`, `gh` | a branch, fork and PR, or an issue |

---

## scaffold-tests

**What.** Reads a module's syntax tree and its contract's Preconditions table, and lists
every test the suite owes. Then writes one failing stub per obligation, and a sandbox script
that imports the module alone and probes its constructors.

**When.** After the module's interface exists on disk, before writing any assertion.

**Value.** A test list made by reading the file is a plausible list that misses the branch
added last week. The AST does not. The stubs fail until written, so none passes by accident.

```
/lld-seed:scaffold-tests src/shapes/square.py
```

```
python scripts/scaffold_tests.py <module> --list     # obligations only
python scripts/scaffold_tests.py <module>            # print obligations, skeleton and sandbox
python scripts/scaffold_tests.py <module> --write    # write both files; never overwrites
python scripts/detect_gaps.py <module>               # what is still owed (rule 35)
```

Options: `--src-root` (default `src`), `--log-level`.

| Kind | From | Means |
| --- | --- | --- |
| `precondition` | a `reject` row in the contract | a test must violate the condition and see the rejection |
| `public-name` | a public `def` or `class`, and public methods of a public class | a caller can reach it |
| `raise` | a `raise X(...)` | the failure path is real |
| `boundary` | the comparison in an `if` that directly guards a raise | the threshold, where off-by-one lives |

```
7 obligations from the AST:
  line   0  [precondition] side_m                       -> test_rejects_side_m
  line   8  [public-name] InvalidSideError             -> test_invalid_side_error_behaves_as_documented
  line  13  [public-name] Square                       -> test_square_behaves_as_documented
  line  20  [boundary   ] side_m at and just below 0   -> test_side_m_boundary_is_respected
  line  20  [raise      ] InvalidSideError             -> test_raises_invalid_side_error
  line  22  [public-name] Square.area_m2               -> test_square_area_m2_behaves_as_documented
  line  27  [public-name] scale                        -> test_scale_behaves_as_documented
```

A generated stub, verbatim (the generator wraps the message itself; `ruff format` would join
it back onto one line):

```
def test_rejects_side_m() -> None:
    """The contract promises side_m is rejected unless side_m > 0. Nothing proves that until a test
    violates it.

    Obligation: precondition from the contract's Preconditions table, row 1.
    """
    pytest.fail(
        "pass a side_m violating side_m > 0 (the boundary values are 0) and "
        "assert the rejection"
    )
```

The sandbox imports the module by its dotted name, so run it as a module from the directory
that contains the package (`src/` here), or with the package installed:

```
cd src && python -m shapes.tests.sandbox_square
```

```
import shapes.square: 8.06 ms
constructions:
  InvalidSideError()                   -> InvalidSideError()  (0.00 ms)
  Square(side_m=1.0)                   -> Square(side_m=1.0)  (0.00 ms)
  Square(side_m=0.0)                   raised InvalidSideError: 0.0
  Square(side_m=-1.0)                  raised InvalidSideError: -1.0
files written: none
```

It asserts nothing. An import over 100 ms prints `slow: something is happening at module
scope`; a file created in the temporary working directory is listed.

`commands/scaffold-tests.md` says to run the sandbox as `python <package>/tests/sandbox_<module>.py`.
That fails with `ModuleNotFoundError: No module named 'shapes'`; use `python -m` as above.

`detect_gaps.py` straight after scaffolding still blocks:

```
src/shapes/square.py (suite: src/shapes/tests/test_square.py):
BLOCKING (2):
  line 20: [35] InvalidSideError - The module raises InvalidSideError; a test must expect it, or nothing proves the failure path works. Nothing in the suite covers it; scaffold_tests.py will write the stub (test_raises_invalid_side_error).
  line 22: [35] Square.area_m2 - Square.area_m2 is part of the public surface of Square. Nothing in the suite covers it; scaffold_tests.py will write the stub (test_square_area_m2_behaves_as_documented).
NEEDS JUDGMENT (1):
  line 20: [35] side_m at and just below 0 - ...
```

The stubs exist; what is missing is a `pytest.raises(InvalidSideError)` and a reference to
`area_m2`. A stub's name does not count as a mention. These clear when the assertions are
written, which is the point. Ignore the "will write the stub" wording.

Limits: no assertions are generated, by design. The scaffolded test file reports ruff `F401`
on its import line until the stubs use the names. With no module on disk the script exits 2.
`clamp` and `propagate` rows produce no stub.

---

## conditions

**What.** Projects the contract's Preconditions table into the module's own docstrings, as
conditions CrossHair can read.

**When.** After the contract's Preconditions table and the function docstrings exist.

**Value.** A contract in `docs/contracts/` is a claim nothing executes. CrossHair reads
docstrings, and reports `Targets found, but contain no checkable functions` against a module
whose claims are all in Markdown.

```
/lld-seed:conditions src/shapes/square.py
```

```
python scripts/conditions.py <module>            # print the projected module
python scripts/conditions.py <module> --write    # edit the module in place
python scripts/conditions.py <module> --check    # exit 1 if a block has drifted (rule 39)
```

Option: `--src-root`. Exit 2 when the contract is missing.

| Verdict | Emits |
| --- | --- |
| `reject` | `raises: <Error>` |
| `clamp` | nothing |
| `propagate` | `pre: <condition>`, only if the condition parses as Python |

Output for a `propagate` row on `factor`:

```python
def scale(square: Square, factor: float) -> Square:
    """A new square with every side multiplied by factor.

    .. derived from docs/contracts/shapes.square.md - regenerate, do not edit
    pre: factor > 0
    .. end derived
    """
```

It touches module-level public functions and public methods of public classes. It skips a
function with no docstring, a prose condition, and private methods - so a `reject` row on a
dataclass field checked in `__post_init__` produces nothing. It reproduces a claim; it cannot
improve one. CrossHair is not bundled; install it to run the conditions.

---

## derive

**What.** Regenerates the `Interface`, `Dependencies` and `Errors` blocks of a contract from
the module's syntax tree, inside `<!-- derived -->` markers.

**When.** Once the interface has settled, and again whenever it changes.

**Value.** A hand-typed fact goes wrong; a generated one can only go stale, and stale is one
command. An external audit found ten contracts with a wrong `Imported by` line (incident 008).

```
/lld-seed:derive src/shapes/square.py
```

```
python scripts/derive.py <module>            # rewrite the blocks
python scripts/derive.py <module> --check    # exit 1 if a block is stale or missing
```

Option: `--src-root`. Exit 2 when the contract is missing.

```
docs/contracts/shapes.square.md: derived blocks regenerated
```

`--check` on a contract that has never been derived:

```
docs/contracts/shapes.square.md: ## Interface has no derived block; run the derive command to add one
docs/contracts/shapes.square.md: ## Dependencies has no derived block; run the derive command to add one
docs/contracts/shapes.square.md: ## Errors has no derived block; run the derive command to add one
```

The gate checks the same thing on every write (rule 38), but skips "no derived block". No
pre-commit hook in this repository or the enforcement template runs `derive --check`, despite
`commands/derive.md` saying pre-commit does; add one or run it in CI.

**Run it from the project root.** The `Imported by` line comes from walking `--src-root`
relative to the current directory. The contract path does too, so from anywhere else it
exits 2 rather than writing a wrong line.

What the first run does to your hand-written sections is in
[contracts.md](contracts.md#derived-and-declared).

---

## diagram

**What.** Four SVG views of a package drawn from the AST: inheritance, module dependencies,
control flow per module, and error flow. Every arrow uses one verb from `raises`, `imports`,
`is`, `catches`, `calls`; every caption stays in a checked subset of ASD-STE100
(`scripts/ste.py`).

**When.** Reviewing a package's shape, or putting a picture beside its contracts.

**Value.** Two diagrams of different packages read the same way, and they are regenerated
rather than drawn, so they cannot drift.

**Requires the `dataviz` skill.** Every colour is a role from its `references/palette.md`.
The script looks in `LLD_DATAVIZ`, then `~/.claude/skills/dataviz`, then the bundled skills
directory under the system temp dir.

```
/lld-seed:diagram src/shapes
```

```
python scripts/diagrams.py <package> --out docs/diagrams   # write
python scripts/diagrams.py <package> --check               # exit 1 if a file is stale
```

Options: `--out` (default `docs/diagrams`), `--src-root`, `--log-level`. Files are named
`<package>.<view>.svg`.

| Exit | Meaning |
| --- | --- |
| 0 | written, or every diagram current |
| 1 | `--check` found a stale file |
| 2 | a label or caption left the approved vocabulary |
| 3 | the `dataviz` skill was not found |

Without the skill it prints the instruction and exits 3:

```
the dataviz skill is required and was not found.
...
look, name the directory: LLD_DATAVIZ=/path/to/dataviz
```

Limits: `errors` matches exception types by name, not resolved symbol. `dependencies` sees
literal imports only. Control-flow layout follows declaration order, so some arrows point
upward.

---

## scaffold-guidance

**What.** Writes or refreshes a folder `CLAUDE.md` from `templates/FOLDER-CLAUDE.md.template`,
preserving every `<!-- manual -->` block.

**When.** Only when an agent will work in a folder and there is something local it cannot
read off the code or the contracts. Not for a library package whose modules have contracts.

**Value.** Orientation where it is needed, without an unchecked second copy of the contracts
everywhere else (incident 008).

```
/lld-seed:scaffold-guidance src/detection
/lld-seed:scaffold-guidance                 # lists qualifying folders and asks
```

The model reads the folder, writes the content to a temporary file, then merges:

```
python scripts/merge_claude_md.py <folder>/CLAUDE.md --generated <temp>
python scripts/merge_claude_md.py <folder>/CLAUDE.md --generated <temp> --stdout   # preview
```

Prints `updated <path>` or `unchanged <path>`; idempotent. The command ends with a table of
folder, action and line count, and lists anything it could not determine.

---

## sweep

**What.** Reachability and duplication over a whole repository, any layout.

**When.** First contact with a repository you did not design, before proposing anything
about it.

**Value.** The lists behind the numbers: which definitions no entry reaches, which code only
one feature uses, which shapes appear twice.

```
/lld-seed:sweep .
```

```
python scripts/sweep.py <root>           # report
python scripts/sweep.py <root> --json    # kind, definitions, unresolved, core, dead, feature_local, overlap, duplication_rate
```

Full reference, including what the numbers get wrong: [sweep.md](sweep.md).

---

## propose

**What.** Clones someone else's repository, sweeps it, verifies one finding in the source,
and sends it as a pull request (default) or an issue.

**When.** You found something on a repository you do not own and want the maintainer to be
able to say yes in one reply.

**Value.** The bar is written down: one finding, verified by opening the files, carrying its
own test evidence, no sales pitch, and an offer to drop it.

```
/lld-seed:propose someone/their-repo
/lld-seed:propose someone/their-repo issue
```

Steps the command follows: `git clone --depth 1`, `sweep.py <dir> --json`, read the lists
under "Before a verdict", pick the one finding that is in production code, checkable in two
files and fixable in one commit; then branch, change, run the touched tests and the repo's
linter, `gh repo fork --clone=false`, push, `gh pr create`. Requires `git` and an
authenticated `gh`.

It publishes to someone else's repository. Read the diff and description before it is sent.
