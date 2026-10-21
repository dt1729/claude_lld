# Contract format

A contract is the written output of design, produced **before** implementation. It lives at
`docs/contracts/<dotted.module.path>.md` — `src/detection/pipeline.py` has the contract
`docs/contracts/detection.pipeline.md`.

The gate validates its *structure*: every required heading present, none left empty or
holding placeholder text. It does not grade the content. A contract that passes validation
and says nothing is a failure of the author, which is why the headings ask for specifics
rather than prose.

## Template

```markdown
# Contract: detection.pipeline

**Status:** draft

## Responsibility

Turn a stream of raw frames into scored detections, applying the active calibration.

## Interface

```python
def run(source: FrameSource, cfg: Settings) -> Iterator[Detection]
```

- Yields in frame order; a dropped frame yields nothing rather than a gap marker.
- `source` is consumed, not copied: a second call on the same source yields nothing.
- Calibration is read once at first `next()`, not per frame.
- Latency is dominated by the detector; this module adds no buffering.

## Preconditions

| Parameter | Must satisfy | On violation |
| --- | --- | --- |
| `source` | open, not already consumed | **reject** - `ValueError` naming the source |
| `cfg.threshold` | `0.0 <= threshold <= 1.0` | **clamp** to the range, log at WARNING |
| `cfg.device_id` | matches a calibrated device | **propagate** - the caller built it |

## Seam

`FrameSource` is the seam: the variation is file-vs-camera, and both exist today
(`VideoFile`, `RtspCamera`). The detector is **not** behind a seam — one implementation,
so a Protocol there would be hypothetical.

Rejected: a callback form (`run(source, on_detection)`). Inverts control, defeats early
exit, and every test needs a collector. Governed by the library-user perspective, since
`run` is exported.

## Dependencies

- **May import:** `detection.calibration`, `detection.lib.*`, stdlib, `numpy`
- **Must not import:** `camera.*` (adapters depend on us, not the reverse), `cli`
- **Imported by:** `cli`, `detection.benchmark`

## Errors

| Type | Raised when | Caller response |
| --- | --- | --- |
| `CalibrationMissingError` | no calibration for the source's device id | prompt the operator to calibrate |
| `SourceExhaustedError` | source closed mid-stream | retry with a new source |

Invalid detections are dropped, not raised: a bad frame is expected, not exceptional.

## Observability

- **INFO** `run.complete` — one line per run: run id, frame count, detection count, duration.
- **WARNING** when more than 10% of frames fail to decode in a run: names the device id.
- **ERROR** never from this module; `CalibrationMissingError` reaches the caller, which
  decides whether it is fatal.
- Every line carries the device id, which is what an operator greps for.
- Never logged: the frame payload, and the calibration file contents.

## Tests

- yields one detection per frame above threshold, in order
- drops detections below threshold
- reads calibration exactly once across a 100-frame run
- raises `CalibrationMissingError` for an unknown device id
- a closed source part-way through raises `SourceExhaustedError`
- a source yielding zero frames completes without error

## Deletion test

Deleting this module pushes frame ordering, calibration caching and threshold filtering into
`cli` and `benchmark` separately — two copies that would drift. It earns its keep.
```

## Derived and declared

Three sections are **generated from the code** and sit inside `<!-- derived -->` markers:
`Interface`, `Dependencies` and `Errors`. Do not edit inside the markers - the next run
overwrites them. Regenerate with:

```
/lld-seed:derive <module>
```

Everything outside the markers is yours and is never touched: what the seam is for, what you
rejected, what each error means to a caller, the deletion test. A derived block lists the
exception types a module raises; the sentence saying *when* and *what a caller should do*
goes in your prose beneath it, because no parser knows that.

The gate checks that the derived half is current, so a contract can be stale but not wrong.
What the syntax tree cannot see - a dynamic import, a re-export, a raise inside a helper -
each block says on its own face.

## Required sections

| Heading | Must contain | Rejected if |
| --- | --- | --- |
| `Responsibility` | one sentence | contains " and " joining two capabilities |
| `Interface` | at least one signature in a code block | empty, or prose with no signature |
| `Preconditions` | a verdict per parameter, or `No preconditions.` | a row naming no verdict |
| `Seam` | what varies, or an explicit statement that nothing does | empty |
| `Dependencies` | a `May import` line | missing the line |
| `Errors` | a table, or the sentence `No error modes.` | empty |
| `Observability` | what is logged and at which level, or `No logging.` | names no level |
| `Tests` | at least three bullets, at least one a failure case | fewer than three |
| `Deletion test` | what reappears in callers | empty |

`Status` is `draft`, `accepted` or `superseded`.

## Writing the Preconditions section

`Errors` asks what a function **raises**. It never asks what a function **refuses**, and
filled in honestly it becomes a changelog of current behaviour rather than a specification.
This table asks the other question, one row per parameter, and the answer is one of exactly
three words:

| Verdict | Means | Costs |
| --- | --- | --- |
| `reject` | raise, naming the offending value | a guard in the body, and a test |
| `clamp` | substitute a safe value and log at WARNING | silent correction, so the log line matters |
| `propagate` | documented precondition, deliberately unchecked | the caller carries it |

**`propagate` is legitimate.** A function called per frame should not revalidate what its
caller guarantees, and a guard written only to satisfy a rule is worse than none. What the
table forbids is leaving the question unanswered.

It is also the verdict that will be abused. A module whose every row says `propagate` has
turned the section into a formality, the same way a module accumulating waivers is telling
you about the module rather than the rules.

`No preconditions.` is a complete answer for a function that takes nothing a caller can get
wrong. Make the claim explicitly, so "designed to accept anything" is distinguishable from
"nobody thought about it" - the same reason `No logging.` exists.

### Why this is not covered by the type annotations

A type says `float`. It does not say `0 < hfov_deg < 180`, and the gap between those two is
where the failures live: a field of view of 180 degrees builds a camera with a focal length
of `5.9e-14` and produces a garbage bearing for every frame, with no error raised. The
annotation is necessary and not sufficient.

## Writing the Observability section

Logging is part of the interface, not an afterthought: the operator is a caller, and a log
line is a promise somebody's alert depends on. State what is emitted at INFO and the event
name for each, what raises it to WARNING or ERROR, the context every line carries, and what
must never be logged here.

`No logging.` is a legitimate answer — a pure function usually has nothing to say. Making
the claim explicit distinguishes "designed to be silent" from "nobody thought about it".

Levels are chosen by who must act, not by how interesting the event is. See
[logging/LEVELS.md](../logging/LEVELS.md).

## Writing the Interface section

The signature is the easy half. The value is in the facts types cannot carry, and a contract
whose Interface section holds only a signature has skipped the work:

- **Invariants** the caller must maintain, and ones the module guarantees
- **Ordering and lifecycle** — what must be called first, what may be called twice
- **Ownership** — who closes it, who may mutate what is returned
- **Units** for every physical quantity
- **Performance** a caller would be surprised by: an O(n²), a network call, a GPU warm-up

## When the design changes

Edit the contract, then the code, in that order. The contract is versioned, so the diff
records why an interface changed and what was rejected — the question nobody can answer six
months later. A contract that no longer describes the code is worse than none, because it
misleads with authority.

Set `Status: superseded` and link forward when a module is replaced rather than changed.
