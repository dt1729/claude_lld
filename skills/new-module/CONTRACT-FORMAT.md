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
**Depth:** senior

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

## Required sections

| Heading | Must contain | Rejected if |
| --- | --- | --- |
| `Responsibility` | one sentence | contains " and " joining two capabilities |
| `Interface` | at least one signature in a code block | empty, or prose with no signature |
| `Seam` | what varies, or an explicit statement that nothing does | empty |
| `Dependencies` | a `May import` line | missing the line |
| `Errors` | a table, or the sentence `No error modes.` | empty |
| `Observability` | what is logged and at which level, or `No logging.` | names no level |
| `Tests` | at least three bullets, at least one a failure case | fewer than three |
| `Deletion test` | what reappears in callers | empty |

`Status` is `draft`, `accepted` or `superseded`. `Depth` is `junior`, `senior` or
`principal`, and the gate cross-checks it: a module with more than two public names cannot
be `junior`.

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
