# Contracts

A contract is the written output of design, produced before the implementation. The gate
refuses a new module under `src/` until its contract validates.

**Prevents:** a module with no stated responsibility, no decided seam, and no answer to what
each parameter refuses - code that exists and runs and was never designed.

The authoring guide, with a full worked example, is
[skills/new-module/CONTRACT-FORMAT.md](../../skills/new-module/CONTRACT-FORMAT.md). This page
is what the scripts actually check.

## Where it lives

`docs/contracts/<dotted.module.path>.md`, relative to the project root. The path segment up
to and including `src` is dropped:

| Module | Contract |
| --- | --- |
| `src/detection/pipeline.py` | `docs/contracts/detection.pipeline.md` |
| `src/shapes/square.py` | `docs/contracts/shapes.square.md` |

The gate resolves it against the session's working directory. Every CLI resolves it against
the current directory, so run them from the project root.

## What validation refuses

`contracts.validate_contract` returns a list of reasons; empty means it validates.

| Check | Refused when |
| --- | --- |
| Required sections | any of `Responsibility`, `Interface`, `Preconditions`, `Seam`, `Dependencies`, `Errors`, `Observability`, `Tests`, `Deletion test` is missing as a `## ` heading (case-insensitive) |
| Placeholders | a section is empty, or has a line that is only `TODO`, `TBD`, `...`, `<...>` or `{{...}}` |
| Status | no `**Status:**` line, or a value other than `draft`, `accepted`, `superseded` |
| Interface | no fenced code block |
| Dependencies | no `May import` line |
| Errors | no table and no `No error modes.` |
| Observability | no `No logging.` and no level named (`debug`, `info`, `warning`, `error`) |
| Preconditions | not `No preconditions.` and no table; a table with no rows; a row naming no verdict |
| Tests | fewer than three `-` or `*` bullets |

Two things the authoring guide asks for are **not** checked by the code: a Responsibility
without " and ", and at least one failure case among the Tests bullets. They are review.

`draft` validates. The new-module skill's completion criteria ask for `accepted`; nothing
enforces it.

## Preconditions

`Errors` asks what a function raises. `Preconditions` asks what it refuses: one row per
parameter, three columns, and exactly one of three verdicts.

```markdown
## Preconditions

| Parameter | Must satisfy | On violation |
| --- | --- | --- |
| `width` | `> 0` | **reject** - `InvalidFovError` naming the value |
| `cfg.threshold` | `0.0 <= threshold <= 1.0` | **clamp** to the range, log at WARNING |
| `hfov_deg` | `0 < hfov_deg < 180` | **propagate** - the caller validated it |
```

| Verdict | Means | Test stub | Docstring condition |
| --- | --- | --- | --- |
| `reject` | raise, naming the offending value | `test_rejects_<parameter>` | `raises: <Error>` |
| `clamp` | substitute a safe value, log at WARNING | none | none |
| `propagate` | documented precondition, deliberately unchecked | none | `pre: <condition>` |

`No preconditions.` is a complete answer for a function nothing can be got wrong with.

How a row is read:

- Backticks and bold are stripped. The verdict is the first of `reject`, `clamp`,
  `propagate` found in the third cell, so prose after it is fine.
- The exception for `raises:` is the first `...Error` or `...Exception` name in the verdict
  cell, then in the condition; `ValueError` if neither names one.
- A condition starting with an operator (`> 0`) is read as `<parameter> > 0`.
- A row applies to a function when its parameter (`cfg` for `cfg.threshold`) is one of
  that function's parameters. Qualify it as `function.parameter` when two functions share a
  name.

**Prevents:** a function that silently accepts a value it cannot handle. On the case that
motivated it, `Range: bytes=100-50` returned `Content-Length: -49` and a 180 degree field of
view built a camera with focal length `5.9e-14`, with every gate green
([proposal 001](../proposals/001-preconditions.md)).

### `verdict_counts`

`contracts.verdict_counts(rows)` returns `{"reject": n, "clamp": n, "propagate": n}` for a
parsed table. It exists so a module whose every row says `propagate` is visible. It is a
Python function only: no command or script prints it yet.

## Derived and declared

| Derived - generated inside `<!-- derived -->` markers | Declared - written by you, never touched |
| --- | --- |
| `Interface`: public signatures | `Responsibility` |
| `Dependencies`: imports out, importers in | `Seam`, and what you rejected |
| `Errors`: exception types raised | what each error means to a caller |
| | `Preconditions`, `Observability`, `Tests`, `Deletion test` |

`/lld-seed:derive <module>` writes the derived blocks ([commands.md](commands.md#derive)).
Real output for a two-name module:

~~~markdown
## Interface

<!-- derived -->
```python
InvalidSideError()
Square(side_m: float)
  .area_m2 -> float
def scale(square: Square, factor: float) -> Square
```

_Generated from the source. Dynamic imports, re-exports and raises inside helpers are not visible here._
<!-- /derived -->
~~~

Facts worth knowing before the first run:

- **The first run inserts, it does not replace.** A section with no block gets one at the
  top; your hand-written signatures, `May import` line and errors table stay beneath it.
  Delete the duplicates, keep the prose (invariants, `Must not import`, caller responses).
- **The derived `May import` is what the module does import**, `__future__` included, not
  what it is allowed to import. State the policy in your prose beneath the block.
- **`Imported by` is computed** from every module under `src/` that imports this one.
- **After the first run, rule 37 reads the derived block**, because it is now the first
  fenced block in `## Interface`.

## The waiver ledger

`docs/contracts/_waivers.md`. See [gate.md](gate.md#the-waiver-ledger).

## Changing a contract

Edit the contract, then the code. Set `Status: superseded` and link forward when a module is
replaced rather than changed. Once the contract has derived blocks, an interface change
needs the step in [troubleshooting.md](troubleshooting.md#rule-38-refuses-a-deliberate-interface-change).
