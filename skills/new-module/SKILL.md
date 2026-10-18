---
name: new-module
description: Scaffold a new Python module the designed way - write the contract first, then the test list, then the implementation, then its folder guidance. Use when adding a module, package, class or public function, when the contract gate blocks a write, or when asked to create something new in a Python repo.
---

# New module

Five steps, in order. The order is the point: each step constrains the next, and skipping one
produces the failure this plugin exists to prevent — code that runs and was never designed.

## 1. Place it

Decide the path before anything else, because it fixes the module's visibility.

- A package root module (`detection/pipeline.py`) is **public**: other packages may import it,
  so its interface is a promise.
- A subfolder module (`detection/lib/nms.py`) is **private**: only its own package may import
  it, and it can be changed freely.

Default to private. Promote to a root module when a second package genuinely needs it. See
[python-style/MODULARIZATION.md](../python-style/MODULARIZATION.md).

## 2. Write the contract

Create `docs/contracts/<dotted.path>.md` from
[CONTRACT-FORMAT.md](CONTRACT-FORMAT.md) and fill every section. Three of them do the real
work:

- **Responsibility** — one sentence. If it needs "and", stop and split into two modules.
  This is the cheapest moment to notice.
- **Seam** — what varies, and what you rejected. Reach for
  [codebase-design/DESIGN-IT-TWICE.md](../codebase-design/DESIGN-IT-TWICE.md) when the module
  is a package entry point or more than one caller already exists.
- **Deletion test** — what reappears in callers if this module vanishes. If the answer is
  "nothing", do not create it.
- **Observability** — what this module logs, at which level, and what it must never log.
  The operator is a caller and a log line is a promise, so it is designed here rather than
  sprinkled in later. `No logging.` is a legitimate answer; silence by accident is not.
  See [logging/LEVELS.md](../logging/SKILL.md).

Choose constructs here, not while typing the implementation:
[design-patterns](../design-patterns/SKILL.md) gives the verdict per perspective, and
[ANTI-PATTERNS.md](../design-patterns/ANTI-PATTERNS.md) lists what the gate will reject.

## 3. Derive the tests from the AST, then write them

The contract's Tests section says what you *intended*. The source says what is *true*. Use
both, in that order, and never let the first stand in for the second.

**Run the tool. Do not substitute your reading of the file.**

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold_tests.py" <module> --list   # obligations
python "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold_tests.py" <module> --write  # stubs + sandbox
```

Every public name, every `raise`, and every guard that produces one is an obligation read
off the syntax tree. Listing what looks important instead produces a plausible set that
misses the branch added last week; the AST does not miss it and gives the same answer twice.

This writes two files and never overwrites an existing one:

- `tests/test_<module>.py` — one stub per obligation, each failing with `pytest.fail` and
  carrying the fact that demands it. Red by construction: a stub cannot pass unwritten.
- `tests/sandbox_<module>.py` — imports the module in a fresh process under a temporary
  directory and builds each public type with values either side of its guards. **Run it
  before writing any assertion.** It shows what the module does alone, which no test in a
  warm process can: import-time work, a constructor that writes a file, what each call
  actually returns or raises.

Then replace each stub's failure with an assertion a plausible bug would break, and rename
it for the behaviour it covers. That judgment is yours; the tool has none, which is why it
generates no assertions. See [test-design](../test-design/SKILL.md).

Finally, confirm nothing is still owed:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/detect_gaps.py" <module>
```

Tests live in `<package>/tests/test_<module>.py` and import the module through its public
path, never by reaching into a subfolder. The gate refuses a test that asserts nothing.

## 4. Implement

Write the body against the contract. If implementation reveals the interface is wrong — and
it sometimes does — **edit the contract first**, then continue. Do not let the code and the
contract diverge silently; the whole value is that the document stays true.

Run `ruff`, `mypy --strict` and `pytest` before considering it done. Fix the code, not the
configuration.

## 5. Record the local guidance

Run `/lld-seed:scaffold-guidance <package-path>` to create or refresh that folder's
`CLAUDE.md`: purpose, public interface, allowed dependencies, local invariants. It carries
only what is local; the rules stay in the plugin.

## Completion criteria

The module is done when all of these hold. Report which, if any, do not.

- [ ] Contract exists, every required section filled, `Status: accepted`
- [ ] Every behaviour in the Tests section has a test, and each failed before it passed
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` all green
- [ ] No entry in [ANTI-PATTERNS.md](../design-patterns/ANTI-PATTERNS.md) is present, or a
      recorded judgment explains why the exception holds
- [ ] The folder `CLAUDE.md` names this module in its public interface, if it is public

## When the gate blocks you

The hook refuses a write and prints the signals it found. That is not an obstacle to route
around: it means step 2 has not happened yet. Write the contract, then repeat the write.

If the change genuinely does not warrant a contract — a typo, a docstring fix, a rename with
no interface change — record that judgment with its reason when the hook asks. The judgment
is logged and reviewable, so make it one you would defend.
