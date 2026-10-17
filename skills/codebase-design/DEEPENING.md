# Deepening a shallow cluster

A cluster of shallow modules shows up as a group of functions that callers must always use
together, in a fixed order, passing intermediate types between them. The fix is to put a
single interface in front of the cluster, then make the old members private, without breaking
callers on the way.

## Recognising the shape

- Call sites repeat the same sequence of three or more calls.
- Intermediate types (`dict[str, Any]`, `tuple[Frame, Meta]`) appear in public signatures but
  are meaningful only between steps.
- A new caller needs a doc page to know the order.
- Tests of step 3 start by replaying steps 1 and 2.

Any two of those justify deepening.

## Procedure

1. **Name the single thing the cluster achieves.** If no single sentence covers it, the
   cluster is two clusters; deepen each separately.
2. **Write the new interface first**, in the contract. Usually one function or one class with
   two or three methods.
3. **Add it alongside** the existing functions, implemented by calling them. No behaviour
   change in this step, so the existing tests still pass unmodified.
4. **Migrate callers** one at a time. Each migration should delete lines at the call site; if
   it does not, the new interface is not deeper, and step 2 was wrong.
5. **Move the old members into a private subfolder** once no external caller remains. The
   entry-point boundary now enforces what the review would otherwise have to.
6. **Replace, do not layer, the tests.** Tests that exercised the old members through their
   own seams get rewritten against the new interface and deleted. Keeping both leaves you
   with a public test surface for a private implementation, which re-freezes exactly the
   shape you removed.

## Dependency categories

Classify each thing the cluster depends on before choosing the seam; the category decides
whether it belongs behind the interface or in front of it.

| Category | Examples | Where it goes |
| --- | --- | --- |
| **Pure computation** | maths, parsing, geometry | behind the interface, always |
| **Ambient I/O** | clock, filesystem, env vars, RNG | behind a parameter with a default, so tests pass a fake without patching |
| **Remote or slow** | network, GPU, database | at a seam, as an adapter: this is where the second implementation actually exists |
| **Caller policy** | thresholds, retry counts, output paths | in front: a frozen config the caller supplies |

Misclassifying caller policy as pure computation is the usual error; it is how thresholds end
up as module-level constants that nobody can override.

## Seam discipline

- A seam exists where something varies **today**, in production or in a test that cannot run
  otherwise. Not where something might vary.
- One seam per axis of variation. Two `Protocol`s whose implementations always change together
  are one seam wearing two hats.
- Put the seam at the widest point the variation covers. A seam under every function in the
  cluster recreates the shallow cluster behind an interface.

## Stopping condition

Stop when the deletion test passes: deleting the new module would push its complexity back
into two or more callers. If deleting it would simply inline one call, it is a pass-through —
remove it and leave the cluster alone.
