# The five perspectives

Every design choice is evaluated by someone. These five want different things, and most bad
pattern arguments are two people reasoning from different seats without saying so. Name the
seat first; the answer usually follows.

## Library user

*Imports your package and calls it. Cannot edit it.*

Asks: Can I construct two of these? Can I run your code in a test without your globals
leaking between cases? Can I substitute my own implementation at the point where I need to?
Will this still work when I upgrade?

Hostile to them: module-level state, `Foo.instance()`, import-time side effects, reading
`os.environ` deep in a call stack, anything that assumes one process holds one configuration.
Each of these is a decision taken away from someone who cannot take it back.

Governs: anything exported from a package root module.

## Library builder

*Maintains the package. Must keep callers working while changing internals.*

Asks: What have I promised? How much of this can I change next month without a major
version? If this abstraction is wrong, what does fixing it cost?

Hostile to them: wide public surfaces, concrete classes that callers subclass, re-exporting
internals through `__init__.py`, returning mutable internal structures. Every one converts an
implementation detail into a promise.

Holds a **veto**, not a preference. A choice that is convenient today and can only be undone
by breaking callers loses to one that keeps the door open — unless the cost of the open door
is paid every day, in which case say so explicitly in the contract.

## Operator

*Runs the program in production. Does not read the source.*

Asks: How is it configured, and can I see the configuration in one place? What happens on
restart? Does it hold one connection pool or four hundred? When it fails, does the log tell
me which input caused it? Can I change a threshold without a deploy?

Wants: exactly one of each expensive resource, explicit lifecycle (start, drain, stop),
configuration resolved once at startup and logged, failures that name the resource and the
input. Genuinely wants shared instances — which is why the singleton argument never dies.

Governs: the composition root and process-level resources.

## Developer

*Works in the codebase. Reads it far more than they write it.*

Asks: Where does this behaviour live? What breaks if I change it? Can I test it without
standing up the world? How many files must I read to understand one request?

Hostile to them: inheritance chains, indirection without variation, patterns applied for
their own sake, anything that requires knowing where a behaviour was mixed in from.

Governs: code inside a package subfolder, where no external contract is at stake.

## End user

*Uses the running system. Never sees the code.*

Asks nothing about structure, and this is the point: almost no pattern choice reaches them.
Where it does, it reaches them as an error message, a latency, or a failure mode.

Use this seat for one thing only: the **error taxonomy**. An exception type exists so somebody
can respond differently to it. If no end-user-visible response differs, the distinction is
decoration. Conversely, a failure they must act on differently needs a type of its own, even
if the implementation is identical.

## Worked conflicts

**A connection pool.** Operator wants one per process. Library user wants to construct two
(one per tenant, or one per test). Resolution: *the instance is shared, the type is not.*
Build one at the composition root and inject it. Both get what they need; neither gets a
module global.

**A plugin registry populated by decorators at import time.** Library builder likes it:
adding a backend touches no shared file. Developer hates it: behaviour depends on which
modules were imported, and "find all implementations" stops working. Library user is harmed
if import order changes behaviour. Resolution: explicit registration at the composition root
where the set is small and known; decorator registration only when third parties genuinely
add backends you cannot enumerate.

**A `Config` object with mutable fields.** Operator wants to change a threshold at runtime.
Library user needs reproducibility and thread safety. Resolution: frozen config plus an
explicit reload that builds a new one, rather than mutation in place. The operator's need was
*change the value*, not *mutate the object* — and those are different requirements once named.
