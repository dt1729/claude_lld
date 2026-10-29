# Skills

Skills are how guidance reaches the model: Claude Code loads one when its `description`
matches the task. They are not invoked by name, though you can ask for one ("use the
codebase-design skill"). Each `SKILL.md` is short and routes to reference files loaded on
demand. Plugin skills are discovered from `skills/<name>/SKILL.md`; nothing registers them.

A rule a tool can enforce is configured in the tool and named in the skill, never restated.

| Skill | Loads when | Gives you | Prevents |
| --- | --- | --- | --- |
| [workflow](../../skills/workflow/SKILL.md) | asking how to use lld-seed, where to start, what next | the two loops, which command when, what done means | running the steps out of order, or claiming a diagnose feature that does not exist |
| [codebase-design](../../skills/codebase-design/SKILL.md) | creating or restructuring a module; asked for LLD or boundaries | deep modules, the deletion test, seam placement, entry-point boundary | a four-step interface sold as modularity |
| [new-module](../../skills/new-module/SKILL.md) | adding a module, class or public function; the gate blocked a write | place, contract, tests from the AST, implement, guidance | implementation before design |
| [python-style](../../skills/python-style/SKILL.md) | writing or reviewing Python, naming, docstrings | four judgment-only reference files and the map of what tools own | prose rules duplicating ruff and mypy |
| [design-patterns](../../skills/design-patterns/SKILL.md) | introducing a class, base class, factory, singleton | a verdict per reader perspective, and the anti-pattern list the gate enforces | a pattern chosen by fashion |
| [logging](../../skills/logging/SKILL.md) | adding a log line, choosing a level, handling an exception | levels by who must act; library emits, application configures | ERROR that fires nightly; a library that configures logging |
| [test-design](../../skills/test-design/SKILL.md) | writing or reviewing tests; the gate reported a test rule | what to assert, fakes over mocks, watch it fail first | a test that cannot fail |
| [commits](../../skills/commits/SKILL.md) | committing, writing a message, splitting work | one reason per commit; the body says why and what was rejected | a history that records what changed and never why |

## Reference files

| Skill | File | For |
| --- | --- | --- |
| codebase-design | `DESIGN-IT-TWICE.md` | comparing radically different interfaces before choosing |
| codebase-design | `DEEPENING.md` | deepening a cluster of shallow modules without breaking callers |
| new-module | `CONTRACT-FORMAT.md` | the contract template, worked example, and section guide |
| python-style | `FORMAT.md` | naming for guarantees, what a docstring owes |
| python-style | `READABILITY.md` | one level of abstraction, reading in one pass |
| python-style | `MODULARIZATION.md` | where a module ends, what it may import |
| python-style | `CUSTOMIZABILITY.md` | how callers configure, substitute, extend |
| design-patterns | `PERSPECTIVES.md` | the five readers: library user, library builder, operator, developer, end user |
| design-patterns | `CATALOGUE.md` | a verdict per perspective for each construct |
| design-patterns | `INHERITANCE.md` | inheritance versus composition, Protocol versus ABC |
| design-patterns | `ANTI-PATTERNS.md` | every numbered rule, its detection and its fix |
| logging | `LEVELS.md` | the level decision procedure, with worked cases |

## Vocabulary

[GLOSSARY.md](../../GLOSSARY.md) defines module, interface, implementation, depth, seam,
adapter, leverage, locality, entry point, contract and the logging terms. Every skill uses
them exactly; "component", "service", "layer", "API" and "boundary" are avoided.
