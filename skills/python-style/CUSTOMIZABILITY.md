# Customizability

Rules for how callers configure, substitute and extend. The aim is that a new use case costs
a parameter, not an edit to the module.

## Accept dependencies; construct them at the entry point

A constructed dependency is a hidden seam: tests must patch an import to reach it.

```python
# good
def run(source: FrameSource, sink: Sink, cfg: Settings) -> Report: ...

# composition root, one place in the program
def main() -> None:
    run(RtspCamera(cfg.url), FileSink(cfg.out), cfg)

# bad
def run(cfg: Settings) -> Report:
    source = RtspCamera(cfg.url)      # the test now needs monkeypatch
```

## Build one frozen config at the entry point and pass it down

A single immutable object read once makes the program's inputs enumerable and its behaviour
reproducible from the object alone.

```python
# good
@dataclass(frozen=True, slots=True)
class Settings:
    model_path: Path
    threshold: float = 0.5

# bad
def detect(frame: Frame) -> list[Box]:
    thr = float(os.environ.get("THRESH", "0.5"))   # input appears mid-call-stack
```

## Keep defaults in the config type

Defaults repeated at call sites drift; one of them is always the odd one out.

```python
# good: threshold: float = 0.5 on Settings, nowhere else
# bad:  cfg.threshold or 0.5   # repeated at four call sites, one says 0.4
```

## Introduce a Protocol on the second implementation

One implementation means a hypothetical seam, and a hypothetical seam is usually wrong about
what varies. A test fake counts as the second implementation.

Which construct to reach for, and the rules for inheritance, ABCs and mixins, are in
[design-patterns/INHERITANCE.md](../design-patterns/INHERITANCE.md). Not repeated here.

## Extend by passing, not by editing

A new case that requires editing a conditional inside the module makes every extension a
change to shared code, and every extension a merge conflict.

```python
# good
def run(frames: Iterable[Frame], score: Callable[[Frame], float]) -> Report: ...

# bad
def run(frames: Iterable[Frame], mode: str) -> Report:
    if mode == "fast": ...
    elif mode == "accurate": ...     # every new mode edits this function
```

## Hold no mutable state at module level

Module state is a shared global: it leaks between tests, forbids two configurations in one
process, and makes call order significant.

```python
# good
class Tracker:
    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

# bad
_SEEN: dict[str, int] = {}
```

## Let the caller choose the failure policy

Retries, timeouts and fallbacks are caller policy; a module that hard-codes them cannot be
used by a caller with a different budget.

```python
# good
def fetch(url: str, *, timeout_s: float, retries: int = 0) -> bytes: ...

# bad
def fetch(url: str) -> bytes:
    for _ in range(3):              # the caller with a 50 ms budget is stuck
        ...
```
