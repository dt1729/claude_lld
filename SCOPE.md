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
4. **Generates per-folder guidance** recursively, so each package carries only its own
   purpose, interface, allowed dependencies and invariants.

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

A rule belongs in markdown only if no tool can decide it. Every rule a tool owns is listed
once, in the tool's config, and referenced from the prose by name.

## Non-goals

- Replacing a linter with prose.
- Teaching Python syntax, or anything the model already does by default.
- Supporting languages other than Python in v0.x. The vocabulary is language-neutral; the
  enforcement is not.

Rejected ideas live in `.out-of-scope/` with the reasoning, so they are not re-litigated.
