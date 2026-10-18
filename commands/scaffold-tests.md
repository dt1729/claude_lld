---
description: Derive test obligations from a module's AST, then scaffold the suite and sandbox
argument-hint: "<module path>"
---

Scaffold the tests and sandbox for `$1` **from its abstract syntax tree**, not from reading
the file and deciding what looks important.

## Why the AST and not your reading

A module's public surface, the exceptions it raises, and the guards that raise them are
facts in the syntax tree. Reading the file and listing what seems worth testing produces a
plausible list that silently misses the branch added last week. The AST does not miss it,
does not get bored, and gives the same answer twice.

So: run the tool, then exercise judgment on what it returns. Do not substitute your reading
for the first step.

## 1. Read the obligations

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold_tests.py" $1 --list
```

Each line is a fact in the source that the suite owes a test:

| Kind | Comes from | Means |
| --- | --- | --- |
| `public-name` | a top-level `def`/`class` without a leading underscore, and the public methods of a public class | a caller can reach it, so a test must |
| `raise` | a `raise X(...)` anywhere in the module | the failure path is real and nothing proves it works |
| `boundary` | the comparison in an `if` that guards a raise | the threshold, where off-by-one lives |

If the list surprises you, that is the point: it is what the code says, and your reading was
what you remembered.

## 2. Generate the skeleton and the sandbox

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold_tests.py" $1 --write
```

Writes two files next to the module, and **never overwrites** an existing one:

- `tests/test_<module>.py` — one stub per obligation, each failing with
  `pytest.fail("not written yet")` and carrying the fact that demands it. Red by
  construction, so no stub can pass unwritten.
- `tests/sandbox_<module>.py` — imports the module in a fresh process under a temporary
  working directory and builds each public type with values either side of its guards. It
  reports; it asserts nothing.

## 3. Run the sandbox before writing a single assertion

```
python <package>/tests/sandbox_<module>.py
```

It answers what no unit test in an already-warm process can: whether importing does work,
whether a constructor reaches outside, how long either takes, and what each construction
actually returns or raises. Read that output — it is the module's real behaviour, and it
frequently disagrees with the docstring.

A slow import or a file written during construction is a finding. Record it.

## 4. Replace each stub's failure with an assertion

This is the judgment the tool does not have. For each stub:

- Assert what a **plausible bug would break**. `assert result is not None` survives almost
  every bug a function can have.
- For a `raise` obligation, expect the type *and* the fact — if you reach for a substring of
  the message, the exception should carry a field instead.
- For a `boundary` obligation, test the value **at** the threshold and the one either side.
  The sandbox output already shows you what each does.
- Rename the stub so the name says what broke: `test_zero_side_is_refused`, not
  `test_square_behaves_as_documented`.

Keep every stub or delete it deliberately. A stub left failing is honest; a stub deleted
because it was inconvenient is the gap this command exists to close.

## 5. Confirm nothing is still owed

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/detect_gaps.py" $1
```

Blocking findings are obligations with nothing in the suite that covers them. Judgment
findings are boundaries, where the AST can see the threshold but not which value a test
passed — confirm those yourself.

Then run the suite and the usual gates. Coverage answers a different question than this
does — whether a line executed, rather than whether anyone thought about it — so run
`pytest --cov --cov-branch` as well. Neither replaces the other.
