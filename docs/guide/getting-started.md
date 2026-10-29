# Getting started

## Requirements

| | |
| --- | --- |
| Python | 3.12+, reachable as `python`. The hook runs `python`, not `python3` |
| Claude Code | 2.1.268+ |
| The `dataviz` skill | required; ships with Claude Code. `/lld-seed:diagram` exits 3 without it rather than draw in colours nothing validated |
| Runtime dependencies | none; every script uses the standard library |

Optional: `pre-commit`, `ruff`, `mypy`, `import-linter` and `pytest` for the
[enforcement templates](../reference/enforcement.md); `git` and an authenticated `gh` for
`/lld-seed:propose`; CrossHair to execute the conditions `/lld-seed:conditions` writes.

## Install

Inside a session:

```
/plugin marketplace add dt1729/claude_lld
/plugin install lld-seed@dt1729
```

Or from a shell:

```
claude plugin marketplace add dt1729/claude_lld
claude plugin install lld-seed@dt1729
```

**Restart Claude Code.** Hooks from a plugin installed mid-session do not run in that
session. Until the restart the skills and commands work and nothing is gated.

### Check the gate is live

In a scratch repository, ask the agent to create `src/demo/anything.py`. It should be refused
with:

```
No contract for src/demo/anything.py.
```

and `.lld/gate.log` should gain a `deny` line. If the write goes through and the log has no
line for it, the hook is not running: the session predates the install, or `python` does not
resolve to 3.12+. A hook command that fails does not block the write, so a broken gate looks
the same as an absent one.

## What the gate refuses

Full table in [gate.md](../reference/gate.md#what-it-decides). In short:

| Write | Refused when |
| --- | --- |
| A **new** `.py` under a path with a `src` segment | `docs/contracts/<dotted.path>.md` is missing or does not validate |
| Any `.py` under `src`, new or existing | a `block` finding from rules 1-10, 12-15, 19-24, or from 37/38 when a contract exists; or a `judge` finding with no waiver |
| A test file anywhere (`test_*.py`, `*_test.py`, or a `tests/` segment) | a `block` finding from test rules 27-33, 36 |
| Everything else | never |

Not gated even under `src/`: `__init__.py`, `conftest.py`, `setup.py`, and any path with a
`tests`, `test`, `scripts`, `migrations`, `_generated` or `generated` segment. The hook's
`src` root is fixed; the CLI scripts take `--src-root`, the hook does not.

The whole resulting file is checked, not the diff. A one-line edit to a legacy module is
refused for a `block` finding fifty lines away.

### Reading a refusal

The reason the model sees names the line, the rule number and what to do:

```
These anti-patterns are decided by the AST and cannot be waived:
  line 24: [19] print - print in a package module: use logging.getLogger(__name__) and a level chosen by who must act
```

Look the number up in [rules.md](../reference/rules.md). A `block` finding is cleared only by
changing the code, or the contract. A `judge` finding prints the row to append to
`docs/contracts/_waivers.md`; add it with a reason you would defend and repeat the write.

`.lld/gate.log` under the project root holds one line per decision:

```
06:10:12 INFO    lld.gate checking Write src/shapes/circle.py (new module)
06:10:12 INFO    lld.gate deny src/shapes/circle.py: new module, contract missing (1 ms)
```

A `deny` line lists the rules that fired. `LLD_LOG_LEVEL=DEBUG` adds the inputs behind each
decision; `LLD_LOG_FILE` moves the log. Add `.lld/` to `.gitignore`.

### Turning it off

`LLD_GATE=off claude` starts a session in which the hook allows every write without looking
at it. It is read from the environment Claude Code started with, so exporting it mid-session
does nothing. Nothing reaches `.lld/gate.log` while it is off. Use it to land a migration,
not to skip one.

Stuck on a specific refusal: [troubleshooting.md](../reference/troubleshooting.md).

## First 15 minutes: a new repository

1. **Lay out packages under `src/`.** The gate governs only paths with a `src` segment. A
   package at the repository root or in `scripts/` is never gated.
2. **Add `.lld/` to `.gitignore`.**
3. **Optionally copy the [enforcement templates](../reference/enforcement.md)** and make the
   edits that page lists. They rerun the structure detector and add rule 35
   (`detect_gaps.py`) at commit time. Neither they nor the gate run `derive.py --check` or
   `conditions.py --check`; put those in CI.
4. **Ask for the first module.** The gate refuses the file. That refusal is step 1 of the
   [write loop](workflow.md#loop-1-writing-new-code): write the contract in
   `docs/contracts/`, then the interface, then `/lld-seed:scaffold-tests`.

Nothing has to be generated first. Folder `CLAUDE.md` files are optional and usually
unnecessary for a library: [scaffold-guidance](../reference/commands.md#scaffold-guidance).

## First 15 minutes: a repository that already exists

The gate is live from the restart, and every edit under `src/` is checked against the whole
file. Look before the first edit.

1. **Sweep it.** `/lld-seed:sweep .` Read the lists, not the percentages. The dead figure is
   wrong until you have confirmed the entry points by hand; see
   [the diagnose loop](workflow.md#loop-2-diagnosing-existing-code).
2. **Run the detectors over what you will touch first.**
   `python <plugin>/scripts/detect_patterns.py src/<pkg>/<module>.py` prints the findings
   the gate will refuse that file for. A module with a `block` finding cannot be edited
   through the gate, on any line, until that finding is fixed.
3. **Write contracts for the modules you are about to change**, not for all of them. An
   existing module without a contract can still be edited; only a new file needs one. A
   contract switches on rule 37 for its module, so its Interface block must match the code
   from the first write after.
4. **New code follows the write loop** from the first file.

**No `src/`?** Only test files are gated. The sweep and the detectors work on any layout;
run them by hand. Both repositories in the
[worked example](workflow.md#worked-example-two-sweeps-on-2026-10-24) keep their code in
`scripts/`, and the gate never fired on that code.

## Where next

- [workflow.md](workflow.md) - both loops, step by step, with what each step produces
- [gate.md](../reference/gate.md), [rules.md](../reference/rules.md),
  [contracts.md](../reference/contracts.md) - what the gate checks
- [commands.md](../reference/commands.md), [skills.md](../reference/skills.md) - everything
  the plugin ships
- [troubleshooting.md](../reference/troubleshooting.md) - the gate refused something and the
  reason is not obvious
