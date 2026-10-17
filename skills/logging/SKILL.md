---
name: logging
description: Design what a module logs - choosing levels by who must act, what every line must carry, what must never be logged, and the library-versus-application split. Use when adding a log line, choosing between DEBUG INFO WARNING ERROR, handling an exception, configuring logging, deciding what an operator needs to diagnose a failure, or reviewing code for logging misuse.
---

# Logging

**A log line is an interface, and the operator is its caller.** It has everything an
interface has: a contract, invariants, and a promise you break at someone else's cost.
Somebody's alert fires on your message text; somebody's dashboard groups by your field names.
Design log output with the same discipline as a function signature, and record it in the
contract's Observability section before writing the code.

Terms are in [GLOSSARY.md](../../GLOSSARY.md). The perspectives referenced below are defined
in [design-patterns/PERSPECTIVES.md](../design-patterns/PERSPECTIVES.md).

## The level is chosen by who must act

Not by how interesting the event felt. Asking "who reads this, and what do they do about it"
answers the question every time; asking "how important is this" never does.

| Level | Who acts | When |
| --- | --- | --- |
| **ERROR** | An operator, now | The operation failed and the system could not recover it. Something a human must fix |
| **WARNING** | An operator, later | The system recovered — retried, fell back, degraded — but the cause will not fix itself |
| **INFO** | An operator, afterwards | A state change needed to reconstruct what happened. One line per unit of work, not per step |
| **DEBUG** | A developer reproducing a fault | Inputs and intermediate state. Off in production, and never load-bearing |

Two consequences people skip:

- **An expected condition is not an ERROR.** A validation failure on user input is the system
  working. Log it at INFO if the operator needs the count, and return the failure to the
  caller. `ERROR` that fires nightly trains its reader to ignore it, which costs you the one
  night it mattered.
- **WARNING means "nobody is awake for this".** If nobody would act on it within a week, it
  is INFO. If somebody must act within the hour, it is ERROR.

Full decision procedure and worked cases: [LEVELS.md](LEVELS.md).

## Libraries log; applications configure

The sharpest rule here, and the one most often broken.

A library **emits** records through `logging.getLogger(__name__)` and does nothing else: no
handlers, no `basicConfig`, no level, no format. The application owns all of that, because
only the application knows whether output goes to a terminal, a file, or a log shipper.

```python
# good, in a library module
log = logging.getLogger(__name__)


def load(path: Path) -> Calibration:
    log.debug("reading calibration from %s", path)


# good, in the application's composition root, once
def main() -> None:
    logging.basicConfig(level=cfg.log_level, format=cfg.log_format)


# bad, in a library: steals a decision the caller cannot take back
logging.basicConfig(level=logging.INFO)
log.setLevel(logging.DEBUG)
```

A library that configures logging is the same defect as a library that reads `os.environ`:
it takes a decision away from someone who cannot override it. Library-user perspective, and
it governs because the module is exported.

## Lazy formatting, always

Pass the format string and its arguments separately. Interpolating with an f-string formats
the message even when the level is disabled, and destroys the grouping key that aggregators
use to collapse a million lines into one event with a count.

```python
# good: formatted only if the level is enabled; groups as one event
log.info("calibration loaded for device %s in %d ms", device_id, elapsed_ms)

# bad: cost paid always, and every line is a unique string
log.info(f"calibration loaded for device {device_id} in {elapsed_ms} ms")
```

## Every line carries its subject

A line that says a thing happened, without saying what it happened to, is unusable the one
time it matters. Name the entity in every line: the request, device, file, job — whatever the
operator would grep for.

```python
# good
log.warning("retrying frame fetch for device %s, attempt %d", device_id, attempt)

# bad
log.warning("retrying")
```

## Log an exception once, where it is handled

Logging at every level as an exception rises produces one failure reported five times, and
the reader cannot tell whether that is five failures. Log where you handle it; re-raise
without logging where you do not.

```python
# good: handled here, so reported here, with the traceback
try:
    cal = load_calibration(path)
except CalibrationMissingError:
    log.exception("no calibration for %s, falling back to defaults", device_id)
    cal = DEFAULT_CALIBRATION

# bad: reported twice, and the second reader cannot tell it is the same failure
except CalibrationMissingError as exc:
    log.error("could not load calibration: %s", exc)
    raise
```

Use `log.exception` (or `exc_info=True`) inside an `except` block. `log.error(str(exc))`
discards the traceback, which is the part that locates the fault.

## Never log a secret

Credentials, tokens, keys, personal data, and full request bodies that may contain any of
them. Logs are copied to places the original data was never cleared for, and a log is the
hardest store to redact after the fact. Log an identifier, never the payload.

```python
# good
log.info("authenticated device %s", device_id)

# bad
log.info("authenticating with token %s", token)
```

## Record it in the contract

Every contract carries an **Observability** section:

- what this module logs at INFO, and the event name for each
- what raises it to WARNING or ERROR
- the context fields every line carries
- what must never be logged here

A module with nothing worth logging writes `No logging.` and that is a legitimate answer —
a pure function usually has nothing to say. Making the claim explicit is the point: it
distinguishes "designed to be silent" from "nobody thought about it".

## What the gate enforces

Entries 19 to 24 of [ANTI-PATTERNS.md](../design-patterns/ANTI-PATTERNS.md) are logging
rules, and the detector decides most of them from the AST: `print` in a package module,
configuring logging outside the composition root, eager f-string formatting, a logger named
by a string literal, a swallowed exception, and `log.error` inside `except` without the
traceback.
