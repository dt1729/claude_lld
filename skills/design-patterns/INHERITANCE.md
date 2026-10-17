# Inheritance, composition, Protocol, ABC

Four ways to share or vary behaviour. They are not interchangeable, and the choice is
decided by *who implements* and *who must import whom*.

## The decision

```
Does a caller need to supply their own implementation?
├── No  → no abstract type at all. One concrete class or module of functions.
└── Yes → Must the implementer import your package to satisfy it?
          ├── No  → typing.Protocol      (structural: they inherit nothing)
          └── Yes → abc.ABC              (nominal: shared code or a subclass registry)

Do you want to reuse code from an existing concrete class?
└── Always → composition. Hold an instance; expose what you mean to expose.
```

## Rules

**Inherit only from an abstract type you own, or from a base whose documented contract is
"subclass me".** `Enum`, `Exception`, `TypedDict`, a framework's `Model` — these invite it.
Your own concrete `VideoReader` does not.

```python
# good: composition. The wrapper controls its own surface.
class CachedReader:
    def __init__(self, inner: VideoReader) -> None:
        self._inner = inner
    def read(self) -> Frame | None: ...

# bad: inherits a surface it did not design and cannot shrink
class CachedReader(VideoReader): ...
```

**One level of inheritance from your own abstract base.** A grandchild means the middle class
is doing two jobs — a partial implementation and a variation — and neither is nameable.

**A subclass must accept everything the base accepts and promise everything it promises.**
Narrowing a parameter type, raising a new exception type, or requiring a setup call the base
does not is a Liskov break: callers hold the base type and will be wrong.

```python
# bad: base says any Path works; subclass silently requires a local one
class S3Store(Store):
    def save(self, p: Path) -> None:
        if p.is_absolute(): raise ValueError(...)
```

**`Protocol` when the implementer should not import you.** This is the usual case across a
package boundary, and the reason is dependency direction: the consumer defines the shape it
needs, the provider satisfies it by accident of having the right methods.

```python
# detection/ports.py — consumer-side definition
class FrameSource(Protocol):
    def read(self) -> Frame | None: ...

# camera/rtsp.py — imports nothing from detection
class RtspCamera:
    def read(self) -> Frame | None: ...
```

**`ABC` when you have real shared implementation, or need to enumerate subclasses.** An ABC
whose every method is abstract is a Protocol with extra coupling; convert it.

```python
# good use of ABC: shared retry logic, two concrete transports
class Transport(ABC):
    def send_with_retry(self, b: bytes, *, attempts: int) -> None:  # concrete, shared
        ...
    @abstractmethod
    def _send_once(self, b: bytes) -> None: ...
```

**Introduce the abstract type on the second implementation.** A test fake counts as a second
implementation; an imagined future backend does not. One implementation means you are
guessing what varies, and the guess costs depth immediately.

**Mixins hold no state.** A mixin with `__init__` or instance attributes creates an
initialisation order its users must know, which is the thing mixins were supposed to avoid.
If it needs state, it is a collaborator: hold it as an attribute.

```python
# good
class Exporter:
    def __init__(self, log: Logger) -> None:
        self._log = log

# bad
class LoggingMixin:
    def __init__(self) -> None:
        self._log = make_logger()     # now every user must call super().__init__()
```

**Make the base abstract or make it final.** A concrete class that is also a base is two
contracts in one file: callers depend on its behaviour, subclasses depend on its internals,
and you cannot change either. Mark leaves `@final`.

## When a class is the wrong construct entirely

A class earns its place when it holds state across calls, enforces an invariant over that
state, or is the thing that varies at a seam. Otherwise use a function.

```python
# bad: a class standing in for a function
class ReportGenerator:
    def __init__(self, run: Run) -> None:
        self._run = run
    def generate(self) -> str: ...

# good
def generate_report(run: Run) -> str: ...
```

A class whose methods are all `@staticmethod` is a module with extra syntax. Use a module.
