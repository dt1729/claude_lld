# Workflow

Two loops. **Loop 1** writes new code and ships complete: every step below exists in
`scripts/` or `skills/`. **Loop 2** diagnoses code that already exists; part of it ships, and
part is direction that is not built. The direction is labelled as such wherever it appears.

The model reads the short form of this page as the [workflow skill](../../skills/workflow/SKILL.md).
Terms (module, interface, seam, depth, adapter) are in [GLOSSARY.md](../../GLOSSARY.md).

## Which loop

| You have | Start at |
| --- | --- |
| A module, class or public function to add | [Loop 1](#loop-1-writing-new-code), step 1 |
| A new file the gate just refused | Loop 1, step 1, for that module |
| An edit to an existing file the gate refused | the rule number in the refusal; [rules.md](../reference/rules.md), then [troubleshooting.md](../reference/troubleshooting.md) |
| A repository you did not design | [Loop 2](#loop-2-diagnosing-existing-code) |
| A verified finding on someone else's repository | `/lld-seed:propose <owner/repo>` |

## Loop 1: writing new code

```
contract ─▶ interface ─▶ scaffold-tests ─▶ implement ─▶ conditions ─▶ derive ─▶ commit
   │            │              │               │             │            │
 gate refuses  rule 37      stubs fail      gate checks   raises: /     rule 38 now
 the new file  checks names until written   every write   pre: lines    guards the
 until valid   and params                                               blocks
```

Each step's output is the next step's input. All paths assume the module is
`src/<pkg>/<module>.py` and every command runs from the project root.

### 1. Contract

| | |
| --- | --- |
| Use | [codebase-design](../../skills/codebase-design/SKILL.md) to decide the interface and seam; [new-module](../../skills/new-module/SKILL.md) steps 1-2 to place the module and write the contract |
| Input | what the module is for, and who calls it |
| Output | `docs/contracts/<pkg>.<module>.md` that validates ([contracts.md](../reference/contracts.md#what-validation-refuses)) |
| Gate | refuses the first write of `src/<pkg>/<module>.py` until the contract exists and validates |

Nine sections are required. Four carry the design:

- **Interface**: the public signatures, in a fenced block. This is what rule 37 compares the
  code against.
- **Seam**: what varies behind the interface, and what you rejected.
- **Preconditions**: one row per parameter, each with a verdict. `reject` raises on purpose
  outside the range; `clamp` coerces into the range and raises nothing; `propagate` leaves
  it undefined and makes the caller responsible. `No preconditions.` is a complete answer
  when nothing can be got wrong.
- **Deletion test**: what reappears in callers if this module vanishes. If the answer is
  "nothing", do not create it.

The rest - Responsibility, Dependencies (`May import`), Errors, Observability, Tests (three
bullets or more) and a `**Status:**` of `draft`, `accepted` or `superseded` - are checked for
presence, not quality. `draft` validates.

### 2. Interface

| | |
| --- | --- |
| Input | the contract |
| Output | `src/<pkg>/<module>.py` with every promised public name, the exact parameters and annotations, and the guards each `reject` row demands. Bodies may be `...` |
| Gate | rule 37: a promised name that is missing, a parameter list that differs, or an annotation that disagrees is a `block`; a public name the contract never mentions is a `judge` |

Write the whole interface in one write. A partial one is refused for the names it leaves out.
This step has to come before step 3: `scaffold_tests.py` reads the module's syntax tree and
exits 2 when there is no file.

### 3. Scaffold the tests

| | |
| --- | --- |
| Run | `/lld-seed:scaffold-tests src/<pkg>/<module>.py` |
| Input | the module on disk; the contract's Preconditions |
| Output | `src/<pkg>/tests/test_<module>.py`, one failing stub per obligation; `src/<pkg>/tests/sandbox_<module>.py`. Neither is overwritten if it exists |
| Gate | test rules 27-33, 36 on every later write to the test file. The stubs call `pytest.fail`, which counts as asserting, so they pass rule 27 |

Obligations come from the code: every public name, every `raise`, every comparison guarding
a raise. `reject` rows in the contract add rejection stubs. `--list` prints the obligations
without writing anything.

Run the sandbox before writing any assertion: `cd src && python -m <pkg>.tests.sandbox_<module>`.
It reports import cost, file writes, and what each constructor does with values either side
of its guards. A slow import or a file written during construction is a finding.

### 4. Implement

| | |
| --- | --- |
| Use | [test-design](../../skills/test-design/SKILL.md) for the assertions; [logging](../../skills/logging/SKILL.md), [design-patterns](../../skills/design-patterns/SKILL.md), [python-style](../../skills/python-style/SKILL.md) for the bodies |
| Output | each stub replaced by an assertion a plausible bug would break, and renamed for what it covers; the bodies written |
| Gate | every write to the module: rules 1-10, 12-15, 19-24, and 37. Every write to the test file: rules 27-33, 36 |
| Check | `python <plugin>/scripts/detect_gaps.py src/<pkg>/<module>.py` - rule 35, an obligation nothing in the suite covers. The gate does not run it |

Watch each test fail before it passes. If the interface turns out wrong, edit the contract
first, then the code: rule 37 refuses the code change otherwise.

### 5. Conditions

| | |
| --- | --- |
| Run | `/lld-seed:conditions src/<pkg>/<module>.py` to print the projection, then again with `--write` |
| Input | the contract's Preconditions rows; functions that already have docstrings |
| Output | between `.. derived from` and `.. end derived` markers in each docstring: `raises: <Error>` for a `reject` row, `pre: <condition>` for a `propagate` row, nothing for `clamp` |

Functions without a docstring are skipped, and so are rows written as prose rather than a
Python expression. CrossHair executes the result; without CrossHair it is documentation in a
checkable shape. `conditions.py --check` exits 1 when the docstrings no longer match the
table (rule 39). Nothing runs that check unless you do.

### 6. Derive

| | |
| --- | --- |
| Run | `/lld-seed:derive src/<pkg>/<module>.py` |
| Output | `<!-- derived -->` blocks in the contract for Interface (signatures), Dependencies (imports out, `Imported by` in) and Errors (types raised). Your prose beneath each block is never touched |
| Gate | from now on, rule 38 refuses any write to the module that would make a block stale |

Derive last. Once the blocks exist, adding a public name, an import or a raise is refused
until the contract is regenerated, so finish the interface first. The parser reads only what
is written literally: a dynamic import, a re-export or a raise inside a called helper does
not appear. Write those in the prose under the block.

### 7. Commit

| | |
| --- | --- |
| Use | [commits](../../skills/commits/SKILL.md) |
| Output | one commit per reason to change. The subject says what changed; the body says why, and what was rejected when the choice was contested |

The contract, the module and its suite usually belong in one commit: they are one decision.
A refactor that enables the module is a separate, earlier commit.

### Done

- [ ] the contract validates; `Status: accepted` (validation accepts `draft`; this asks for more)
- [ ] `detect_gaps.py <module>` reports nothing blocking
- [ ] every test was seen failing, and fails for one reason
- [ ] `derive.py <module> --check` and `conditions.py <module> --check` exit 0
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` and pre-commit green
- [ ] every waiver row is one you would defend to a reviewer

## Loop 2: diagnosing existing code

### What ships today

| Step | Run | Output |
| --- | --- | --- |
| 1. Sweep | `/lld-seed:sweep <root>` | the text report: counts of `core` / `shared` / `dead`, dead fraction, feature-local count per entry, top ten overlap pairs, top ten clone groups with their sites |
| 2. Get the lists | `python <plugin>/scripts/sweep.py <root> --json` | `core`, `dead` and `feature_local` as names; `overlap`; `duplication_rate`. The clone groups are only in the text report; `shared` is only a count |
| 3. Confirm entry points | list every file a person runs directly; check each was found | the entry points the dead set actually depends on |
| 4. Read | the dead list grouped by module and class; the top clone groups opened in the source | candidate findings |
| 5. Verify | the "Before a verdict" checks in [sweep.md](../reference/sweep.md#before-a-verdict) | findings that survive, each with a file and line |
| 6. Act | your repository: Loop 1 for each module you change. Someone else's: `/lld-seed:propose <owner/repo>` | a change, or one pull request or issue |

The sweep walks every `.py` under the root regardless of layout, unlike the gate. It finds
entry points by lookup: `if __name__ ...` guards, `[project.scripts]`, framework decorators,
a module-level `app = ...`, alembic `upgrade`/`downgrade`. Clones are Type-1/2 only:
function and class bodies hashed with names, attributes and literal values erased, five
statements or more counting the `def`.

The documented caveats, each of which has produced a wrong headline:

- **A script with no main guard is not an entry point.** Everything only it reaches reads
  as dead.
- **A library has no in-repo callers.** `kind: library` means the dead set is the public
  API.
- **Framework dispatch is invisible.** Dunders, `__post_init__`, pydantic validators,
  `HTMLParser.handle_*`, Qt slots.
- **Deliberate copies are not clones.** Snapshots, vendored files, a file that says it is a
  copy.
- **Tests inflate duplication.** An unparametrised suite shows as many clones.
- **Monorepos overlap at 1.00.** An artifact of workspace packages.
- **A helper under five statements is never a clone**, however many files copy it. A
  one-line `def` is two. Grep for short repeated helpers by hand.

**Done** means every reported item names a file and line, was confirmed by opening the
source, and is classified: dead, framework-dispatched, library API, deliberate copy, or real
duplication. No percentage is quoted without the list behind it.

### Worked example: two sweeps on 2026-10-24

Two of the author's repositories, swept with the plugin as it ships.

**openarm_control reported 21.6% dead. Most of it was not.** `make_gif.py` and
`make_plots.py` are run directly but have no `if __name__ == "__main__"` guard; their work
happens at module level. The sweep found no entry point in either, so the functions they
call - `follow_waypoints`, `record_gif`, `save_data`, `load_data` - had no path from any
entry and landed in the dead list. Step 3 catches this: `make_gif.py` is a file a person
runs, and it is not in the entry-point list.

**manipulation_vision's sweep missed six helpers copied four times.** `individual_touch.py`,
`orange_individual_touch.py`, `nine_sphere_touch.py` and `tactile_video.py` in `scripts/`
each define the same six one-liners:

```python
def jnt_adr(m, n): return m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n)]
def act_id(m, n):  return mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, n)
def body_id(m, n): return mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, n)
def site_id(m, n): return mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, n)
def geom_id(m, n): return mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, n)
def even(x):       return x if x % 2 == 0 else x + 1
```

Each is two statements; the floor is five. Twenty-four definitions, none of them hashed, and
the report says nothing. `grep -n "^def " scripts/*.py | sort -t: -k3` finds them in a second.

**The gate never fired on any of this code.** Both repositories keep it in `scripts/`, which
has no `src` segment and is excluded by name even under one. The detectors and the sweep still run on
that code by hand; the gate does not. Only test-named files (`scripts/test_cam.py` in
manipulation_vision) would be checked, against the test rules.

[sweep.md](../reference/sweep.md#example) reproduces the first two failures on a three-file
repository.

### Direction, not implemented

**Nothing in this section exists in `scripts/`.** It is where Loop 2 is meant to go, drawn
from the sweeps above. Do not describe it as a feature.

| Today | Direction |
| --- | --- |
| The headline is dead% and duplication% | The headline is **concentration**: inequality of module size, inequality of fan-in, and how far the directory tree disagrees with the import graph |
| Percentages | **Named findings**, each checkable by opening two files |
| A dead figure is printed whatever the entry points | **No dead figure until the entry points are confirmed.** The report lists what it found and the scripts it could not classify, and withholds the number |
| A plugin directory nobody imports reads as dead | A plugin directory is a **declared boundary**: code a host loads is not dead |
| "Clone", "duplication rate" | **"Shape collision"**: the detector erases identifiers, so a shape is what it compares |

Until then, steps 3 and 5 above are how the first and third rows get done: by hand.

## Adopting on an existing repository

[getting-started.md](getting-started.md#first-15-minutes-a-repository-that-already-exists)
has the order. Short form: Loop 2 first; run `detect_patterns.py` over the files you will
touch, because the gate checks the whole file on every edit; write contracts only for the
modules you are about to change; Loop 1 for everything new.
