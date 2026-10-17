# Glossary

Use these terms exactly. Consistent language is what makes design reviewable; "component",
"service", "layer" and "API" are banned because each means five things to five readers.

Vocabulary adapted from [mattpocock/skills](https://github.com/mattpocock/skills)
(`codebase-design`), itself drawing on Ousterhout and Feathers. Divergences are noted.

**Module** — anything with an interface and an implementation. Scale-agnostic on purpose: a
function, a class, a `.py` file, or a package. _Avoid_: unit, component, service.

**Interface** — everything a caller must know to use the module correctly. Not just the type
signature: also invariants, ordering constraints, error modes, required configuration, units,
and performance characteristics. _Avoid_: API, signature (both too narrow).

**Implementation** — what is inside the module. Distinct from **adapter**: a module can be a
small adapter with a large implementation (a Postgres repo) or a large adapter with a small
one (an in-memory fake).

**Depth** — leverage at the interface: how much behaviour a caller can exercise per unit of
interface they must learn. **Deep** = much behaviour behind a small interface. **Shallow** =
the interface is nearly as complex as the implementation.

**Seam** (Feathers) — a place where behaviour can be altered without editing in that place;
the *location* where a module's interface lives. Where to put the seam is a separate decision
from what goes behind it. _Avoid_: boundary (overloaded by DDD's bounded context).

**Adapter** — a concrete thing satisfying an interface at a seam. Names a *role*, not a shape.

**Leverage** — what callers get from depth: more capability per unit of interface learned.

**Locality** — what maintainers get from depth: change, bugs and verification concentrate in
one place. Fix once, fixed everywhere.

**Entry point** — in Python, a module at a package's root (`pkg/loader.py`). Public by
position. Everything in a subfolder (`pkg/_internal/`, `pkg/lib/`) is private, regardless of
underscore naming. Depth, not designation.

**Contract** — the written output of design, produced before implementation. Records
responsibility, interface, seam, allowed dependencies, error modes and the test list.
See `skills/new-module/CONTRACT-FORMAT.md`.

## Rejected framings

- **Depth as a ratio of implementation lines to interface lines** (Ousterhout's formulation):
  rewards padding the implementation. Use depth-as-leverage instead.
- **"Interface" as a `typing.Protocol` or a class's public methods**: too narrow. The interface
  includes every fact a caller must know, including the ones types cannot express.
- **"Boundary"**: say **seam** or **interface**.
