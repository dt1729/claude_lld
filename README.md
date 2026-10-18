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
| Observability | `logging` skill — levels by who must act, library-versus-application split |
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

v0.1.0. Built and validated against real code.

- 137 tests, `ruff` + `mypy --strict` + `pre-commit` green, plugin validates.
- Calibrated against a repository it did not write (`docs/incidents.md`, incident 001).
- One module built end to end through the flow, then reviewed against every rule:
  `docs/phase-4-review.md`. It passes every gate and has six semantic defects, which is the
  honest measure of what this does and does not buy.

**Unverified:** the `PreToolUse` hook has been exercised with real payloads through the
exact command string the manifest declares, but never observed intercepting a write inside a
live session — a plugin installed mid-session does not activate its hooks until restart.

## Credits

The deep-module vocabulary, the design-it-twice procedure and the entry-point boundary rule
are adapted from [mattpocock/skills](https://github.com/mattpocock/skills), which applies
them to TypeScript. Divergences are recorded in `GLOSSARY.md`.

MIT licensed.
