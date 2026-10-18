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
| 19 | `print` in a package module | AST |
| 20 | Logging configured outside the composition root | AST |
| 21 | Eager f-string formatting in a log call | AST |
| 22 | Logger named by a string literal | AST |
| 23 | Exception logged without its traceback | AST |
| 24 | Exception caught, logged, and swallowed | AST->judge |
| 25 | Log line with no subject | judge |
| 26 | Secret or payload in a log line | judge |
| 27 | Test that asserts nothing | AST |
| 28 | Suite with no failure case | AST->judge |
| 29 | Assertion on a substring too short to be wrong | AST->judge |
| 30 | `sleep` in a test | AST |
| 31 | Test importing past the entry-point boundary | AST |
| 32 | More mocks than assertions | AST->judge |
| 33 | Asserting that a call happened, not that behaviour is right | AST->judge |
| 35 | Public name with no test referencing it | judge |
| 36 | Test name joining two things with "and" | AST->judge |

Rules 27 to 36 are decided by `scripts/detect_tests.py`, which reads the test files the
structure detector excludes. Rule 34 (one test covering several behaviours) was specified,
implemented, and removed: counting assertion subjects flagged 32 sound tests in this repo and
no unsound ones. It is reviewed, not detected - see incident 005.

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

**Detect:** `os.environ` or `os.getenv` in a module that is not the composition root. A
module counts as the composition root when it is named for the job (`main.py`, `cli.py`,
`__main__.py`, `settings.py`, `config.py`, a logging-config module) **or** carries an
`if __name__ == "__main__"` guard: a module that is executable is an entry point whatever
it is called.
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

## 19. `print` in a package module

Output that cannot be routed, filtered, levelled or turned off, and that corrupts any stdout
protocol the process participates in.

**Detect:** a call to `print` in a module under the package root.
**Fix:** `log = logging.getLogger(__name__)` and a level chosen from
[logging/LEVELS.md](../logging/LEVELS.md). A CLI writing its actual output to stdout is the
exception, and belongs in the composition root.

## 20. Logging configured outside the composition root

`basicConfig`, `setLevel`, `addHandler` or a formatter inside a library module takes a
decision from the application that cannot be taken back, exactly like reading the
environment below the root.

**Detect:** `basicConfig`, `setLevel`, `addHandler`, `removeHandler` or `setFormatter` in a
module that is not a declared composition root.
**Fix:** emit through `getLogger(__name__)` and let the application configure. See
[logging/SKILL.md](../logging/SKILL.md#libraries-log-applications-configure).

## 21. Eager f-string formatting in a log call

The message is built whether or not the level is enabled, and every line becomes a unique
string, which destroys the grouping key aggregators use to collapse repeats into one event.

**Detect:** an f-string, `.format()` call, or `%` expression as the first argument to a
logger method.
**Fix:** pass the format string and arguments separately: `log.info("loaded %s", name)`.

## 22. Logger named by a string literal

A hardcoded name decouples the logger from its module, so per-module level configuration
stops working and two modules can silently share one logger.

**Detect:** `getLogger("literal")` where the argument is not `__name__`.
**Fix:** `getLogger(__name__)`. A deliberate logger tree root — `getLogger("lld")` in an
application's own setup — belongs in the composition root.

## 23. Exception logged without its traceback

`log.error(str(exc))` discards the part that locates the fault, leaving the reader a message
with no frame to look at.

**Detect:** a `log.error` / `log.critical` call inside an `except` handler, with no
`exc_info` keyword and not `log.exception`.
**Fix:** `log.exception(...)` inside the handler, or `exc_info=True`.

## 24. Exception caught, logged, and swallowed

The caller is told the operation succeeded while the log says otherwise. The failure then
surfaces later, somewhere unrelated, as missing data.

**Detect:** an `except` handler whose body is only a logging call, with no `raise`, `return`
or other recovery.
**Judge:** legitimate at a top-level boundary that must not crash — a request handler, a
worker loop — where continuing is the deliberate policy.
**Fix:** recover explicitly and say so, or re-raise and let the caller decide.

## 25. Log line with no subject

A line naming an event but not what it happened to is unusable the one time it matters,
because the reader cannot tell which request, device or file it refers to.

**Judge:** no reliable signature. Reviewed against what an operator would grep for.

## 26. Secret or payload in a log line

Credentials, tokens, keys, personal data, or a whole request body that may contain them.
Logs are copied to places the data was never cleared for, and are the hardest store to
redact afterwards.

**Judge:** a name-based signature (token, password, secret, key) catches the obvious cases
and misses the ones that matter, so this is reviewed rather than detected. Log an
identifier, never the payload.

## 27. Test that asserts nothing

A test with no `assert` and no `pytest.raises` passes whatever the code does. It raises the
count and lowers the meaning.

**Detect:** a `test_*` function with no assert, no raises, and no call to a `check_` /
`verify_` / `assert_` helper that would carry the assertion.
**Fix:** assert the behaviour, or delete the test.

## 28. Suite with no failure case

A suite of only happy paths has probably never seen the code fail, and a test that has never
failed has not been shown to test anything.

**Detect:** five or more tests in one module, none of which raises or is named for a failure.
**Judge:** whether a module has a failure worth testing is a fact about the module, which a
file-local detector cannot see. A pure function legitimately has none.
**Fix:** add the error or boundary the module is supposed to handle.

## 29. Assertion on a substring too short to be wrong

`assert "1" in str(exc)` passes against any message containing a 1, including the wrong one.

**Detect:** an `in` comparison whose left side is a string literal shorter than four
characters, inside a test.
**Judge:** a short literal is occasionally the whole point, such as a status code.
**Fix:** assert the whole message, or give the exception a field and assert on that.

## 30. `sleep` in a test

A sleeping test is a flaky test with a timer attached: it is slow when it passes and
misleading when it fails.

**Detect:** a call to `sleep` anywhere in a test module.
**Fix:** wait on the condition, or inject the clock so the test controls time.

## 31. Test importing past the entry-point boundary

Tests and callers cross the same seam. A test reaching into a private subpackage tests
something no caller can reach, and freezes an implementation detail.

**Detect:** an absolute `from pkg.lib...` / `.internal` / `.impl` import in a test module.
**Fix:** import the root module that owns the public name. If the behaviour is unreachable
from there, the module is the wrong shape.

## 32. More mocks than assertions

When the mocks outnumber the assertions, the subject under test is the mock.

**Detect:** more `Mock` / `patch` constructions than `assert` statements in one test.
**Judge:** legitimate when the collaborators are genuinely remote or slow.
**Fix:** a real collaborator, or one fake that satisfies the seam.

## 33. Asserting that a call happened, not that behaviour is right

`store.save.assert_called_once()` tests the implementation. It keeps passing after the
implementation stops working, and fails after a harmless refactor.

**Detect:** a call to `assert_called*` / `assert_any_call` / `assert_has_calls` in a test.
**Judge:** legitimate when the call *is* the behaviour, such as an audit log.
**Fix:** assert the result, or the observable effect on a fake.

## 35. Public name with no test referencing it

**Judge:** needs the module-to-test mapping, which the detector does not build. Reviewed
against the contract's Tests section, which lists the behaviours that should exist.

## 36. Test name joining two things with "and"

A test named for two behaviours fails for two reasons, so its name stops identifying what
broke.

**Detect:** `_and_` in a test function name.
**Judge:** the name may describe one thing that happens to contain "and", as in
`test_class_with_init_and_one_method`. The detector cannot tell those apart, which is why
this is not a block.
**Fix:** split it, so the name of a failure is the behaviour that broke.
