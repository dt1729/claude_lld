---
name: workflow
description: Where to start with lld-seed and what to do next - which command or skill comes after which, and what done means. Use when asked how to use lld-seed, where do I start, what next, how the commands fit together, how to adopt the plugin on an existing repository, how to sweep or diagnose a codebase, or when the contract gate has refused a write and the next step is unclear.
---

# Workflow

Two loops. Pick by what you are holding: code that does not exist yet, or code that does.

| You have | Start at |
| --- | --- |
| A module, class or public function to add | Loop 1, step 1 |
| A new file the gate refused | Loop 1, step 1, for that module |
| An edit to an existing file the gate refused | the rule number in the refusal: [rules.md](../../docs/reference/rules.md), then [troubleshooting.md](../../docs/reference/troubleshooting.md) |
| A repository you did not design | Loop 2 |
| A verified finding on someone else's repository | `/lld-seed:propose <owner/repo>` |

Terms are in [GLOSSARY.md](../../GLOSSARY.md). The long form, with each step's output:
[docs/guide/workflow.md](../../docs/guide/workflow.md).

## Loop 1: new code

Each step's output is the next step's input. Paths assume `src/<pkg>/<module>.py`; run every
command from the project root.

| # | Step | How | Produces |
| --- | --- | --- | --- |
| 1 | Contract | [codebase-design](../codebase-design/SKILL.md), then [new-module](../new-module/SKILL.md) step 2 | `docs/contracts/<pkg>.<module>.md` that validates |
| 2 | Interface | one write: every promised name, exact parameters, the guards each `reject` row demands; `...` bodies | a module rule 37 accepts |
| 3 | Scaffold tests | `/lld-seed:scaffold-tests <module>` | `tests/test_<module>.py` failing stubs, `tests/sandbox_<module>.py` |
| 4 | Implement behind the gate | run the sandbox, replace each `pytest.fail` with an assertion, write the bodies ([test-design](../test-design/SKILL.md)) | tests that each failed first, then pass |
| 5 | Conditions | `/lld-seed:conditions <module>`, then `--write` | `raises:` / `pre:` lines in docstrings |
| 6 | Derive | `/lld-seed:derive <module>` | `<!-- derived -->` blocks in the contract |
| 7 | Commit | [commits](../commits/SKILL.md) | contract, module and suite as one decision |

Three orderings that matter:

- **Interface before scaffold.** `scaffold_tests.py` reads the module's syntax tree and exits
  2 with no file on disk.
- **The first write keeps every promise.** Once the contract exists, rule 37 refuses a write
  that omits a promised name or changes a parameter list. A partial interface is refused.
- **Derive last.** Once the contract has derived blocks, rule 38 refuses any write that adds
  a public name, an import or a raise, and `derive` cannot fix that from inside the refused
  write. Changing the interface later: [troubleshooting.md](../../docs/reference/troubleshooting.md#rule-38-refuses-a-deliberate-interface-change).

The gate refuses a **new** `.py` under a `src/` segment until its contract validates, and
checks every write there, and to any test file, against the AST rules. A `judge` finding can
be waived in `docs/contracts/_waivers.md` with the row the refusal prints; a `block` finding
cannot. `python <plugin>/scripts/detect_gaps.py <module>` (rule 35) is not run by the gate;
run it after step 4.

### Done

- the contract validates, `**Status:** accepted` (validation accepts `draft`; this asks more)
- `detect_gaps.py <module>` reports nothing blocking
- `derive.py <module> --check` and `conditions.py <module> --check` exit 0
- ruff, `mypy --strict`, pytest and pre-commit are green
- every test was seen failing before it passed

## Loop 2: diagnose existing code

**Ships today.**

1. `/lld-seed:sweep <root>` - counts of `core`, `shared`, `dead`, feature-local per entry,
   overlap, top clone groups.
2. `sweep.py <root> --json` - the names behind `core`, `dead`, `feature_local`. The text
   report has counts only.
3. Confirm the entry points by hand: list every file a person runs directly. One with no
   `if __name__` guard is not found, and everything only it reaches reads as dead.
4. Read the dead list grouped by module and class; open the top clone groups.
5. Apply "Before a verdict" in [sweep.md](../../docs/reference/sweep.md#before-a-verdict).
   Report only what survived, each with a file and line. A helper under five statements is
   never a clone; grep for those.
6. Your repository: Loop 1 for each module you change. Someone else's: `/lld-seed:propose`.

**Planned, not built.** None of this exists in `scripts/`. Never describe it as a feature:

- concentration as the headline (module-size and fan-in inequality, directory tree against
  import graph) instead of dead% and duplication%;
- named findings checkable in two files, instead of percentages;
- withholding the dead figure until entry points are confirmed;
- plugin directories as declared boundaries, not dead code;
- "shape collision" for what is now called a clone, since identifiers are erased.

## Adopting on an existing repository

Existing modules need no contract to be edited, but every edit is checked against the whole
resulting file, so legacy code trips `block` rules on lines you did not touch. Loop 2 first.
Run `detect_patterns.py` over the files you will change. Write contracts only for modules
you are about to change, and use Loop 1 for everything new. `LLD_GATE=off claude` disables
the gate for a session, visibly; use it to finish a migration, not to avoid one.
