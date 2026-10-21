# Decision: where a contract lives, and what the module carries

**Answers:** proposal 001, Appendix B · issue #5
**Date:** 2026-10-21
**Status:** decided

---

## The observation

> lld-seed writes contracts to `docs/contracts/*.md`, where nothing can execute them.
> CrossHair needs the same facts in the function. Same information, two places, and only
> one of them is checkable.

CrossHair, run against the functions as they were:

```
WARNING: Targets found, but contain no checkable functions.
```

The same claims moved into the docstring:

```
error: ZeroDivisionError: when calling intrinsics_from_fov(1, 1, 5e-324)
```

## The decision

**The contract stays authoritative in markdown. The module carries a generated projection of
the part a tool can execute.**

Three things follow, and the third is the one worth reading.

### 1. Not icontract

`@require(lambda hfov_deg: 0 < hfov_deg < 180)` is executable, checkable and wrong for this
plugin. It puts a runtime dependency inside the **shipped package**, not the development
environment. ruff, mypy, import-linter, pre-commit and Semgrep are all dev-time: a consumer
of a seeded library installs none of them. icontract would be the first tool lld-seed asks a
user's *users* to install, and it adds a per-call cost to every guarded function.

Docstring conditions are inert text to Python. Zero runtime cost, zero dependency, and
CrossHair reads them.

### 2. Not "move the contract into the code"

The contract holds things no parser wants and no function body should carry: what the seam
is for, what was rejected and why, the deletion test. Appendix B is not an argument for
deleting the markdown - it is an argument that the *executable half* currently exists only
where nothing can run it.

This is the same split the derived blocks already make. A hand-written fact can be wrong; a
generated one can only be stale.

### 3. The verdict decides which condition is correct

This is the finding. A naive projection emits `pre:` for every row, and that is actively
harmful.

CrossHair's `pre:` means *assume this holds, do not explore outside it*. So:

| Verdict | Emits | Why |
| --- | --- | --- |
| `reject` | `raises: <Error>` | The function is **total**. Outside the range it raises, on purpose. A `pre:` here tells CrossHair not to explore the exact inputs the guard exists for - it would hide the bug the guard was written to catch. |
| `clamp` | nothing | Total, defined everywhere, raises nothing. There is no condition to state. |
| `propagate` | `pre: <condition>` | The one case where a precondition is literally true: the function is **undefined** outside the range and the caller carries it. Without `pre:` CrossHair reports failures the author already said they do not handle. |

Emitting `pre:` for a `reject` row would suppress exactly the counterexamples that matter.
Emitting it for a `clamp` row would describe a restriction that does not exist. The three
verdicts are not three flavours of the same annotation - they are three different claims
about the domain of the function, and only one of them is a precondition.

The `Preconditions` table is therefore not only documentation. It carries precisely the
information needed to generate a correct CrossHair annotation, which nothing else in the
system had.

## What is built now

`scripts/conditions.py`:

- `render_conditions(...)` - the docstring block for one function, from its contract rows
- `project(...)` - a module's source with each public function's block inserted or refreshed
- `stale(...)` - `Finding`s where a module's block no longer matches its contract

The block is delimited the way the contract's derived sections are, so the boundary between
generated and hand-written is visible in the file rather than remembered:

```python
def intrinsics_from_fov(width: int, height: int, hfov_deg: float) -> Intrinsics:
    """Build a pinhole camera model from a field of view.

    A caller passes the sensor size it actually captured at.

    .. derived from docs/contracts/trackscope.data.md - regenerate, do not edit
    raises: InvalidFovError
    pre: width > 0
    .. end derived
    """
```

## What is deliberately not built

**Nothing rewrites a module without being asked.** `project()` returns new source; the
command writes it only on request. Every generator in this plugin so far writes a *new* file
- a contract, a test file, a sandbox script. Editing a file the author already owns is a
different act, and it gets an explicit command rather than a silent pass.

**The gate does not yet block on a stale block.** `stale()` returns findings and the command
reports them; wiring that into `require_contract.py` waits until the projection has run
against real repositories. A gate that blocks on a generator nobody has exercised is how
incident 005 happened - three of ten rules misfired on first contact with real code.

## What this does not fix

CrossHair found `intrinsics_from_fov(1, 1, 5e-324)` *inside* a precondition a human wrote.
`5e-324` satisfies `0 < hfov_deg < 180` and still breaks the function. A projection cannot
help with that: it faithfully reproduces a claim that was too weak. That is the
**insufficient guard** case, it belongs to issue #4, and no amount of generating annotations
reaches it.
