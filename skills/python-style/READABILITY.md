# Readability

Rules for whether a function can be understood in one pass. Formatting, complexity limits and
blind excepts are enforced by ruff and absent here.

## One level of abstraction per function

A function either orchestrates named steps or performs one step. Mixing the two forces the
reader to switch altitude mid-function.

```python
# good
def publish_report(run: Run, sink: Sink) -> None:
    report = summarise(run)
    rendered = render_markdown(report)
    sink.write(rendered)


# bad: two orchestration lines, then byte-level work
def publish_report(run: Run, sink: Sink) -> None:
    report = summarise(run)
    lines = [f"# {report.title}", ""]
    for row in report.rows:
        lines.append(f"| {row.name} | {row.value:.2f} |")
    sink.write("\n".join(lines))
```

## Name the guarantee, not the mechanism

Callers depend on what is true afterwards; mechanisms change and leave the name lying.

```python
# good
def ensure_calibrated(cam: Camera) -> Calibration: ...


# bad: renaming the cache breaks the name's promise
def check_cache_then_run_calibration(cam: Camera) -> Calibration: ...
```

## Give a multi-operator condition a name

A named boolean states the business rule once; an inline one restates it at every reader.

```python
# good
is_stale = age_s > cfg.max_age_s and not frame.pinned
if is_stale:
    return None

# bad
if age_s > cfg.max_age_s and not frame.pinned:
    return None
```

## Keep the happy path at the lowest indentation

Guard clauses exit early so the main sequence reads top to bottom, unindented.

```python
# good
def load(path: Path) -> Config:
    if not path.exists():
        raise ConfigMissingError(path)
    return _parse(path.read_text())


# bad
def load(path: Path) -> Config:
    if path.exists():
        return _parse(path.read_text())
    else:
        raise ConfigMissingError(path)
```

## Make illegal states unrepresentable

A type that cannot express the bad state removes the check, and the test for the check.

```python
# good
Confidence = NewType("Confidence", float)  # constructed only via validated factory


def make_confidence(v: float) -> Confidence: ...


# bad: every consumer re-validates, and one of them forgets
def score(v: float) -> float:  # 0..1, honest
    ...
```

## Comments carry the why

The code already states what happens; a comment that restates it goes stale silently.

```python
# good
# Vendor firmware reports 0xFFFF for a saturated pixel, not an error.
if raw == 0xFFFF:
    return SATURATED

# bad
# if raw equals 0xFFFF, return saturated
if raw == 0xFFFF:
    return SATURATED
```

## Keep a function's name and its return type honest

A function named for a query must not mutate; one named for a command must not be relied on
for a value. Mixed functions force the caller to read the body.

```python
# good
def next_frame(self) -> Frame | None: ...  # query, no visible effect
def advance(self) -> None: ...  # command


# bad: name says query, body consumes the buffer
def peek(self) -> Frame | None:
    return self._buffer.pop()
```
