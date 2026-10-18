# Phase 4: self-review of a module built with the system

A 60-line module (`ledger.balance`) built end to end through the `new-module` flow, then
reviewed against every rule in the plugin. It passes `ruff`, `mypy --strict`, `pytest` and
the anti-pattern detector with zero findings.

It has six defects. That gap is the finding.

## What the mechanical tier caught

Nothing, after incident 004 was fixed. The module is clean under all 26 anti-patterns.

## What review caught that no tool did

**1. `running_balance` is a noun phrase.** `FORMAT.md` requires verb phrases for functions —
"a name that reads as a noun gives no clue whether calling it does anything". The name should
be `compute_balance`. The author of that rule broke it within an hour of writing it, and no
gate noticed.

**2. `currency: str` leaves illegal states representable.** `READABILITY.md` requires making
them unrepresentable. `Entry(amount_minor=1, currency="not a currency")` type-checks. It
should be a `NewType` with a validating factory, or an `Enum` of the currencies in use. Rule
12 did not fire because the parameter is never compared against string literals — the
detector tests for one symptom of stringly-typing, not the condition.

**3. `Money` and `Entry` are structurally identical.** Two frozen dataclasses, same two
fields, different names. Apply the deletion test to `Entry`: nothing reappears. It is a type
that exists for a distinction the code does not yet make.

**4. The exceptions carry no structured data.** The contract promises the caller can "name
the offending index", but the index is embedded in a message string. Any caller that wants it
must parse prose. `CurrencyMismatchError` should carry `index` and `currency` as attributes.
The contract and the implementation disagree, and the contract validator checks only that
the section exists.

**5. The RED step was weaker than TDD requires.** The six tests failed together with one
`ModuleNotFoundError`, not individually for their own reasons. "If you didn't watch the test
fail, you don't know if it tests the right thing" — a collection error proves only that the
import is missing.

**6. One assertion is brittle.** `assert "1" in str(caught.value)` matches any `1` anywhere in
the message. It would pass against a wrong message. No rule in the corpus covers assertion
strength, which is a gap rather than a violation.

## What this says about the system

The division of labour claimed in `SCOPE.md` holds, and the costs are now measured rather
than asserted:

- **Structure is mechanically enforceable, and the enforcement works.** Frozen value types,
  empty `__init__`, no module state, no import-time work, no blind excepts, full annotations
  — all free, all checked, zero effort at review time.
- **Meaning is not.** Naming, type-level modelling, whether two types are really one, whether
  a contract matches its implementation. Every one of the six defects is semantic, and every
  one needs a reader.

The honest conclusion: this plugin raises the floor and does not raise the ceiling. It makes
undesigned code hard to write. It does not make well-designed code automatic, and anyone who
reads a green gate as "this is good" will ship all six of these.

## Gaps this surfaced in the corpus

- No rule covers assertion strength, so defect 6 has nothing to cite.
- No check that a contract's promises match the implementation. The validator is structural
  only; defect 4 passed it.
- `FORMAT.md`'s verb-phrase rule has no detector, and it is mechanically checkable for the
  common cases — a function whose name is a bare noun with no verb.
