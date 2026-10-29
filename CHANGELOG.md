# Changelog

Versions are `0.x`: the shape is still moving, so a minor bump may break a contract you
already wrote. Each entry says which ones do.

## Unreleased

Proposed as 0.8.0; see `docs/release/0.8.0-plan.md`. The release where the documentation
started being read off the scripts instead of off earlier prose.

### Breaking

None. A contract that validates under 0.7.0 still validates; no script that reads a
contract, a waiver row or a hook payload has changed.

### Docs

- `docs/guide/`: getting started (new and existing repositories, the restart a hook needs),
  the two loops step by step with each step's input, output and gate, and a troubleshooting
  page with one section per refusal whose cause is not obvious.
- `docs/reference/`: the gate, every numbered rule with its script and tier, contracts,
  commands, skills, the sweep, the detectors and the enforcement templates - each
  enumerated from `scripts/`.
- The README is the front door again: pitch, install, the two loops, and a feature table
  that says what each part prevents and links to its reference page. Its Status section
  said 254 tests and its badge 265; the suite has 356 passing and 1 skipped.

### Skills

New: `workflow`. Says which loop to start in, which command comes next, and what done
means. It lists the diagnose-side direction - concentration as the sweep headline, no dead
figure until entry points are confirmed, "shape collision" for clones - as **not built**,
so the model does not describe it as a feature.

### Known wrong, now documented

Two sweeps on 2026-10-24 were wrong in ways the docs now name and the `workflow` skill tells
the model to check by hand: a script with no main guard is not an entry point, so
openarm_control read 21.6% dead, mostly falsely; and helpers under five statements are
never hashed, so six one-line helpers copied across four files in manipulation_vision went
unreported. Neither is fixed in code yet.

**Still unverified**, unchanged from 0.5.0: the `PreToolUse` hook has never been observed
intercepting a write inside a live session.

## 0.7.0 — 2026-10-23

The release where contracts started saying what a function refuses, and the sweep started
reading its own lists.

### Breaking

- **Contracts now require a `Preconditions` section.** Every contract written against 0.6.0
  or earlier stops validating until the section is added. That break is accepted rather than
  versioned around: this is 0.x, the install base is small, and re-running the seeding
  regenerates a contract in the new shape. (proposal 001)

### Preconditions

`Errors` asks what a function **raises**. It never asks what a function **refuses**, so
filled in honestly it is a changelog of current behaviour rather than a specification. The
new section asks the other question — one row per parameter, and one of exactly three
verdicts:

| Verdict | Means |
| --- | --- |
| `reject` | raise, naming the offending value |
| `clamp` | substitute a safe value and log at WARNING |
| `propagate` | documented precondition, deliberately unchecked |

`No preconditions.` is a complete answer. `propagate` is legitimate — a function called per
frame should not revalidate what its caller guarantees — and is also the verdict that will
be abused, so `verdict_counts` makes the distribution countable the way the waiver ledger
counts judgments.

This came from outside: a session applying 0.5.0 to a real package put every gate green on
code with no input validation anywhere. `Range: bytes=100-50` returned `Content-Length: -49`
to a browser; a field of view of 180 degrees built a camera with a focal length of `5.9e-14`
and drew every bearing without a word. The limit is structural — `detect_patterns.py`
answers questions about shape, and "this function divides by a number the caller controls"
is a question about the relationship between a parameter and what is done to it. The full
proposal, with its measurements, is `docs/proposals/001-preconditions.md`.

Step 1 of the proposal: the section and its validator. No Semgrep, no new engine.

### The table is executable now, in two directions

**Tests.** `scaffold_tests.py` emits one rejection stub per `reject` row, named
`test_rejects_<parameter>`. The stub still fails until a person writes it - no generated
assertion, the rule the whole scaffolder follows - but it says what to do rather than
`not written yet`, and offers the boundary values from the condition, which is where
off-by-one lives. `clamp` and `propagate` rows produce nothing: clamp substitutes rather
than raises, so a test asserting an exception would be wrong, and propagate is the author
stating that nothing is checked.

**Conditions.** `/lld-seed:conditions` projects the table into the module's own docstrings,
where CrossHair can read it. A contract in `docs/contracts/*.md` is a contract nothing can
run - CrossHair reports `Targets found, but contain no checkable functions` against a module
whose claims are all in markdown.

The verdict decides which condition is correct, and this is the part that is easy to get
backwards. CrossHair's `pre:` means *assume this holds, do not explore outside it*:

| Verdict | Emits | Why |
| --- | --- | --- |
| `reject` | `raises: <Error>` | The function is total. A `pre:` would tell CrossHair to skip the exact inputs the guard exists for |
| `clamp` | nothing | Total, defined everywhere, raises nothing |
| `propagate` | `pre: <condition>` | The one case where a precondition is literally true |

Emitting `pre:` everywhere - the obvious implementation - would suppress exactly the
counterexamples worth having. See `docs/proposals/001a-where-contracts-execute.md`.

The projection edits a file you already own, so it never writes without `--write`, skips a
function with no docstring, and skips a prose condition rather than emit an unparseable
`pre:`. Rule 39 reports a block that has drifted from its contract.

### Sweep

Two new commands. `/lld-seed:sweep` runs the repository-level reachability and duplication
analysis that until now lived only in `scripts/sweep.py`, and `/lld-seed:propose` turns one
verified finding on someone else's repository into a pull request or issue, with the bar for
what may be sent written down: one finding, verified in the source, carrying its own tests,
no sales pitch.

The detector itself was measured against 125 Claude-authored repositories on the way, and
most of what it called dead was its own blindness. Each gap is now closed, with a test
naming the repository that exposed it:

- a dotted name handed around as a value (`{"process": jobs.process}`) was not an edge;
  55 of 291 definitions in one repository read as dead, 8 after;
- `Foo()` never reached `Foo.__init__`, so constructors and everything only they set up
  read as dead;
- a callback bound as `self._send` was not a reference; 127 of 859 in one tkinter app;
- `@mcp.tool` and friends were not framework decorators; 253 of 886 in one MCP server;
- `app = FastAPI()` and `app = create_application()` were not entry points;
- a module's import-time body was not part of reaching it, so a table like
  `SCREENS = [Gate(fn=_margin)]` left every function in it dead - 66 in one screener. The
  main guard is now the one block an import does not run.

What remains known-wrong is listed in the command: framework dispatch (`HTMLParser`
handlers, pydantic validators, dunders), libraries whose API has no in-repo callers, and
deliberate copies. Those need a reader, and the command says to be one.

## 0.6.0 — 2026-10-21

The release where the plugin stopped choosing its own colours.

### Breaking

- **The `dataviz` skill is now a prerequisite.** It ships with Claude Code. `lld-seed`
  designs nothing of its own: every palette, surface and typeface in a generated diagram is
  a role from `dataviz/references/palette.md`. `/lld-seed:diagram` exits 3 with the install
  instruction rather than draw a figure whose colours nothing validated. If the skill lives
  somewhere the script does not look, name it: `LLD_DATAVIZ=/path/to/dataviz`.

### Why it became a requirement

The diagrams shipped in 0.5.0 with a palette picked by hand here. Colour in them carries
meaning — blue is a type, red is an error — so that was an accessibility decision made by
taste. The validator `dataviz` ships failed it on three of five checks:

```
[FAIL] CVD separation      #b3282b <-> #3f7d20  dE 1.3 (deutan)
[FAIL] Normal-vision floor #8a6400 <-> #3f7d20  dE 11.8   (floor 15)
[FAIL] Lightness band      dark: 3 of 4 slots outside L 0.48-0.67
```

Delta-E 1.3 is the finding. The two colours separating an error from a success were, for a
reader with deuteranopia, one colour. The roles now in use pass the same validator at
delta-E 23.8 light and 25.7 dark against a floor of 8.0.

Fixing the hexes and continuing to choose them was the rejected alternative: it leaves the
next person free to pick by eye, which is the failure rather than the symptom. So the rule is
written in `SCOPE.md`, `README.md`, `CLAUDE.md` and `commands/diagram.md`, `find_dataviz`
enforces it, and `scripts/tests/test_palette.py` pins every role to its shipped value.
(incident 010)

### Also in this release

- Standalone diagrams are readable on a dark page. They were emitted with `currentColor`,
  which resolves only for inline SVG; as files referenced as images every stroke fell back to
  near-black. Colours are literal now, with a `prefers-color-scheme` block and a `data-theme`
  scope, which is the pattern `dataviz` prescribes.
- Prose in a figure follows the shipped rule — system sans, no serif. Identifiers stay in
  mono, the one documented departure: a node label is a name the reader has to grep for.
- 265 tests, up from 254.

### Known limits

- Only the palette and type come from `dataviz`. Its other steps — mark specs, the hover
  layer, the legend and direct-label pass, the anti-patterns catalogue — are not applied to
  these diagrams yet.
- Control-flow layout places nodes in declaration order, so a raise target can sit in an
  earlier row than the function raising into it and those arrows point upward.

**Still unverified**, unchanged from 0.5.0: the `PreToolUse` hook has been exercised with
real payloads through the exact command the manifest declares, but never observed
intercepting a write inside a live session.

## 0.5.0 — 2026-10-21

The release where the tooling stopped only checking work and started producing it.

### Breaking

- **`Depth` is gone from contracts.** Contracts carried
  `Depth: junior | senior | principal`, borrowed from a model-tier budget where it meant
  something. In a contract it described nothing about the module, so it was a label an
  author gave their own effort and nobody could check. Remove the line; validation no
  longer asks for it. (incident 009)
- **Folder `CLAUDE.md` is no longer generated by default.** `/lld-seed:scaffold-guidance`
  swept a repository and `new-module` told every module to run it. A module's contract is
  checked against its code and a folder file is not, so a folder file repeating a contract
  was an unchecked second copy. It now needs a reason, and the command asks rather than
  sweeping. Existing folder files are left alone. (incident 009)

### The contract's factual half is now generated

`Interface`, `Dependencies` and `Errors` sit inside `<!-- derived -->` markers and come from
the syntax tree. Everything outside the markers is yours and is never touched. `Imported by`
comes from a reverse import graph across `src/`, which no single file can answer and which an
external audit found wrong in ten contracts.

A hand-written fact can be wrong; a generated one can only be stale, and stale is one
command. Rule 38 checks currency. A contract with no derived blocks is a migration state, not
a defect.

```
/lld-seed:derive src/shapes/square.py
```

### Tests are derived from the source, not from prose

`scaffold_tests.py` reads every public name, every `raise` and every guard that produces one,
and writes a failing stub per obligation plus a sandbox script that runs the module alone in
a fresh process. It writes no assertions: a generated `assert result is not None` passes the
gate, raises the count and proves nothing. `detect_gaps.py` keeps the obligations met.

### Four diagrams, drawn from the AST

Inheritance, module dependencies, per-module control flow and error flow, as SVG. Every
arrow carries one verb from a closed list and every caption is held to a checkable subset of
ASD-STE100, so two diagrams of different packages read the same way. The official ASD-STE100
dictionary is a published specification and is not bundled; this is a conforming subset and
says so.

### Rules

- 27-36: test quality. A test that asserts nothing, a sleeping test and a deep import block;
  weak substrings, mock-heavy tests and two-behaviour names are handed to judgment.
- 37: the module must match the interface its contract promises.
- 38: a derived block must still match the code.
- 19-26: logging. `print` in a package, configuration below the composition root, eager
  f-string formatting, an exception logged without its traceback.

Rule 34 was specified, built, and removed: counting assertion subjects flagged 32 sound tests
in this repo and no unsound ones. (incident 005)

### Skills

New: `logging`, `test-design`, `commits`. The `commits` skill moves this repo's own git
conventions into something a governed repo receives.

### Enforcement

`ruff.toml`, `mypy.ini`, `.pre-commit-config.yaml` and an `.importlinter` template. Until
0.5.0 every claim about ruff enforcing complexity had no configuration behind it.

### Honesty

`docs/incidents.md` records nine incidents — every rule that turned out wrong on contact with
real code, including three of ten test rules that misfired on their first run and two rules
that existed only by analogy. `docs/phase-4-review.md` records six defects in a module that
passes every gate.

**Still unverified:** the `PreToolUse` hook has been exercised with real payloads through the
exact command the manifest declares, but never observed intercepting a write inside a live
session.

## 0.1.0 — 2026-10-17

First release. The vocabulary (`GLOSSARY.md`), the design skills (`codebase-design`,
`design-patterns`, `python-style`), the contract format, the `PreToolUse` gate, the
anti-pattern detector, and the folder-guidance generator.
