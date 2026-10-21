---
description: Draw inheritance, dependency, control-flow and error diagrams from the AST
argument-hint: "<package path>"
---

Draw four views of `$1` from its syntax tree, as SVG beside the contracts.

**Requires the `dataviz` skill.** Load it before drawing. Every colour in the output is a
role from `dataviz/references/palette.md` and none is chosen here; the script exits non-zero
with the install instruction if the skill is absent, because a figure whose palette nothing
validated is the thing this plugin exists to refuse.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/diagrams.py" $1 --out docs/diagrams
python "${CLAUDE_PLUGIN_ROOT}/scripts/diagrams.py" $1 --check   # fail if stale
```

| Diagram | What it shows | What it makes visible |
| --- | --- | --- |
| `inheritance` | each class and the base it names | a base of a base, which the depth rule forbids |
| `dependencies` | each module and a module it imports | a cycle, or an arrow into a private subpackage |
| `flow-<module>` | each public name and the errors it raises | a public name that raises nothing, or everything |
| `errors` | each module that raises or catches a type | an error nobody catches, or one caught everywhere |

## The language of the labels

Every arrow carries **one** verb from a closed list - `raises`, `imports`, `is`, `catches`,
`calls` - and every caption stays inside a checkable subset of ASD-STE100: short active
sentences, one idea each, no gerund used as a noun, approved words only. Identifiers pass
through unchanged, because a reader must be able to grep for what they see.

The point is that two diagrams of different packages read the same way. A reader learns the
vocabulary once. `scripts/ste.py` enforces it and the command fails rather than drawing a
label nobody can rely on - which it did to its own captions the first time it ran.

**What it is not:** the official ASD-STE100 dictionary is a published specification and is
not bundled. This is a conforming subset - a small approved vocabulary plus the structural
rules a parser can check. The module says so on its own face.

## What the diagrams cannot show

`errors` matches exception types by name, not by resolved symbol, so two types sharing a
name look like one. `dependencies` sees literal imports only. Each caption states its own
limit, because a figure that silently under-reports is the same lie in a smaller font.
