---
description: Reachability and duplication over a whole repository, with the lists, not just the numbers
argument-hint: "<repo root>"
---

Sweep `$1` and read the lists before saying anything about the numbers.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/sweep.py" $1           # human report
python "${CLAUDE_PLUGIN_ROOT}/scripts/sweep.py" $1 --json    # core / feature_local / dead / overlap / duplication_rate
```

## What the four sets mean

Entry points are found, not guessed: main guards, `[project.scripts]`, framework decorators
(`@app.route`, `@mcp.tool`, `@click.command`, ...), a module whose body builds the served
`app`, and the files a tool runs by convention (alembic migrations). Each entry's reach set
is walked over a function-level call graph that follows bare names, imported names,
constructors to `__init__`, callbacks handed around as values (`command=self._send`,
`{"process": jobs.process}`), and import-time module bodies.

| Set | Means |
| --- | --- |
| `core` | reached from every entry point |
| `feature_local[e]` | reached only from entry `e` |
| `shared` | reached from some entries, not all |
| `dead` | reached from no runtime entry and no test |

`duplication_rate` is the share of definitions in Type-1/2 clone groups: identical after
normalising names and literals, five or more statements. Type-3 (near-miss) clones are not
detected.

## Before a verdict

The numbers lie in known ways. Check each before repeating one:

- **A library has no in-repo callers.** Its public API reads as dead. `kind: library` in the
  report says the dead set is the API, not waste. CrossHair reads 25% dead for this reason.
- **Framework dispatch is invisible.** `HTMLParser.handle_data`, pydantic validators, dunders,
  `__post_init__` and Qt slots are called by code outside the repository. Read the dead list
  grouped by class before counting them.
- **Deliberate copies are not clones.** Dated snapshot directories, vendored skill scripts,
  kernel variants kept side by side, and a file whose header says *this is a copy and must
  stay one* are design decisions. Open the top clone groups and look.
- **Tests inflate duplication.** A suite that should be parametrised shows as 10x clones of a
  six-line test. Say so rather than attributing it to the production code.
- **Monorepos overlap at 1.00.** Workspace packages make every entry reach everything; the
  overlap table is an artifact there, not a finding.

Report what survived that reading, with the file and line for each item. A count with no
list behind it is not a finding.
