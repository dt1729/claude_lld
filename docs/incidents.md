# Incidents

Every rule in this plugin should trace back to something that actually went wrong. This is
that record: one entry per observed failure, what it cost, and what changed because of it.

A rule with no incident behind it is a prediction. Predictions are allowed, but they are
weaker than scars and should be the first things challenged when the corpus needs pruning.

---

## 001 — The detector over-fires on real code it did not write

**Date:** 2026-10-17
**Found by:** first run against an unseen repository (`openarm_control`, 15 modules,
2,199 lines, no tests, no linter config, flat `scripts/` layout)

**What happened.** 132 findings in 2,199 lines — one every 17 lines. Had the gate been live
while that code was written, almost every write would have been blocked. Three distinct
defects, all in the detector rather than the code:

1. **False positives on pure constructors.** Ten module-level `np.array([...])` constants
   were reported as import-time side effects. A constant built from a value constructor is
   data, not work.
2. **One defect reported twice.** A module-level `print` fired both rule 03 (import-time
   side effect) and rule 19 (`print` in a package module); `basicConfig` fired both 03 and
   20. Roughly 15 of the 132 were duplicates, which inflates the apparent severity and
   makes the report read as noise.
3. **Wrong tier, not wrong rule.** `sys.path.insert`, module-level `argparse` setup and
   `matplotlib.use` are genuine side effects *and* near-universal in scripts. Blocking on
   them is how a gate gets switched off in week two.

**What changed.**

- `PURE_CALLS` gained the value constructors (`array`, `zeros`, `deque`, `Counter`, …).
- `CLAIMED_BY_OTHER_RULES`: rule 03 stays silent on anything rules 19 and 20 already report.
- `IMPORT_TIME_IDIOMS`: the common script idioms report as `judge`, not `block`.

Findings fell 132 → 107, and rule 03's blocking count fell 36 → 3. What remains is
load-bearing: 40 eager f-string log calls, one class inheriting a concrete base, three
genuine import-time side effects (`yaml.safe_load(open(...))`, a simulation constructed at
module scope).

**What it says about the corpus.** The rules were right; the calibration was invented. Every
threshold in this plugin was set by reasoning rather than measurement, and this is the first
one measured. Expect the same of the others.

**Still open.** 24 `print` findings came from forcing `scripts/` to be the package root for
this test. In normal use the gate excludes `scripts/` entirely, so they would never fire —
which means the rule is untested for the case it actually governs, not that it is wrong.

---

## 002 — The detector's CLI could only take one file

**Date:** 2026-10-17
**Found by:** wiring it into pre-commit and running it

**What happened.** `pre-commit` passes every staged file as an argument. The parser declared
a single positional `path`, so the hook failed with
`unrecognized arguments: scripts/contracts.py scripts/logsetup.py ...` the first time it ran
for real. Every batch caller — pre-commit, a shell glob, CI — was broken.

**Why it survived 134 tests.** All of them call `detect()`, the library function. Nothing
exercised `main()`. The tests covered the logic and skipped the interface, which is the
failure mode the plugin's own guidance warns about: *the interface is the test surface*.

**What changed.** `paths` is now `nargs="+"`, findings are grouped per file, and the exit
code is the OR across them.

---

## 003 — The detector caught a stringly-typed parameter in the gate itself

**Date:** 2026-10-17
**Found by:** running the detector over its own repository in pre-commit

**What happened.** Rule 12 fired on `resulting_source(tool: str, ...)` in
`require_contract.py`: a `str` parameter compared against three string literals
(`"Write"`, `"Edit"`, `"MultiEdit"`). Exactly the shape `CATALOGUE.md` says to replace with
a dispatch when the set is closed — and the set is closed, because it is the same set the
gate watches.

**What changed.** Three named appliers in a `dict`, dispatched by lookup.
`WATCHED_TOOLS` is now derived from that dict rather than declared separately, so the tools
the gate watches and the tools it knows how to apply cannot drift apart.

**Why this one matters.** It is the first finding the system produced against code written
*after* the rule existed, by an author who had read it. Guidance alone did not prevent it;
the detector did. That is the argument for mechanical enforcement, observed rather than
asserted.

---

## 004 — The detector blocked the shape the guidance prescribes

**Date:** 2026-10-17
**Found by:** building a sample feature end to end with the gate in the loop (phase 4d)

**What happened.** A module defining a normal exception hierarchy was blocked:

```python
class LedgerError(Exception): ...


class EmptyLedgerError(LedgerError): ...  # rule 04: BLOCK


class CurrencyMismatchError(LedgerError): ...  # rule 04: BLOCK
```

`FORMAT.md` requires exactly this — *"Name every error type for its condition"*, with the
worked example `class CalibrationMissingError(DetectionError)`. So one half of the plugin
instructed a shape the other half refused, and the refusal was unwaivable because rule 04
is `block` tier.

**Root cause.** Rule 04 resolved only the *immediate* base. `OPEN_BASES` contains
`Exception`, but `LedgerError`'s subclasses name `LedgerError`, not `Exception`, so the
exemption never applied past the first level.

**What changed.** `_local_exception_types` computes the transitive closure of classes
deriving from `Exception`, and rule 04 and rule 05 both skip them. An exception tree is the
one case where inheriting from a concrete class of your own is correct — it is the mechanism
by which a caller chooses the granularity it catches at — and depth in such a tree is a
feature, not a smell. Three regression tests pin it, including one proving a non-exception
concrete base still blocks.

**Why this one matters most.** The other incidents were a detector being noisy. This was the
system contradicting itself, and it was unwaivable, so following the guidance made the gate
unusable. No amount of review would have found it: it took writing one real module. Everything
in this plugin written without that loop should be assumed to contain more of these.

---

## 005 — Three of ten test rules were wrong on first contact

**Date:** 2026-10-18
**Found by:** a dogfood test asserting this repo's own suite passes the rules it defines

**What happened.** The test tier was specified as ten rules and implemented in one sitting.
Run against the 137 tests already in this repo, three of them misfired:

- **Rule 34** (one test covering several behaviours) counted distinct names inside assert
  statements as a proxy for distinct subjects. `assert 1 in rules(src)` followed by
  `assert verdict_of(src, 1) == BLOCK` reads as four subjects when it is one behaviour
  checked twice. 32 findings, every one of them sound code.
- **Rule 28** (no failure case) looked only for `pytest.raises`. The detector suites test
  failure by asserting a rule fires, and `merge_claude_md` raises nothing at all. 5 findings,
  all wrong, and all at block tier.
- **Rule 36** (name joins two behaviours) matched `_and_`, which cannot distinguish
  `test_validates_and_saves` from `test_class_with_init_and_one_method`. 6 findings, mostly
  naming one thing.

**What changed.** Rule 34 was removed from the detector: counting assertion subjects has no
signature that separates the two cases, so it is reviewed rather than detected, alongside
entries 17, 18, 25, 26 and 35. Rule 28 is now judgment, needs five tests before it applies,
and treats a failure-shaped test name as a failure case. Rule 36 is judgment.

**What it says about the corpus.** Seven of ten rules survived contact; three did not, and
two of the three would have blocked correct code. The same ratio should be assumed for any
tier written in one sitting — which is the argument for building the C/C++ tier against real
repositories rather than from a specification.

**Worth noting:** the rules were caught by a test that applies them to the suite that defines
them. That test is cheap, and every future tier should ship with one.

---

## 006 — The plugin told people to write tests from prose while holding an AST

**Date:** 2026-10-18
**Found by:** the user asking, three times, whether the AST generated the tests

**What happened.** `new-module` step 3 said "the contract's Tests section is a list of
behaviours; turn each into a test". That list is written by hand, so it records what the
author remembered, and it goes stale the moment a branch is added. Meanwhile the plugin
already parsed every module it governed - and used that only to check work after the fact.
Rule 35, the one rule that would have read obligations off the source, was prose with no
implementation and a note excusing it: "needs the module-to-test mapping, which the detector
does not build."

**What changed.** `obligations.py` reads obligations off the syntax tree: every public name,
every raise, and the guard that produces one. `scaffold_tests.py` turns them into failing
stubs and a sandbox script. `detect_gaps.py` implements rule 35 against them. The skills now
instruct the session to run the tool rather than read the file, and say why.

**What it does not do.** Generate assertions. A generated `assert result is not None` passes
the gate, raises the count and proves nothing - the exact shallow test this plugin exists to
prevent. The AST supplies the obligation; a reader supplies the judgment.

**Caught on the way in, by this repo's own gates:** rule 27 fired on two tests of the new
scaffolder that called `ast.parse` and asserted nothing, and mypy caught a bytes constant
that would have written `b'...'` into a generated test name.
