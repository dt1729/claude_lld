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
