<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/banner-light.png">
    <img src="docs/assets/banner-dark.png" alt="lld-seed: your coding agent designs before it writes, or it does not write" width="100%">
  </picture>
</p>

<p align="center">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-blue.svg">
  <img alt="Runtime dependencies: none" src="https://img.shields.io/badge/runtime%20deps-stdlib%20only-brightgreen.svg">
  <img alt="Tests: 356 passing" src="https://img.shields.io/badge/tests-356%20passing-brightgreen.svg">
  <img alt="Status: v0.7.0" src="https://img.shields.io/badge/status-v0.7.0-orange.svg">
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/demo.gif">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/demo-light.gif">
    <img src="docs/assets/demo.gif" alt="The gate refusing an undesigned write, then allowing one with a contract" width="100%">
  </picture>
</p>

A Claude Code plugin for Python repositories: it refuses a new module under `src/` until a
design contract for it validates, then checks every write against that contract and the
AST rules.

## Install

```
/plugin marketplace add dt1729/claude_lld
/plugin install lld-seed@dt1729
```

**Restart Claude Code after installing.** Hooks from a plugin installed mid-session do not
run until restart; until then nothing is gated. To check it is live, ask for
`src/<pkg>/anything.py` in a scratch repository: it should be refused with
`No contract for src/<pkg>/anything.py.`, and `.lld/gate.log` should gain a `deny` line.

### Requirements

| | |
| --- | --- |
| Python | 3.12+, reachable as `python` - the hook calls `python`, not `python3` |
| Claude Code | 2.1.268+ |
| **The `dataviz` skill** | **required** - ships with Claude Code |
| Runtime dependencies | none; the scripts use the standard library |

`dataviz` is not optional. Every diagram takes its palette, surfaces and type from that
skill, and `/lld-seed:diagram` exits 3 rather than draw colours nothing validated. See
`SCOPE.md`.

Optional: `ruff`, `mypy`, `import-linter`, `pytest` and `pre-commit` for the
[enforcement templates](docs/reference/enforcement.md); `git` and an authenticated `gh` for
`/lld-seed:propose`; CrossHair to run the conditions `/lld-seed:conditions` writes.

> **It will refuse writes.** That is the feature. `LLD_GATE=off claude` starts a session with
> the gate disabled; `.lld/gate.log` records every decision it makes. Add `.lld/` to
> `.gitignore`.

## Why

Coding agents default to code that exists and runs: no low-level design, no seams between
independent logic, no compartmentalisation. Flat functions, shallow tests and tangled imports
follow from that. This plugin supplies the missing step and refuses to let it be skipped.

## Workflow

Two loops. Step by step, with the output of each: [docs/guide/workflow.md](docs/guide/workflow.md).
First session, new or existing repository: [docs/guide/getting-started.md](docs/guide/getting-started.md).
The `workflow` skill gives the model the same map.

**Write loop - code that does not exist yet.** Ships complete.

```
contract ──▶ scaffold-tests ──▶ implement behind the gate ──▶ conditions ──▶ derive
```

1. **Contract.** `docs/contracts/<dotted.path>.md`. The gate refuses the module's file until
   it validates.
2. **Scaffold the tests.** Write the whole interface in one write first - rule 37 refuses
   one that leaves a promised name out - then `/lld-seed:scaffold-tests` reads its AST and
   writes one failing stub per obligation, plus a sandbox.
3. **Implement behind the gate.** Every write is checked against the structure, logging and
   test rules, and against the contract's interface.
4. **Conditions.** `/lld-seed:conditions` turns the Preconditions table into `raises:` /
   `pre:` lines in the docstrings.
5. **Derive, last.** `/lld-seed:derive` regenerates Interface, Dependencies and Errors from
   the AST. From then on rule 38 refuses a write that makes them stale.

**Diagnose loop - code that already exists.** `/lld-seed:sweep <root>`, then read the lists,
not the percentages. Two known errors: a script with no main guard is not an entry point, so
what only it reaches reads as dead; a helper under five statements is never reported as a
copy. Check both by hand before quoting a number. `/lld-seed:propose` sends one verified
finding to someone else's repository.

**Planned, not built.** A sweep headline about concentration - module-size inequality,
fan-in inequality, directory tree against import graph - instead of dead% and duplication%,
and no dead figure until the entry points are confirmed. Nothing in `scripts/` does this yet.

## Features

| Feature | What it is | Prevents | Reference |
| --- | --- | --- | --- |
| Gate | `PreToolUse` hook on `Write\|Edit\|MultiEdit`, deciding from the file the call would produce | a new module nobody designed; a `block` finding landing because nobody looked | [gate.md](docs/reference/gate.md) |
| Rules | numbered rules 1-39, `block` or `judge`, decided from the AST; a `judge` finding clears with a waiver row, a `block` finding never does | singletons, import-time side effects, `print` in a package, eager log formatting, a test that cannot fail | [rules.md](docs/reference/rules.md) |
| Contracts | one Markdown file per module: Responsibility, Interface, Preconditions, Seam, Dependencies, Errors, Tests, Deletion test | a parameter nobody decided the limits of; a hand-typed `Imported by` that outlives its code | [contracts.md](docs/reference/contracts.md) |
| Commands | `scaffold-tests`, `conditions`, `derive`, `diagram`, `scaffold-guidance`, `sweep`, `propose` | a test list made from memory; a precondition only Markdown holds; a diagram with an unvalidated palette | [commands.md](docs/reference/commands.md) |
| Skills | `workflow`, `codebase-design`, `new-module`, `python-style`, `design-patterns`, `logging`, `test-design`, `commits` | prose restating ruff; a pattern chosen by fashion; steps run out of order | [skills.md](docs/reference/skills.md) |
| Sweep | entry points, reach sets (`core`, `feature_local`, `shared`, `dead`), entry overlap, Type-1/2 clones over a whole repository | a verdict on a repository from a number with no list behind it | [sweep.md](docs/reference/sweep.md) |
| Detectors | `detect_patterns`, `detect_tests`, `detect_gaps`, `conformance`, `obligations`; the CLIs run without Claude Code | a rule enforced only inside a session; a public name or raise no test covers | [detectors.md](docs/reference/detectors.md) |
| Enforcement | `ruff.toml`, `mypy.ini`, `.pre-commit-config.yaml` and an `.importlinter` template | prose restating what a tool can decide | [enforcement.md](docs/reference/enforcement.md) |
| Troubleshooting | one section per refusal whose cause is not obvious | `LLD_GATE=off` used to dodge a rule rather than finish a migration | [troubleshooting.md](docs/guide/troubleshooting.md) |

Anything a tool can check is enforced by the tool and named, not restated, in the prose.
See `SCOPE.md` for the division of labour and `GLOSSARY.md` for the vocabulary.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/flow.gif">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/flow-light.gif">
    <img src="docs/assets/flow.gif" alt="A write travels through the gate to disk, the checks and a commit; every refusal arcs back to the author, and a judged finding becomes a recorded incident that edits the rules" width="100%">
  </picture>
</p>

## Status

v0.7.0 - see [CHANGELOG.md](CHANGELOG.md).

- 356 tests passing, 1 skipped (the `dataviz` check, where the skill is absent); `ruff`,
  `mypy --strict` and `claude plugin validate .` green.
- Calibrated against a repository it did not write (`docs/incidents.md`, incident 001); the
  sweep measured against 125 Claude-authored repositories (CHANGELOG, 0.7.0).
- One module built end to end through the flow, then reviewed against every rule:
  `docs/phase-4-review.md`. It passes every gate and has six semantic defects, which is the
  honest measure of what this does and does not buy.

## Unverified

The `PreToolUse` hook has been exercised with real payloads through the exact command string
the manifest declares, but has **never been observed intercepting a write inside a live
session**. Until it has, the gate's effect on a real session is a claim, not a result.

## Credits

The deep-module vocabulary, the design-it-twice procedure and the entry-point boundary rule
are adapted from [mattpocock/skills](https://github.com/mattpocock/skills), which applies
them to TypeScript. Divergences are recorded in `GLOSSARY.md`.

The demo pipeline — author each frame as HTML, screenshot it with headless Chrome, assemble
with Pillow, transcode with ffmpeg — is taken from
[Parth1811/JevFlow](https://github.com/Parth1811/JevFlow). Keeping the design in CSS rather
than in drawing coordinates is their idea, and it is a better one than the approach it
replaced here.

MIT licensed.
