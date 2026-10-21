# Scope

## The problem

Coding agents default to code that merely exists and runs: no low-level design, no seams
between independent logic, no compartmentalisation. Flat procedural functions, shallow tests
and tangled imports are symptoms. The missing design step is the cause.

## What this plugin does

1. **Supplies a design vocabulary** so "make it modular" becomes a checkable instruction,
   covering logging as a first-class concern rather than an afterthought.
2. **Gates implementation on a written contract** via a blocking `PreToolUse` hook.
3. **Installs real enforcement** (ruff, mypy, import-linter, pytest, pre-commit) so the prose
   never repeats what a tool can check.
4. **Writes folder guidance where an agent needs orienting** - not everywhere. A module's
   contract is checked against its code; a folder file is not, so one that repeats a
   contract is an unchecked second copy. See incident 008.

## Prerequisite: the `dataviz` skill

**`lld-seed` requires the `dataviz` skill that Claude Code ships. Without it the plugin does
not work.** It is a dependency in the same sense as Python 3.12, not a suggestion.

This plugin designs nothing of its own. Every figure it draws takes its palette, its
surfaces and its type from `dataviz`, and three rules follow from that:

- **No colour is chosen in this repo.** `scripts/diagrams.py` declares roles - page plane,
  chart surface, primary and secondary ink, muted, baseline, categorical slot 1, status
  critical - and every value comes from `dataviz/references/palette.md`. A literal hex that
  is not a role from that file fails `scripts/tests/test_palette.py`.
- **No palette ships unvalidated.** `dataviz/scripts/validate_palette.py` decides whether a
  palette is safe. Nobody here reasons about delta E and nobody eyeballs it.
- **The diagram commands refuse to run without it.** `/lld-seed:diagram` fails with the
  install instruction rather than draw a figure whose colours nothing checked.

Colour in these diagrams carries meaning: blue is a type, red is an error. That makes the
palette an accessibility decision, and this plugin's first rule is that a decision a tool can
make is never made by hand. The one time it was made by hand here, red and green sat 1.3
apart under simulated deuteranopia - one colour, to the readers the distinction was for.
See incident 010.

## Division of labour

| Concern | Owner |
| --- | --- |
| Formatting, import order, line length | ruff format |
| Complexity, statement/branch/argument counts, blind excepts | ruff lint |
| Type correctness, exhaustiveness, optionality | mypy --strict |
| Import direction, cycles, entry-point boundary | import-linter |
| Test existence and coverage | pytest + hook |
| `print` in a package, eager log formatting, swallowed exceptions | ruff + the gate |
| Which level an event deserves, what a line must carry, what is never logged | **the markdown** |
| Where a seam goes, what an abstraction is for, when to split | **the markdown** |
| Diagram palette, surfaces, type, contrast, colourblind separation | **the `dataviz` skill** |

A rule belongs in markdown only if no tool can decide it. Every rule a tool owns is listed
once, in the tool's config, and referenced from the prose by name.

## Non-goals

- Replacing a linter with prose.
- Designing a visual language. `dataviz` owns colour and type; this plugin owns only what
  the syntax tree says.
- Teaching Python syntax, or anything the model already does by default.
- Supporting languages other than Python in v0.x. The vocabulary is language-neutral; the
  enforcement is not.

Rejected ideas live in `.out-of-scope/` with the reasoning, so they are not re-litigated.
