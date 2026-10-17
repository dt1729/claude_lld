# Pattern catalogue

Each entry: what it is for, the verdict from each perspective that cares, where it goes in
the tree, and the shape that is wrong. Perspectives are defined in
[PERSPECTIVES.md](PERSPECTIVES.md); precedence when they conflict is in
[SKILL.md](SKILL.md#precedence-when-perspectives-conflict).

---

## Singleton

**For:** exactly one of an expensive or stateful resource per process — a connection pool, a
metrics registry, a model loaded into GPU memory.

| Perspective | Verdict |
| --- | --- |
| Operator | **Wants it.** One pool, one warm model, one place to look |
| Library user | **Hostile.** Cannot run two configurations, cannot isolate tests |
| Library builder | **Veto on the global form.** Un-globalling it later breaks every caller |
| Developer | Hidden coupling; tests leak state between cases |

**Resolution: the instance is a singleton, the type is not.** Construct one at the
composition root and pass it down. The operator gets one pool; the library user can build a
second; nobody depends on a global.

```python
# good — composition root owns the single instance
def main() -> None:
    pool = ConnectionPool(cfg.dsn, size=cfg.pool_size)
    run(pool, cfg)

# bad — the decision is now unavailable to every caller forever
class ConnectionPool:
    _instance: ConnectionPool | None = None
    @classmethod
    def instance(cls) -> ConnectionPool: ...
```

**Lives in:** the module that owns the type defines the class; `main`/`cli` constructs it.

---

## Factory

**For:** construction that requires a decision the caller should not make — selecting an
implementation, validating raw input into a guaranteed-valid type, or reusing an expensive
intermediate.

| Perspective | Verdict |
| --- | --- |
| Library user | Good: one call, no knowledge of which class comes back |
| Library builder | Good: the concrete type stays replaceable |
| Developer | Harmful when it only forwards to a constructor |

**Apply the deletion test.** Delete the factory: if callers write `Thing(...)` and nothing
else is lost, the factory was a pass-through.

```python
# good: the choice and the validation are the factory's job
def make_source(cfg: Settings) -> FrameSource:
    if cfg.url.startswith("rtsp://"):
        return RtspCamera(cfg.url, timeout_s=cfg.timeout_s)
    return VideoFile(Path(cfg.url))

# bad
def make_detector(cfg: Settings) -> Detector:
    return Detector(cfg)
```

**Lives in:** the module that owns the returned type, named `make_x` or `from_y`. A separate
`factories.py` is a smell unless the factory needs dependencies the type's module must not
import — in which case it belongs at the composition root instead.

---

## Registry

**For:** a set of implementations that third parties extend and you cannot enumerate.

| Perspective | Verdict |
| --- | --- |
| Library builder | Good: new backends touch no shared file |
| Developer | **Hostile:** behaviour depends on import order; "find all implementations" fails |
| Library user | Harmed when a missing import silently changes behaviour |

**Default to an explicit dict at the composition root.** Reach for decorator registration
only when the implementations genuinely come from outside your repo.

```python
# good — enumerable, greppable, no import-order dependency
BACKENDS: Final = {"yolo": make_yolo, "rtdetr": make_rtdetr}

# use only for true third-party extension
@register("yolo")
class YoloDetector: ...
```

---

## Strategy

**For:** behaviour that varies per call site, chosen by the caller.

A `mode: str` parameter with a branch inside is a strategy that has not been extracted; every
new mode edits shared code and the parameter accepts values the type system cannot check.

```python
# good
def run(frames: Iterable[Frame], score: Callable[[Frame], float]) -> Report: ...

# acceptable when the set is genuinely closed and exhaustiveness matters
def run(frames: Iterable[Frame], mode: Mode) -> Report:   # Mode is an Enum
    match mode: ...

# bad
def run(frames: Iterable[Frame], mode: str) -> Report:
    if mode == "fast": ...
```

**Enum over callable when** the set is closed, the caller must not invent members, and you
want `match` exhaustiveness. **Callable over enum when** callers legitimately supply their own.

---

## Builder

**For:** an object with many optional parts where intermediate states are invalid.

In Python this is usually unnecessary: keyword arguments with defaults, or a frozen dataclass
with `replace()`, cover it. Reach for a builder only when construction is genuinely staged
and a half-built object must not be usable.

```python
# good — Python already has the builder
@dataclass(frozen=True, slots=True)
class Query:
    table: str
    limit: int = 100
q2 = replace(q, limit=10)

# bad — six methods and a mutable object to avoid four keyword arguments
QueryBuilder().table("runs").limit(10).build()
```

---

## Adapter

**For:** making a foreign interface satisfy a seam you own.

| Perspective | Verdict |
| --- | --- |
| Library user | Good: your package stops leaking a vendor's types |
| Developer | Good when thin; a second place to look when it grows logic |

Keep the adapter translating only. Logic inside an adapter is logic that exists once per
backend, which is how three backends end up with three different behaviours.

**Lives in:** beside the thing being adapted, never beside the seam. `camera/rtsp.py` adapts
RTSP to `FrameSource`; `detection/` never learns that RTSP exists.

---

## Context manager

**For:** anything acquired that must be released — files, sockets, locks, GPU memory,
temporary state.

| Perspective | Verdict |
| --- | --- |
| Operator | **Wants it:** clean shutdown, no leaked handles on failure |
| Developer | Lifetime is visible in the indentation |

If a type has `open()`/`close()`, `start()`/`stop()`, or `acquire()`/`release()`, it needs
`__enter__`/`__exit__` as well. A caller who must remember the second call will eventually not.

```python
# good
with VideoFile(path) as src:
    run(src)

# bad: the exception path leaks the handle
src = VideoFile(path); run(src); src.close()
```

---

## Class vs function

A class earns its place when it **holds state across calls**, **enforces an invariant over
that state**, or **is the thing that varies at a seam**. Otherwise write a function.

```python
# bad: constructed, called once, discarded
class ReportGenerator:
    def __init__(self, run: Run) -> None: self._run = run
    def generate(self) -> str: ...

# good
def generate_report(run: Run) -> str: ...
```

Related: a class of only `@staticmethod` is a module; a dataclass with methods that ignore
its fields is two things.

---

## Dataclass vs TypedDict vs NamedTuple vs plain class

| Use | When |
| --- | --- |
| `@dataclass(frozen=True, slots=True)` | Default for data that crosses a seam |
| `TypedDict` | The data *is* JSON and must stay a dict at the boundary |
| `NamedTuple` | Positional unpacking is the point, and there are two or three fields |
| Plain class | There is an invariant to enforce in `__init__`, or state that mutates |

Frozen by default: a mutable value object passed across a seam makes every holder a potential
writer, and the bug appears far from the write.
