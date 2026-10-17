# Design it twice

The first interface you think of is the one the implementation suggested. It encodes how you
happened to decompose the problem, not what callers need. Designing a second, *materially
different* interface costs minutes and changes the outcome more than any amount of polishing
the first.

## Procedure

1. **State the caller's job** in one sentence, with no reference to internals.
2. **Produce two or three interfaces that differ in kind**, not in naming. Varying a parameter
   name or swapping a function for a method is the same design twice.
3. **Score each** against the table below.
4. **Write down the one you rejected and why**, in the contract's Seam section. The rejected
   alternative is the most useful thing a future reader can have.

Radically different means different along one of these axes:

| Axis | Option A | Option B |
| --- | --- | --- |
| Who holds state | caller passes it each call | module owns a session object |
| When work happens | eager, returns a result | lazy, returns a plan the caller runs |
| What varies | one function, a config object | several small adapters at a seam |
| Direction of control | caller drives a loop | module drives, caller supplies a callback |
| Failure shape | raises on bad input | returns a result the caller must inspect |

## Scoring

Rank the candidates on each, highest first. If one wins on depth and loses on everything
else, it is usually still the right answer.

- **Depth** — behaviour available per unit of interface the caller must learn.
- **Locality** — where a likely change lands. One module, or N call sites?
- **Seam placement** — does the thing that actually varies sit at the seam? A seam in the
  wrong place is worse than no seam, because it looks like it is doing work.
- **Test surface** — can every behaviour in the test list be reached through the interface,
  with no patching?
- **Wrongness cost** — if this design is wrong in three months, is it a rename, or a rewrite
  of every caller?

## Worked example

Caller's job: *run a detector over a video and get per-frame results.*

**A — eager, returns everything.** `detect_video(path, cfg) -> list[FrameResult]`
Depth high, test surface trivial. Fails on long videos: holds every result in memory, and the
caller cannot stop early or show progress.

**B — iterator.** `detect_video(path, cfg) -> Iterator[FrameResult]`
Same interface size, streams, caller controls consumption and can stop early. Loses the
simple "give me all of it" case by one `list()` call.

**C — callback.** `detect_video(path, cfg, on_result: Callable[[FrameResult], None]) -> None`
Inverts control. Caller cannot stop early without an exception, cannot compose with other
iterators, and every test needs a collector function.

Pick **B**. Record in the contract: *"Rejected A (unbounded memory on long inputs) and C
(inverted control defeats early exit and composition). B costs callers one `list()` for the
batch case."*

## Parallel exploration

For a design with wide blast radius, generate the candidates concurrently: dispatch one
subagent per axis with the caller's job statement and no further context, then score the
returned interfaces yourself. Independent generation avoids three variations on the first
idea. Use this when the module is a package's entry point or when several callers already
exist; skip it for a single internal helper.
