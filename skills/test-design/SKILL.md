---
name: test-design
description: Write tests that can fail for one reason - choosing what to assert, when a fake beats a mock, how to reach a failure path, and why a test that has never failed proves nothing. Use when writing or reviewing tests, deciding what to mock, fixing a flaky test, or when the gate reports a test anti-pattern.
---

# Test design

A test is an experiment with one hypothesis. It earns its place by being **able to fail**,
failing for **one reason**, and naming that reason when it does.

**Which tests must exist is not a judgment call.** Every public name, every `raise`, and
every guard that produces one is a fact in the module's syntax tree, and
`scaffold_tests.py` reads them off it. Run that before writing tests - a list made by
reading the file is a plausible list that misses the branch added last week:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold_tests.py" <module> --write
python "${CLAUDE_PLUGIN_ROOT}/scripts/detect_gaps.py" <module>     # what is still owed
```

The AST supplies the obligations and a failing stub for each. It generates no assertions,
because a generated `assert result is not None` is a shallow test with a passing grade.
**What to assert is the judgment, and that is what follows.**

The mechanical half is also enforced: entries 27 to 36 of
[design-patterns/ANTI-PATTERNS.md](../design-patterns/ANTI-PATTERNS.md) are decided by
`detect_tests.py`, and the gate refuses a test that asserts nothing.

## Watch it fail first

Write the test, run it, read the failure, *then* write the code. A test that passed the
first time it ran has not been shown to test anything — it may be asserting something the
code did already, or nothing at all.

This is cheap and it is skipped constantly, including by this plugin's own first module,
where six tests failed together with one import error rather than individually for their own
reasons. That is a weaker red than it looks: it proved the module was missing, not that any
assertion was wired to any behaviour.

**The check:** can you say, for each test, what message you saw when it failed? If not, break
the implementation and watch it.

## Assert the thing that would be wrong

An assertion is load-bearing when a plausible bug would break it. `assert result is not None`
survives almost every bug a function can have.

```python
# good: a wrong currency, a wrong sum, or a wrong type all break this
assert running_balance(entries) == Money(400, "USD")

# bad: passes for Money(0, "EUR")
assert running_balance(entries) is not None

# bad: passes against a message that says anything containing a 1
assert "1" in str(caught.value)

# good: the exception carries the fact, and the test asserts the fact
assert caught.value.index == 1
```

When you find yourself matching a substring of an error message, that is the design telling
you the exception should carry a field.

## One behaviour, one test, one name

The name is what a failing CI run shows you. `test_rejects_zero_side` tells you what broke;
`test_square` does not.

```python
# good
def test_area_of_a_unit_square_is_one() -> None: ...
def test_zero_side_is_refused() -> None: ...


# bad: two behaviours, so a failure names neither
def test_validates_and_computes() -> None: ...
```

A test with four unrelated assertions is four tests sharing a name. Splitting costs nothing
and buys a failure message that locates the fault.

## Reach the failure paths

The contract's Tests section lists behaviours, and at least one must be a failure. Error
handling is the code least exercised in production and most likely to be wrong — a module
whose suite never raises has tested the half that already works.

```python
# the happy path is the easy half
def test_area_of_a_unit_square_is_one() -> None:
    assert Square(1.0).area_m2 == 1.0


# this is the half that finds bugs
def test_zero_side_is_refused() -> None:
    with pytest.raises(InvalidSideError):
        Square(0.0)
```

Boundaries deserve the same: empty input, one element, the value either side of a threshold.

## Prefer a fake to a mock

A **fake** is a working implementation with a shortcut — an in-memory store, a clock you
advance. A **mock** records calls and asserts about them.

Fakes test behaviour; mocks test implementation. A mock keeps passing after the real thing
breaks, and fails after a refactor that changed nothing observable.

```python
# good: a fake satisfies the seam, and the assertion is about an outcome
store = InMemoryStore()
run(store)
assert store.get("run-1").status == "complete"

# bad: asserts a call happened; passes if save() writes nothing
store = Mock()
run(store)
store.save.assert_called_once()
```

Writing the fake is also the second implementation that makes a `Protocol` legitimate — see
[design-patterns/INHERITANCE.md](../design-patterns/INHERITANCE.md). If a fake is hard to
write, the seam is in the wrong place.

## Test through the interface

Tests import a package's root modules, never its subfolders. A test that reaches into
`pkg.lib.nms` tests something no caller can reach and freezes a detail you wanted free to
change.

If a behaviour is only reachable by going around the interface, the module is the wrong
shape. Fix the shape; do not reach past it.

## Never sleep

`time.sleep` in a test buys a pass today and a flake next month, on someone else's machine.
Wait on the condition, or inject the clock so the test controls time rather than hoping.

## Completion criteria

- [ ] `scaffold_tests.py --list` was run, and every obligation it names has a test
- [ ] `detect_gaps.py` reports nothing blocking
- [ ] The sandbox was run, and its output holds no surprises
- [ ] Every behaviour in the contract's Tests section has a test
- [ ] At least one failure case and one boundary
- [ ] You watched each test fail, and know the message it gave
- [ ] Each test would break under a plausible bug
- [ ] Each test name says what broke
- [ ] No `sleep`, no deep imports, no assertions about calls
