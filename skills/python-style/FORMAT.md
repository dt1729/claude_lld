# Naming and docstrings

Layout, quotes, import order and PEP 8 casing are enforced by `ruff format` and absent here.
What follows is the part a formatter cannot decide: which word, and what the docstring owes
a caller.

## Name functions as verb phrases, predicates as questions

A name that reads as a noun gives no clue whether calling it does anything.

```python
# good
def load_calibration(path: Path) -> Calibration: ...
def is_saturated(px: int) -> bool: ...
def has_expired(t: Token, now: datetime) -> bool: ...

# bad
def calibration(path: Path) -> Calibration: ...
def saturated(px: int) -> bool: ...
```

## Reserve `make_` and `from_` for construction

A consistent prefix tells the reader a new object comes back and nothing else happened.

```python
# good
def make_tracker(cfg: Settings) -> Tracker: ...
def from_yaml(text: str) -> Settings: ...

# bad
def tracker_setup(cfg: Settings) -> Tracker: ...
def get_settings(text: str) -> Settings: ...     # "get" implies retrieval, not parsing
```

## Put the unit in the name of every physical quantity

Unit mismatches are the cheapest bug to prevent at the name and the most expensive to find
in a log.

```python
# good
timeout_s: float
distance_m: float
mass_kg: float

# bad
timeout: float      # seconds? milliseconds? the caller guesses
```

## Spell names out, except for domain-standard abbreviations

An abbreviation saves the writer once and costs every reader; a domain term the field already
uses costs nobody.

```python
# good
detection_count, calibration, rms, fov, roi, iou

# bad
det_cnt, calib, cfg_mgr, proc_res
```

## Open a module with a one-sentence responsibility

If the sentence needs "and", the module is two modules; the docstring is where that shows up
first.

```python
"""Convert raw sensor frames into calibrated detections."""
```

## Document what the types cannot carry

Restating a signature in prose adds a second thing to keep in sync. Document the facts a
caller needs and the annotations cannot express.

```python
# good
def load_calibration(path: Path) -> Calibration:
    """Read a calibration file.

    The file is read once; later edits are not picked up.
    Raises CalibrationMissingError if the path does not exist, and
    CalibrationInvalidError if the schema version is newer than this build.
    """

# bad
def load_calibration(path: Path) -> Calibration:
    """Load calibration.

    Args:
        path: a Path to the calibration file.
    Returns:
        a Calibration.
    """
```

Document, in this order, only what applies: invariants the caller must maintain, ordering or
lifecycle constraints, error modes with their conditions, units, and performance
characteristics a caller would be surprised by.

## Name every error type for its condition

A caller catches a condition, not a location; error names ending in the module they came
from force the caller to know the layout.

```python
# good
class CalibrationMissingError(DetectionError): ...
class SchemaTooNewError(DetectionError): ...

# bad
class PipelineError(Exception): ...      # raised for six unrelated conditions
```

## Write a TODO with an owner and a trigger

An unattributed TODO is a comment that will never be removed.

```python
# good
# TODO(divya, #142): drop once the firmware reports saturation explicitly.

# bad
# TODO: fix this properly
```
