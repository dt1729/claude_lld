# Proposal: precondition checking in lld-seed

**For:** whoever is working on `dt1729/claude_lld`
**From:** a session applying lld-seed v0.5.0 to a real repository (`trackscope`)
**Date:** 2026-10-21
**Status:** proposal, nothing implemented

> **Received into the repo 2026-10-21, unedited.** It is kept verbatim because it is
> evidence from a session that was not ours, and trimming it to fit would be editing the
> measurements. Written against v0.5.0; the current release is 0.6.0, which changed nothing
> this proposal depends on. Tracking and decisions live in `docs/proposals/README.md`.

---

## 1. How this came up

lld-seed v0.5.0 was applied end to end to `trackscope`, a ~1,000-line Python package
serving a browser dashboard over the standard library. The seeding went well and is not
the subject of this document. Four contracts were written, the enforcement configs landed,
116 tests were added where there had been 24, and every gate went green:

```
ruff            All checks passed
mypy --strict   Success: no issues found
import-linter   2 contracts kept, 0 broken
pytest          116 passed, 3 xfailed
lld detectors   clean
pre-commit      11 hooks passed
```

The repository owner then read the three modules and asked why none of them has any input
validation. They were right. Every gate above is green on code with no precondition
checking anywhere.

**This is not a complaint about the seeding. It is a gap in what the system can see.**

---

## 2. The evidence

Each of the following is reachable from a CLI flag, an HTTP header, or a file on disk.
None is an internal caller doing something perverse. All were executed, not reasoned about.

| Input | Result |
| --- | --- |
| `Range: bytes=100-50` | **`Content-Length: -49`** sent to the browser |
| `--hfov 0` | `ZeroDivisionError`, traceback |
| `--hfov 180` | `fx = 5.9e-14`. No error. Every bearing in the run is garbage |
| `--hfov -65` | `fx = -1506`. Negative focal length. No error |
| `--width 0` | `fx = 0`, principal point `(-0.5, -0.5)`. No error |
| `geo.json` with `lat: 1000` | Accepted. Returns a coordinate |
| `offset_to_latlon` at latitude 90 | Longitude **14,670,601,919,589** |
| `NaN` in a CSV cell | Propagates as `nan` through range and bearing |
| `geo.json` missing `lat` | `KeyError` — though the same function guards `origin is None` |

The silent cases matter more than the crashes, and there are more of them.

The repository's own README states its purpose: *"Not for showing that a run worked. For
working out whether to believe it."* It refuses to draw a target position without a camera
heading, because a default would be "a specific wrong answer that looks exactly like a
right one." It then accepts `--hfov 180`, builds a camera model with a focal length of
5.9e-14, and draws every bearing without a word.

The design rigour went into the module boundaries and skipped the front door.

---

## 3. Why lld-seed did not see it

Not an oversight in the rules. A structural limit.

`detect_patterns.py` is 982 lines of hand-written Python `ast` visitors. It answers
questions about **shape**: how many branches, how many returns, is this class holding
mutable state, does this module import across a boundary. It found twelve real structural
problems in one module, correctly.

"This function divides by a number the caller controls" is not a shape question. It is a
question about the relationship between a parameter and the operations performed on it.
No amount of adding visitors to that file reaches it, and every visitor added is Python-only
forever.

Two related observations from the same exercise:

**The contract's `Errors` section asks the wrong question.** It asks what a function
*raises*. It never asks what a function *refuses*. Filled in honestly, it becomes a
changelog of current behaviour rather than a specification.

**Symptoms get filed as isolated incidents.** The trackscope contracts record
`KeyError escapes build()` and `OSError escapes __main__` as two separate "recorded gaps".
They are not two gaps. They are two visible instances of one systemic absence, and writing
them down separately made the absence feel handled.

---

## 4. What was trialled

Four tools were run against the real functions. Results are measured, not quoted from
documentation.

### Hypothesis — property-based testing

Three properties, stated the way a contract would state them. **3.9 seconds. Found all
three bugs, with minimised counterexamples:**

```
test_focal_length_is_positive_and_finite  → ZeroDivisionError
test_a_shifted_point_stays_on_the_earth   → AssertionError (the pole case)
test_range_is_never_a_nan                 → cam=(0.0, nan, 0.0)
                                            "or any other generated value"
```

That last line is Hypothesis isolating *which* argument caused the failure.

### CrossHair — symbolic execution

First run, against the functions as they are:

```
WARNING: Targets found, but contain no checkable functions.
```

**CrossHair only analyses functions carrying a precondition or postcondition in the code.**
Moving the same claims from markdown into the function body changed everything:

```
error: ZeroDivisionError: when calling intrinsics_from_fov(1, 1, 5e-324)
error: ValueError: math domain error when calling intrinsics_unguarded(0, 0, inf)
```

No tests written. And `5e-324` is a denormal float that satisfies the precondition
`0 < hfov < 180` which a human wrote — **CrossHair produced a better counterexample than
the person specifying it.**

### Hypothesis ghostwriter — comparison with `scaffold_tests.py`

```python
@given(width=st.integers(), height=st.integers(), hfov_deg=st.floats())
def test_fuzz_intrinsics_from_fov(width: int, height: int, hfov_deg: float) -> None:
    probe_mod.intrinsics_from_fov(width=width, height=height, hfov_deg=hfov_deg)
```

Runnable. `scaffold_tests.py` currently emits `pytest.fail("not written yet")`.

### Semgrep — pattern matching across languages

Not run against trackscope, but its language support was verified:

| | |
| --- | --- |
| Python | Generally available, cross-file dataflow |
| C / C++ | Generally available, cross-file dataflow |
| Licence | Semgrep CE is LGPL-2.1; Opengrep is a fully open fork |
| Rules | YAML that looks like source code |
| Speed | Seconds — fast enough for a `PreToolUse` hook |

### A dependency worth noticing

CrossHair needs type annotations. trackscope's four modules have annotation debt deferred
by name in `ruff.toml` and `mypy.ini`. So:

```
annotate  →  contract as code  →  CrossHair, icontract-hypothesis
```

**The annotation debt is not cosmetic. It blocks every deep tool in this list.** Worth
saying out loud in the skills, because "defer the annotations" currently reads as a free
choice.

---

## 5. The proposal

### 5.1 The unit — a `Preconditions` section in the contract

This is the centre of the proposal. Everything else reads from it.

One row per parameter. The author must pick one of exactly three answers:

| Parameter | Must satisfy | On violation |
| --- | --- | --- |
| `hfov_deg` | `0 < hfov_deg < 180` | **reject** — `ValueError` naming the value |
| `width` | `> 0` | **reject** |
| `rate_limit` | `> 0` | **clamp** to the default, log at WARNING |
| `marks` | ascending `t`, caller guarantees | **propagate** — documented precondition, unchecked |

`reject` / `clamp` / `propagate`. Choosing is a design decision, which is lld-seed's entire
thesis — decide before writing. Today nothing in the contract format asks the question.

`propagate` is deliberately available. A function called per frame should not re-validate
what its caller guarantees. The point is that the choice is recorded, not that everything
is checked.

### 5.2 The engine — Semgrep

It is the only candidate meeting the "Python, C++, and C" requirement, and the one that
matches the actual complaint. The complaint was *absence of guards*, and absence-of-guard
is what a pattern matcher is for.

A second reason matters more for the plugin's future: porting the 38 existing rules from
`detect_patterns.py` to Semgrep YAML makes them multi-language for free, and turns a new
rule from a visitor class into a five-line file.

### 5.3 The split between fast and slow

Do not ask one tool to do both.

| Stage | Tool | Why |
| --- | --- | --- |
| Write gate — blocking | Semgrep | Seconds. Finds a missing guard |
| CI — thorough | Hypothesis, CrossHair (Python) | Minutes. Finds an insufficient guard |
| CI — thorough | libFuzzer + ASan/UBSan (C/C++) | For anything that parses bytes |

**Semgrep would not have found `hfov = 5e-324`.** It finds that a guard is missing, not
that a guard is wrong. That division is correct and should be stated in the skill so nobody
expects otherwise.

---

## 6. Where it embeds

Five insert points in the existing flow.

```
  design ──► CONTRACT ──► GATE ──► implementation ──► tests ──► commit
               (A)        (B)          (C)            (D)        (E)
```

### A. Contract format — start here

| File | Change |
| --- | --- |
| `skills/new-module/CONTRACT-FORMAT.md` | Document the `Preconditions` section and the three verdicts |
| `scripts/contracts.py` | Add `"Preconditions"` to `REQUIRED_SECTIONS` (line 21) |
| `scripts/contracts.py` | Validate: a table, or the sentence `No preconditions.` |
| `skills/codebase-design/SKILL.md` | Add the question to the design procedure |

This is a **schema change**, not a rule and not code. It is also the cheapest piece and the
one everything else depends on.

A migration note: adding a required section invalidates every existing contract in every
repo already seeded. Either ship it behind a contract-format version field, or accept the
break and say so in the changelog.

### B. The gate

`scripts/require_contract.py` already refuses a write with no contract. Extend it: refuse a
write whose public function has a `Preconditions` row with verdict `reject` and no matching
guard in the body.

This is where Semgrep runs, because it is the only one fast enough for a `PreToolUse` hook
with a 10-second timeout.

### C. The rule engine

`rules/python/*.yaml`, `rules/c/*.yaml`, `rules/cpp/*.yaml`.

Keep the 38 existing rules; port them. Add the validation family:

- a public function indexes a dict parameter without `.get` or a membership test
- a parameter reaches division, `math.*`, `int()` or `float()` with no guard
- a public function's numeric parameter is used in arithmetic with no range check
- **C/C++**: a pointer parameter is dereferenced without a null check; an index derived
  from a parameter has no bounds check; `memcpy`/`strcpy` takes a caller-supplied length

### D. Test scaffolding

`scripts/scaffold_tests.py`. Each `Preconditions` row becomes:

- a test named `test_rejects_<param>_<condition>`, for every `reject` row
- one Hypothesis property per numeric parameter, from the stated range

This is the step that makes the contract executable. The same table then drives the guard,
the gate, and the test — which is the property lld-seed already claims for its derived
blocks, extended to the half that matters most.

### E. Pre-commit and CI

| File | Change |
| --- | --- |
| `templates/enforcement/.pre-commit-config.yaml` | Add a `semgrep --config <plugin rules>` hook |
| `templates/enforcement/README.md` | Add semgrep to the install line |
| New: `templates/enforcement/ci-deep.yml` | CrossHair and Hypothesis, or the C/C++ fuzz lane |

---

## 7. Architecture: rule, library, or dependency?

The question was asked directly, so here is the precise answer. Four distinct things, and
only one is new code inside the plugin.

| Piece | Kind | Where |
| --- | --- | --- |
| `Preconditions` section | **Schema** — a change to the design artifact | `templates/`, `CONTRACT-FORMAT.md`, `contracts.py` |
| The ruleset | **Data** — YAML, no code | `rules/{python,c,cpp}/*.yaml`, shipped with the plugin |
| Semgrep | **External dependency** — installed, never vendored | the user's environment |
| `scripts/detect_guards.py` | **New plugin code** — an adapter, ~150 lines | `scripts/` |

**lld-seed already has this exact pattern.** It depends on ruff, mypy, import-linter and
pre-commit today, named in `templates/enforcement/` and installed by the user rather than
bundled. Semgrep becomes the fifth. The one difference: lld-seed would ship its *own*
ruleset rather than only a config file, because the rules encode lld-seed's opinions rather
than a community default.

### Keep the stdlib-only property

The README advertises `runtime deps: stdlib only`. Preserve it:

- `detect_guards.py` subprocesses to `semgrep --json` and parses the result. It does not
  `import semgrep`.
- Semgrep absent → print a note on stderr and exit 0, the same way the plugin's own absence
  should be handled by a consumer. A contributor fixing a typo must not need Semgrep
  installed.
- Map Semgrep's JSON into the existing `Finding` dataclass in `scripts/findings.py`
  (`rule, name, line, verdict, message`) so output, the waiver ledger in
  `docs/contracts/_waivers.md`, and `format_report` all keep working unchanged.

That last point is why the adapter is small. Everything downstream of `Finding` already
exists.

### Rule numbering

The existing rules are numbered 1–38, and waivers reference them by number
(`| trackscope/server.py | 3 | 2026-10-21 | reason |`). Allocate the validation family a
reserved block — 40–59, say — so Semgrep-sourced findings never collide with AST-sourced
ones, and a waiver stays readable about which engine produced the finding.

---

## 8. Limits, stated up front

Put these in the skill, not in a FAQ. Each one is a thing a user will otherwise discover as
a disappointment.

- **Semgrep finds missing guards, not wrong guards.** `hfov = 5e-324` passes a handwritten
  precondition and still breaks the function.
- **CrossHair is timeout-bounded.** "Verified" means "no counterexample found in 30
  seconds", not a proof.
- **Ghostwriter output needs editing.** An empirical study of 203 tests found ~18% fully
  automatable, 30% needing adaptation, 52% incompatible. It is a stub generator, not an
  oracle.
- **`propagate` is a legitimate verdict and will be abused.** If a repo's contracts are all
  `propagate`, the section has become a formality. Worth a report line counting the
  distribution, the way the waiver ledger already counts judgments.

---

## 9. Suggested order

1. **A alone.** The `Preconditions` section plus its validator. No Semgrep yet. This is
   useful on its own: it makes the design question unavoidable, which is most of the value.
2. **D.** `scaffold_tests` emits a rejection test per `reject` row. Now the contract is
   executable and the gap is visible as a failing test.
3. **C + B.** The Semgrep ruleset and the adapter. The gate starts enforcing what A declared.
4. **E.** The deep CI lane, per language.
5. **Port the 38 rules to YAML.** Only now, and only if steps 1–4 proved the engine out.
   This is the step that brings C and C++ into the plugin, and it is the largest.

Step 1 is worth doing even if nothing else is. Steps 3 and 5 are where the multi-language
claim becomes real.

---

## 10. Sources

- [Semgrep supported languages](https://semgrep.dev/docs/supported-languages) ·
  [CE languages](https://semgrep.dev/docs/semgrep-ce-languages) ·
  [rule syntax](https://docs.semgrep.dev/writing-rules/rule-syntax) ·
  [Opengrep comparison](https://docs.semgrep.dev/faq/comparisons/opengrep)
- [CrossHair: contracts](https://crosshair.readthedocs.io/en/latest/contracts.html) ·
  [kinds of contracts](https://crosshair.readthedocs.io/en/latest/kinds_of_contracts.html)
- [icontract](https://github.com/Parquery/icontract) ·
  [icontract-hypothesis](https://github.com/mristin/icontract-hypothesis)
- [Hypothesis integrations and ghostwriter](https://hypothesis.readthedocs.io/en/latest/reference/integrations.html) ·
  [empirical study of property-based testing](https://link.springer.com/article/10.1007/s10664-026-10953-w)
- [C++26 contracts](https://pkglog.com/en/blog/cpp26-contracts-guide/) ·
  [sanitizers handbook](https://gist.github.com/MangaD/3b46e4c5ef4c63e44a21bed39ae64093) ·
  [libFuzzer guide](https://qaskills.sh/blog/libfuzzer-c-cpp-testing-guide)

---

## Appendix A: raw probe output

```
geo.py
  offset_to_latlon at the north pole          returned (90.0, 14670601919589.61)
  offset_to_latlon with latitude 1000         returned (1000.0, 0.00517319154274426)
  project_target, origin dict with no lat     KeyError: 'lat'
  project_target, heading as a string         TypeError: must be real number, not str
  camera_to_local_enu, 2-tuple instead of 3   ValueError: not enough values to unpack
  bearing_and_range with a NaN component      returned (0.0, nan, nan)

data.py
  intrinsics_from_fov(--hfov 0)               ZeroDivisionError: float division by zero
  intrinsics_from_fov(--hfov 180)             returned {'fx': 5.878304635907295e-14, ...}
  intrinsics_from_fov(--hfov -65)             returned {'fx': -1506.8981540327907, ...}
  intrinsics_from_fov(--width 0)              returned {'fx': 0.0, 'cx': -0.5, 'cy': -0.5, ...}
  detect_teleports(rate_limit=0)              returned [{'t': 1.0, 'rate': ...}]
  discover() on a file, not a directory       NotADirectoryError

server.py — the Range header, straight off the wire
  bytes=0-9              -> code=206 Content-Length=10
  bytes=100-50           -> code=206 Content-Length=-49     <-- malformed response
  bytes=500-499          -> code=206 Content-Length=0
  bytes=-                -> code=206 Content-Length=2048
  bytes=abc-def          -> code=200 Content-Length=2048
```

## Appendix B: the CrossHair experiment

The only change between these two runs is where the contract lives.

**Contract in `docs/contracts/trackscope.data.md`:**

```
WARNING: Targets found, but contain no checkable functions.
```

**Same claims, in the docstring:**

```python
def intrinsics_from_fov(width: int, height: int, hfov_deg: float) -> dict:
    """
    pre: width > 0
    pre: 0 < hfov_deg < 180
    post: __return__["fx"] > 0
    """
```

```
error: ZeroDivisionError: when calling intrinsics_from_fov(1, 1, 5e-324)
```

> lld-seed writes contracts to `docs/contracts/*.md`, where nothing can execute them.
> CrossHair needs the same facts in the function. Same information, two places, and only
> one of them is checkable.

Whether lld-seed should emit `icontract` decorators, CrossHair docstring conditions, or
plain guard clauses is a separate decision. The observation stands regardless of which.
