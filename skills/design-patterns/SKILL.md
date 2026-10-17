---
name: design-patterns
description: Decide which Python construct to use - inheritance or composition, Protocol or ABC, factory or constructor, singleton or injected instance, class or function. Use when introducing a class, adding a base class, writing a factory, sharing one instance across a program, choosing an extension mechanism, or reviewing code for pattern misuse.
---

# Design patterns

A pattern is not good or bad in itself. It is good or bad **for a particular reader of the
code**, and the readers disagree. A singleton the operator wants is the same object the
library user cannot work around. Decide by naming the perspective that governs, not by
recalling whether the pattern is fashionable.

## The decision procedure

1. **Name who the code is for.** Five perspectives, defined in
   [PERSPECTIVES.md](PERSPECTIVES.md): library user, library builder, operator, developer,
   end user.
2. **Find the entry in [CATALOGUE.md](CATALOGUE.md)** for the construct you are reaching for.
   Each entry gives a verdict per perspective, not a single recommendation.
3. **Apply the precedence rule** below when the verdicts conflict.
4. **Record the decision in the contract's Seam section**, with the perspective that governed.
   A pattern choice without a named perspective is a preference, and preferences get
   overturned by the next person with a different one.

## Precedence when perspectives conflict

| The code is | Governing perspective | Because |
| --- | --- | --- |
| Exported from the package (a root module) | **Library user** | They cannot work around your choice; you can |
| At the composition root (`main`, CLI, service entry) | **Operator** | Process-level resources are theirs to own |
| Inside a package subfolder | **Developer** | No external contract is at stake |
| Anything that forecloses a future change | **Library builder vetoes** | A veto, not a preference: convenience now loses to a door left open |

The library builder's veto is the rule people skip. Ask: *if this turns out wrong in six
months, is the fix a rename or a breaking change for every caller?* A choice that can only be
undone by breaking callers needs a stronger reason than "it was simpler today".

## Fast answers

These are the cases that recur. Full reasoning in the linked files.

| Reaching for | Use instead, unless | See |
| --- | --- | --- |
| Inheriting to reuse code | the base is an abstract type you own and the subclass *is* one | [INHERITANCE.md](INHERITANCE.md) |
| `Foo.instance()` / module global | the instance is built once at the composition root and injected | [CATALOGUE.md](CATALOGUE.md#singleton) |
| A class with `__init__` and one method | it is a function | [CATALOGUE.md](CATALOGUE.md#class-vs-function) |
| A factory that calls a constructor | construction needs a decision the caller should not make | [CATALOGUE.md](CATALOGUE.md#factory) |
| An ABC so callers can subclass | the implementer should not have to import you: use `Protocol` | [INHERITANCE.md](INHERITANCE.md) |
| A `mode: str` parameter and a branch | pass the behaviour in | [CATALOGUE.md](CATALOGUE.md#strategy) |
| A base class to share two helper methods | a module of functions | [ANTI-PATTERNS.md](ANTI-PATTERNS.md) |

Constructs that are forbidden outright, and how they are detected, are in
[ANTI-PATTERNS.md](ANTI-PATTERNS.md). Those are the entries the contract gate enforces
mechanically; everything else on this page is judgment the gate records rather than decides.
