---
name: python-style
description: Judgment-level Python conventions that linters cannot check - naming for guarantees, one level of abstraction, module boundaries, dependency injection, docstring contracts. Use when writing or reviewing Python, naming a function or module, deciding what belongs in a docstring, or choosing how callers configure and extend code.
---

# Python Style

Four reference files, each holding rules a tool cannot decide. Read the one matching the
decision in front of you; do not read all four by default.

| Deciding | Read |
| --- | --- |
| What to call it, what the docstring owes the reader | [FORMAT.md](FORMAT.md) |
| Whether a function reads in one pass | [READABILITY.md](READABILITY.md) |
| Where a module ends and what it may import | [MODULARIZATION.md](MODULARIZATION.md) |
| How callers configure, substitute or extend | [CUSTOMIZABILITY.md](CUSTOMIZABILITY.md) |

Two neighbours own what this skill does not:

- Interface shape, seam placement, depth: [codebase-design](../codebase-design/SKILL.md).
- Which construct to use — inheritance, Protocol, factory, singleton — and the anti-pattern
  list the gate enforces: [design-patterns](../design-patterns/SKILL.md).
- What a module logs, at which level, and what it must never log: [logging](../logging/SKILL.md).

## What is enforced mechanically

These are configured once in `ruff.toml`, `mypy.ini` and `.importlinter`, and are deliberately
absent from the reference files. Do not restate them in any `CLAUDE.md`.

| Concern | Enforced by |
| --- | --- |
| Formatting, quotes, import order, line length | `ruff format`, `I` |
| Cyclomatic complexity, statements, branches, arguments | `C901`, `PLR0915`, `PLR0912`, `PLR0913` |
| Blind `except`, silent pass, raise-without-from | `BLE`, `TRY`, `B` |
| Boolean positional arguments | `FBT001`, `FBT002` |
| Mutable default arguments, loop-variable capture | `B006`, `B023` |
| Missing or imprecise annotations, `Any` leakage | `mypy --strict`, `ANN` |
| Import cycles, entry-point boundary violations | `import-linter` |
| Untested new modules, coverage floor | `pytest --cov`, contract hook |

A rule earns a place in prose only when no tool can decide it. When tooling catches up, move
the rule into the tool and delete the prose.
