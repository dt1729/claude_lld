# claude_lld

A Claude Code plugin (`lld-seed`) that makes coding agents design before they implement.

Agents default to code that exists and runs: no low-level design, no seams between
independent logic, no compartmentalisation. Flat functions, shallow tests and tangled imports
follow from that. This plugin supplies the missing step and refuses to let it be skipped.

## How it works

| Layer | Mechanism |
| --- | --- |
| Vocabulary | `GLOSSARY.md` — module, interface, depth, seam, adapter |
| Design | `codebase-design` skill — deep modules, the deletion test, design it twice |
| Conventions | `python-style` skill — four reference files of judgment-only rules |
| Gate | `PreToolUse` hook — no implementation in `src/` without a contract |
| Enforcement | ruff, mypy `--strict`, import-linter, pytest, pre-commit |
| Per-folder guidance | `/lld-seed:scaffold-guidance` — recursive, idempotent `CLAUDE.md` |

Anything a tool can check is enforced by the tool and named, not restated, in the prose.
See `SCOPE.md` for the division of labour.

## Install

```bash
/plugin marketplace add dt1729/claude_lld
/plugin install lld-seed@dt1729
```

Then, in the repo you want governed:

```
/lld-seed:scaffold-guidance
```

## Status

v0.1.0, in development. Phases 3 (generator and hooks) and 4 (validation and pre-commit)
are not yet built.

## Credits

The deep-module vocabulary, the design-it-twice procedure and the entry-point boundary rule
are adapted from [mattpocock/skills](https://github.com/mattpocock/skills), which applies
them to TypeScript. Divergences are recorded in `GLOSSARY.md`.

MIT licensed.
