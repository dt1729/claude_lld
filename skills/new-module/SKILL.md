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

Choose constructs here, not while typing the implementation:
[design-patterns](../design-patterns/SKILL.md) gives the verdict per perspective, and
[ANTI-PATTERNS.md](../design-patterns/ANTI-PATTERNS.md) lists what the gate will reject.

## 3. Write the test list, then the tests

The contract's Tests section is a list of behaviours **through the interface**. Turn each
into a test before the implementation exists. They fail; that is the point — a test that has
never failed has not been shown to test anything.

Include at least one failure case and one boundary. A test list of only happy paths is the
shallow-test failure mode, and it is visible at this step rather than three weeks later.

Tests live in `<package>/tests/test_<module>.py` and import the module through its public
path, never by reaching into a subfolder.

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
