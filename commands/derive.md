---
description: Regenerate the factual half of a contract from the module's AST
argument-hint: "<module path> [--check]"
---

Regenerate the derived blocks in the contract for `$1`, from the module's syntax tree.

## What is derived and what is yours

A contract has two kinds of sentence, and only one of them can be generated.

| Derived — inside `<!-- derived -->`, never hand-edited | Declared — yours, never touched |
| --- | --- |
| `Interface`: public signatures | `Responsibility` |
| `Dependencies`: real imports out, real importers in | `Seam`, and what you rejected |
| `Errors`: the exception types raised | what each error **means to a caller** |
| | `Observability`, `Tests`, `Deletion test` |

The split is by who can know the sentence. A parser knows that `InvalidSideError` is raised;
only you know that a caller should prompt the operator rather than retry. So the derived
block lists the types and your prose beneath it says what they mean.

## Run it

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/derive.py" $1           # rewrite the blocks
python "${CLAUDE_PLUGIN_ROOT}/scripts/derive.py" $1 --check   # fail if they are stale
```

`--check` is what the gate and pre-commit run. A stale block means the code moved and the
contract has not caught up — which is why the fix is a command rather than a judgment call.

## Why this exists

Contract drift was the single defect an external audit found in every dimension it examined:
ten contracts with a wrong `Imported by` line, five asserting an edge another contract
forbids, interfaces describing code that was not there. Every one of those lines was typed by
hand and then outlived its code.

Generating them removes the failure rather than detecting it. The same reasoning as a
formatter: nobody writes a lint rule for indentation, because the tool makes it true and
`--check` fails the build when it is not.

## What it cannot see

The syntax tree reads what is written literally. A dynamic import, a re-export, a `raise`
inside a helper this module calls — none of them appear. Every generated block says so on its
own face, because a block that silently under-reports is the same lie in a smaller font.

When you know of a fact the parser cannot reach, write it in your prose beneath the block.
That is exactly the kind of sentence the declared half is for.
