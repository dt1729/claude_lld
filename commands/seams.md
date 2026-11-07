---
description: Every seam in a repository and the adapters behind it, in Python, C and C++, with the cells a seam matrix would owe
argument-hint: "<repo root>"
---

Survey `$1` and read the lists before saying anything about the numbers.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/seams.py" $1            # human report
python "${CLAUDE_PLUGIN_ROOT}/scripts/seams.py" $1 --json     # seams / implementers / unavailable
python "${CLAUDE_PLUGIN_ROOT}/scripts/seams.py" $1 --min 2    # only seams with two or more adapters
```

## What is found

A seam is a declared interface: a `Protocol` or ABC in Python, a class with a pure virtual
method in C++, a struct of function pointers in C. An adapter is matched one of three ways:

| How | Means |
| --- | --- |
| `inherits` | names the seam in its bases (`class Ompl(Planner)`, `class Ompl : public Planner`) |
| `structural` | defines every method of a Python `Protocol` with the same arity |
| `table` | a C variable of the struct type with an initializer (`static const struct ops usb_ops = {...}`) |

`cells` is parameters times adapters: the number of claims a seam matrix would have to make,
one per adapter per parameter, that the adapter honours that parameter in its backend's
terms. The finder counts cells; it does not judge them.

## Before a verdict

- **One adapter is a hypothetical seam (rule 11).** A `Protocol` with a single implementation
  is an abstraction nobody has needed yet. Say so, with the file and line.
- **A test fake is an adapter.** `tests/fake_planner.py` satisfying the seam structurally is
  a legitimate second implementation; that is what the seam is for.
- **Bases match by simple name.** Two seams called `Handler` in different packages share
  their adapters. Check the paths before counting.
- **Structural matching is refused for one parameterless method.** `Closable.close()` would
  match half a codebase. Those seams list only explicit inheritors.
- **`ABC.register`, concepts, template duck typing and per-platform factories are
  invisible.** The count under-reports there.
- **`not analysed` is a failure, not a zero.** C and C++ need tree-sitter
  (`pip install tree-sitter tree-sitter-c tree-sitter-cpp`). When it is missing the report
  says so and the exit status is 1. Never report "no seams" for a language that was not read.

Report what survived that reading, with the file and line for each item. A count with no
list behind it is not a finding.
