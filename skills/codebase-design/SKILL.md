---
name: codebase-design
description: Design deep Python modules - decide interfaces, seams and dependency direction before writing implementation. Use when creating a new module, package, class or public function; when restructuring existing code; when a module has grown two reasons to change; or when asked for low-level design, LLD, architecture, module boundaries, or how to split code up.
---

# Codebase Design

Design **deep modules**: much behaviour behind a small interface, placed at a clean seam,
testable through that interface. The aim is leverage for callers, locality for maintainers,
and testability for everyone.

Terms used here are defined in [GLOSSARY.md](../../GLOSSARY.md) and are not interchangeable
with "component", "service" or "boundary".

## Design before implementation

Produce the contract first, in a file, then write code against it. A contract records:

1. **Responsibility** — one sentence. If it needs "and", you have two modules.
2. **Interface** — public names with signatures, plus the facts types cannot carry:
   invariants, ordering constraints, error modes, units, required configuration.
3. **Preconditions** — one row per parameter: what it must satisfy, and which of
   `reject` / `clamp` / `propagate` happens when it does not. The type says `float`; it does
   not say `0 < hfov_deg < 180`, and the gap between those is where the silent failures live.
4. **Seam** — where the interface lives, and what varies across it.
5. **Dependencies** — what this module may import, and what may import it.
6. **Test list** — behaviours exercised through the interface, including failure modes.
7. **Deletion test** — what complexity reappears in callers if this module vanishes.

The format and a worked example are in
[new-module/CONTRACT-FORMAT.md](../new-module/CONTRACT-FORMAT.md). The `new-module` skill
scaffolds one. A `PreToolUse` hook refuses implementation writes into `src/` until the
contract file exists.

**The front door is part of the design.** A module can have a clean seam, a correct
dependency direction and no input validation anywhere — every gate green on code that
returns `Content-Length: -49` to a browser for `Range: bytes=100-50`. Decide what each
parameter refuses at the same time you decide what the interface accepts, because afterwards
nobody asks the question again.

## Deep vs shallow

```
  DEEP (aim for this)              SHALLOW (avoid)
  ┌───────────────────┐            ┌─────────────────────────────┐
  │  small interface  │            │      large interface        │
  ├───────────────────┤            ├─────────────────────────────┤
  │                   │            │  thin implementation        │
  │   much behaviour  │            └─────────────────────────────┘
  │                   │
  └───────────────────┘
```

When designing an interface, ask in order:

- Can I remove a parameter, or an entire public name?
- Can I move a decision the caller is making into the module?
- Can I hide more complexity behind what remains?

**Good** — one public name; the caller learns a path and gets validation, retries, schema
drift handling and caching:

```python
def load_calibration(path: Path) -> Calibration: ...
```

**Bad** — same work, but every caller must know the order, the intermediate types, and
which steps are optional:

```python
def read_yaml(path: Path) -> dict[str, Any]: ...
def validate_schema(raw: dict[str, Any]) -> dict[str, Any]: ...
def coerce_units(raw: dict[str, Any]) -> dict[str, Any]: ...
def build_calibration(raw: dict[str, Any]) -> Calibration: ...
```

The second form is not "more modular". It is one module with a four-step interface.

## Principles

**Depth is a property of the interface, not the implementation.** A deep module may be
internally composed of small swappable parts; they are simply not public. Internal seams
exist for the module's own tests. External seams exist for its callers.

**The deletion test.** Imagine deleting the module. If complexity vanishes, it was a
pass-through and should go. If complexity reappears across N callers, it earns its keep.

**The interface is the test surface.** Tests and callers cross the same seam. Needing to test
*past* the interface means the module is the wrong shape; fix the shape, do not reach inside.

**One adapter is a hypothetical seam; two is a real one.** Introduce a `Protocol` when a
second implementation exists, not in anticipation of one. Speculative seams cost depth now
and are usually wrong about what varies.

**Split on reasons to change, not on line count.** Two reasons to change in one module is the
signal. A 400-line module with one reason is healthy; a 60-line module with three is not.

## Python specifics

**Entry-point boundary.** A package's public surface is the modules at its root. Everything in
a subfolder is private, whatever it is named. Depth, not designation; no underscore convention
to remember and no barrel `__init__.py` re-exporting the world.

```
detection/
  pipeline.py      # public: callers import detection.pipeline
  calibration.py   # public
  lib/
    nms.py         # private: detection.lib.nms is off limits to other packages
  tests/
```

**Accept dependencies; do not construct them.** Construction belongs at the entry point, so
tests can substitute without patching.

```python
# good: the seam is a parameter
def run(source: FrameSource, detector: Detector) -> Report: ...


# bad: the seam is buried, and the test has to monkeypatch an import
def run() -> Report:
    source = RtspCamera(os.environ["CAM_URL"])
```

**Return values; do not mutate arguments.** A returned result is checkable in one line; a
mutation requires reconstructing the state that preceded it.

**Model states as types, not flags.** `Frame | None` and a `match` beat a `bool is_valid`
sitting beside the data it describes.

## Going deeper

- Exploring several radically different interfaces before committing, and comparing them on
  depth, locality and seam placement: [DESIGN-IT-TWICE.md](DESIGN-IT-TWICE.md).
- Deepening an existing cluster of shallow modules without breaking callers:
  [DEEPENING.md](DEEPENING.md).
- Choosing the construct once the seam is decided — inheritance or composition, Protocol or
  ABC, factory, singleton, registry: [design-patterns](../design-patterns/SKILL.md).
