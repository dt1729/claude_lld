# Anti-patterns

Constructs that are wrong often enough that the burden of proof sits on the author. Each
entry names what the gate detects, so the judgment is reproducible rather than a matter of
taste on the day.

**Detection column** says how the contract gate recognises it from the AST of a pending
write. `AST` means mechanically decided and blocked. `AST->judge` means the shape is detected
mechanically and handed to the model with the evidence, because the shape alone is not proof.
`judge` means no reliable signature; it is reviewed, not detected.

| # | Anti-pattern | Detection |
| --- | --- | --- |
| 1 | Global singleton accessor | AST |
| 2 | Module-level mutable state | AST |
| 3 | Import-time side effects | AST |
| 4 | Inheriting from a concrete class you own | AST |
| 5 | Inheritance depth > 1 below your own base | AST |
| 6 | All-abstract ABC | AST |
| 7 | Stateful mixin | AST |
| 8 | Class with `__init__` plus one method | AST->judge |
| 9 | All-staticmethod class | AST |
| 10 | Pass-through factory or wrapper | AST->judge |
| 11 | `Protocol` with a single implementation | AST->judge |
| 12 | Stringly-typed mode parameter | AST->judge |
| 13 | Environment read below the composition root | AST |
| 14 | Mutable value object crossing a seam | AST->judge |
| 15 | Barrel `__init__.py` | AST |
| 16 | Deep import into another package subfolder | AST (import-linter) |
| 17 | Logic inside an adapter | judge |
| 18 | Exception type with no distinct caller response | judge |

---

## 1. Global singleton accessor

A classmethod returning a cached class attribute, a `get_foo()` returning a module global, or
an instance assigned on first use. Removes a decision from every caller permanently and
shares state between tests.

**Detect:** a classmethod returning `cls._instance`, or a module-level name assigned inside a
function through `global`.
**Fix:** construct once at the composition root, inject. See [CATALOGUE.md](CATALOGUE.md#singleton).

## 2. Module-level mutable state

A module-level list, dict, set or counter written at runtime. It is a global with a nicer
name: two configurations cannot coexist, and test order becomes significant.

**Detect:** module-level assignment of a mutable literal or call, where the name is later a
target of mutation or subscript assignment anywhere in the module.
**Fix:** put it on an instance the caller owns. Module-level `Final` constants are fine.

## 3. Import-time side effects

Work performed at module scope: reading a file, loading a model, opening a socket, reading
the environment, constructing a logger with handlers. Failures surface as import errors far
from the cause, and every test session pays the cost.

**Detect:** module-level call that is not a literal, a constant expression, a dataclass field
or a decorator application.
**Fix:** move it into a function the composition root calls.

## 4. Inheriting from a concrete class you own

Code reuse by inheritance couples the subclass to the base internals and inherits a public
surface the subclass did not design and cannot shrink.

**Detect:** a class whose base resolves to a class in this repo that is not `ABC`,
`Protocol`, `Enum` or `Exception` and carries no abstract methods.
**Fix:** hold an instance; expose what you mean to expose.

## 5. Inheritance depth greater than one

A grandchild means the middle class is both a partial implementation and a variation, and
neither is nameable.

**Detect:** a base class in this repo that itself has a base in this repo.
**Fix:** flatten; move shared code into a collaborator.

## 6. All-abstract ABC

An `ABC` whose every method is abstract imposes nominal inheritance and an import dependency,
buying nothing a `Protocol` would not.

**Detect:** a class inheriting `ABC` where every method body is a docstring, `pass` or
ellipsis.
**Fix:** convert to `Protocol`, so implementers need not import you.

## 7. Stateful mixin

A mixin with a constructor or instance attributes creates an initialisation order its users
must know, which is the thing mixins exist to avoid.

**Detect:** a class named `*Mixin`, or used only as a secondary base, that defines `__init__`
or assigns to `self`.
**Fix:** make it a collaborator held as an attribute.

## 8. Class with a constructor and exactly one other method

Usually a function wearing a costume: the constructor arguments are the function arguments,
deferred.

**Detect:** a class with exactly two methods, one being `__init__`, and no class attributes.
**Judge:** legitimate when the instance is a seam (injected and substituted) or holds state
between calls that is not visible in the signature.
**Fix:** a function.

## 9. All-staticmethod class

A module with extra syntax and an import path nobody needs.

**Detect:** a class where every method carries `@staticmethod` and there are no class
attributes.
**Fix:** a module of functions.

## 10. Pass-through factory or wrapper

A function or class that forwards to one call and adds nothing: a name, a file and an
indirection, hiding nothing.

**Detect:** a function whose body is a single return of one call, passing its parameters
through unchanged; or a class every method of which delegates to the same attribute.
**Judge:** legitimate when it exists to satisfy a seam (an adapter), or to narrow a surface
deliberately.
**Fix:** delete it and let callers call the thing.

## 11. Protocol with a single implementation

A hypothetical seam. It costs depth now and is usually wrong about what will vary.

**Detect:** a `Protocol` in this repo with fewer than two structural implementations,
counting test fakes.
**Judge:** a fake in the test suite is the second implementation and makes it legitimate.
**Fix:** use the concrete type until the second implementation exists.

## 12. Stringly-typed mode parameter

A `str` parameter branched on inside accepts values the type system cannot check, and every
new mode edits shared code.

**Detect:** a parameter annotated `str` compared against two or more string literals in the
body.
**Fix:** an `Enum` when the set is closed, a `Callable` when callers may supply their own.

## 13. Environment read below the composition root

An environment read outside `main`, the CLI or a settings loader hides an input in the middle
of the call stack, where no caller can override it and no test can see it.

**Detect:** `os.environ` or `os.getenv` in a module that is not the declared composition root.
**Fix:** read it once into the frozen config; pass the config.

## 14. Mutable value object crossing a seam

A non-frozen dataclass passed between modules makes every holder a potential writer, and the
resulting bug appears far from the write.

**Detect:** a dataclass without `frozen=True` appearing in a public signature of a root
module.
**Judge:** legitimate for an accumulator owned by one module, or where profiling shows the
copy cost matters.
**Fix:** `frozen=True, slots=True`; derive with `replace()`.

## 15. Barrel `__init__.py`

Re-exporting a package's contents makes every internal move a public change and hides which
module owns a name.

**Detect:** an `__init__.py` containing imports or `__all__`.
**Fix:** keep it empty; let callers import the owning module.

## 16. Deep import into another package subfolder

Reaches past the entry-point boundary into code that was never promised to anyone.

**Detect:** import-linter contract violation.
**Fix:** import a root module, or promote what you need to one.

## 17. Logic inside an adapter

An adapter translates. Logic placed there exists once per backend, which is how three
backends acquire three behaviours.

**Judge:** no reliable signature. Reviewed when an adapter grows a branch that is not
translation.

## 18. Exception type with no distinct caller response

An exception exists so somebody can respond differently to it. If every caller catches it the
same way as its sibling, the distinction is decoration. The inverse is also a defect: a
failure callers must handle differently needs its own type even when the implementation is
identical.

**Judge:** no signature. Reviewed against the callers that exist.
