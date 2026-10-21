---
description: Project a contract's Preconditions table into docstring conditions a tool can execute
argument-hint: "<module path>"
---

Write the executable half of `$1`'s contract into `$1` itself.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/conditions.py" $1            # print the projection
python "${CLAUDE_PLUGIN_ROOT}/scripts/conditions.py" $1 --write    # edit the module
python "${CLAUDE_PLUGIN_ROOT}/scripts/conditions.py" $1 --check    # fail if it has drifted
```

## Why a module needs this at all

A contract lives in `docs/contracts/*.md`, where nothing can run it. CrossHair reads
conditions out of a function's own docstring and reports this against a module whose claims
are all in markdown:

```
WARNING: Targets found, but contain no checkable functions.
```

Same facts, two places, and only one of them is checkable. This generates the second from
the first, so the contract stays the thing a person reads and the docstring becomes the
thing a tool runs.

## The verdict decides which condition is correct

This is the part worth knowing before using the command, because a naive projection emits
`pre:` for every row and that is worse than emitting nothing. CrossHair's `pre:` means
*assume this holds, do not explore outside it*.

| Verdict | Emits | Why |
| --- | --- | --- |
| `reject` | `raises: <Error>` | The function is total: outside the range it raises on purpose. A `pre:` here tells CrossHair to skip the exact inputs the guard exists for |
| `clamp` | nothing | Total, defined everywhere, raises nothing |
| `propagate` | `pre: <condition>` | The one case where a precondition is literally true: undefined outside the range, and the caller carries it |

## What it writes

```python
def intrinsics_from_fov(width: int, hfov_deg: float) -> Intrinsics:
    """Build a pinhole camera model from a field of view.

    A caller passes the sensor size it actually captured at.

    .. derived from docs/contracts/trackscope.data.md - regenerate, do not edit
    raises: InvalidFovError
    pre: width > 0
    .. end derived
    """
```

Everything outside the markers is yours and is never touched. Inside them, the next run
overwrites — the same discipline as the contract's own `<!-- derived -->` blocks.

## What it will not do

- **It does not write without `--write`.** Every other generator here creates a new file;
  this one edits a file you already own, so that stays an explicit choice.
- **It skips a function with no docstring.** This generates a contract's executable half,
  not a docstring nobody wrote.
- **It skips prose.** `open, not already consumed` is a legitimate precondition and not a
  Python expression; an unparseable `pre:` hands CrossHair a syntax error instead of a
  claim. Prose rows stay in the contract where a person reads them.
- **It cannot improve a claim, only reproduce one.** CrossHair found
  `intrinsics_from_fov(1, 1, 5e-324)` *inside* a hand-written `0 < hfov_deg < 180`. That is
  an insufficient guard, and no projection reaches it.

See `docs/proposals/001a-where-contracts-execute.md` for the decision and what was rejected.
