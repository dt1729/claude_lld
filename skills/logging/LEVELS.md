# Choosing a level

The level is a claim about **who must act, and how soon**. Decide it by answering that, then
check the claim against the table. Every other way of choosing — how unusual the event is,
how much work it took, how proud you are of the code path — produces logs that are loud
where nothing matters and silent where something does.

## The procedure

```
Did the operation fail in a way the system could not recover?
├── Yes → must a human intervene before it works again?
│         ├── Yes → ERROR
│         └── No, the caller handles it → return the failure; log at INFO if a count matters
└── No  → did the system do something unplanned to succeed? (retry, fallback, degrade)
          ├── Yes → will the cause fix itself?
          │         ├── No  → WARNING
          │         └── Yes → INFO
          └── No  → is this a state change an operator needs afterwards?
                    ├── Yes → INFO
                    └── No  → DEBUG, or nothing at all
```

The last branch is the one that keeps logs readable. "Nothing at all" is a valid outcome and
the most under-used one.

## Worked cases

| Event | Level | Why |
| --- | --- | --- |
| Config file missing at startup | ERROR | Cannot run; a human must supply it |
| A frame fails to decode, pipeline continues | INFO | Expected with real hardware; the count matters, the event does not |
| 40% of frames fail to decode | WARNING | Recovered, but a camera needs attention |
| Upstream call retried once, then succeeded | INFO | Self-correcting; noise at WARNING |
| Upstream call retried three times, then succeeded | WARNING | Working, but the dependency is degrading |
| Upstream call exhausted retries | ERROR | The operation failed and will keep failing |
| User submitted an invalid threshold | INFO | The system worked; validation did its job |
| Database schema is newer than this build | ERROR | Cannot proceed correctly; needs a deploy |
| Cache miss | DEBUG, or nothing | Normal operation; at INFO it drowns everything else |
| Job started / finished, with duration | INFO | The spine of "what happened last night" |
| Parsed 1,204 records from a file | INFO | One line, with a count — not 1,204 lines |

## One line per unit of work

The unit is whatever the operator reasons about: a request, a job, a file, a run. Log its
start and its outcome, with identifiers and a duration. Do not log each step inside it at
INFO; those are DEBUG.

```python
# good
log.info("run %s complete: %d frames, %d detections, %d ms", run_id, frames, hits, ms)

# bad: a thousand lines that say nothing collectively
for frame in frames:
    log.info("processing frame %d", frame.index)
```

The test: could an operator reconstruct last night from the INFO lines alone, without
reading any of them twice? If INFO volume scales with input size rather than with work
units, the level is wrong.

## Levels are a promise

Changing a line's level changes who gets woken up. Moving something to ERROR adds a pager
entry; moving something off ERROR silently removes one. Treat a level change the way you
treat a signature change — library-builder perspective — and say so in the contract diff.

Message text is a promise too. Somebody's alert matches on it. Keep the prefix stable and
put the variable parts in arguments, which is another reason for lazy formatting: the
format string becomes the stable event identity.

## DEBUG is for reproduction, not narration

DEBUG earns its place when it would let a developer reproduce a fault without adding new
logging. That means inputs, decisions taken, and the values a branch turned on.

```python
# good: enough to replay the decision
log.debug("threshold %.2f from %s, %d candidates above it", threshold, source, count)

# bad: narrates control flow, helps nobody
log.debug("entering select_targets")
log.debug("loop iteration")
```

DEBUG must never be load-bearing: no side effects in a log call, and nothing that only works
when the level is enabled.

## No custom levels

Python gives five. A sixth between INFO and WARNING always turns out to mean "I was not sure
who should act", which is the question the level exists to answer. Decide instead.
