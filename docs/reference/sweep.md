# Sweep

`scripts/sweep.py`, run by `/lld-seed:sweep` and `/lld-seed:propose`. Reads every `.py`
file under a root, finds where execution begins, builds a function-level call graph, and
reports what each entry point reaches and which code is written twice.

**Prevents:** a verdict on a repository from a number with no list behind it.

**When.** First contact with a repository you did not design, and before
`/lld-seed:propose`. Not for gating: the sweep decides nothing and exits 0 whatever it finds.

Everything above [Direction](#direction-not-implemented) ships in 0.7.0. Everything in it is
planned and does not exist in `scripts/`.

```
python scripts/sweep.py <root>           # human report; root defaults to the current directory
python scripts/sweep.py <root> --json    # machine-readable
```

Skipped directories: `.git`, `.venv`, `venv`, `__pycache__`, `node_modules`, `.tox`,
`build`, `dist`, `.mypy_cache`; and `setup.py`. Exit 2 when the root is not a directory or
holds no Python.

## Entry points

Found by lookup table, not inference, and each carries the pattern that found it:

| Kind | Pattern |
| --- | --- |
| `main-guard` | a module-level `if __name__ ...` comparison |
| `served-app` | a module-level `app = FastAPI()` (or `Flask`, `Starlette`, `FastMCP`, `Celery`, `Typer`, `Quart`, `Litestar`, `Sanic`), or any call assigned to `app` / `application` |
| `console-script` | a target in `[project.scripts]` of `pyproject.toml` |
| `framework-decorator` | a function decorated `route`, `get`, `post`, `put`, `delete`, `patch`, `command`, `group`, `task`, `callback`, `app`, `on_event`, `websocket`, `tool`, `resource`, `prompt` |
| `tool-invoked` | `upgrade` / `downgrade` under a `migrations`, `versions` or `alembic` directory |
| `test` | `test_*` functions and pytest fixtures; walked separately |

A repository with no runtime entry is classified `library`, and the report says that "dead"
is not a meaningful answer there. One with more than ten exported names per runtime entry is
`mixed`; otherwise `application`.

## The call graph

Edges come from bare names, imported names, constructors (`Foo()` reaches `Foo.__init__`),
functions handed around as values (`command=self._send`, `{"process": jobs.process}`,
dispatch tables), and a module's import-time body. A call whose receiver was imported from
a module the sweep did not parse (the standard library, a dependency, anything outside the
root) is not an edge; no manifest is read, whatever `core/callgraph.py`'s docstring says.
Annotations are not edges. A method call on an untyped receiver resolves to every
definition with that name, which over-reports. `unresolved call sites` counts the calls
whose target could not be named at all (`getattr(obj, name)()` and the like).

## The sets

| Set | Means |
| --- | --- |
| `core` | reached from every runtime entry |
| `feature_local[e]` | reached only from entry `e` |
| `shared` | reached from some entries, not all (count in the report; not in `--json`) |
| `dead` | reached from no runtime entry **and** no test |

**The text report prints counts only.** The lists - which names are `dead`, `core`, or local
to each entry - are in `--json`. Read those before quoting a number. The JSON carries
`kind`, `definitions`, `unresolved`, `core`, `dead`, `feature_local`, `overlap` and
`duplication_rate`; it does not carry `shared` or the clone groups, which appear only in
the text report (top ten).

**Overlap** is the Jaccard index between each pair of entries' reach sets: `1.0` means one
tangle with two doors.

## Clones

`core/clones.py` hashes each function and class body after erasing every name, attribute
and literal value (literal *types* are kept). Two bodies with the same hash are reported as
one shape. That is Type-1/2 detection; near-miss and semantically equal code are not found.

- Only functions and classes with **five or more statements, counting the `def` itself**
  are hashed. A one-line helper is two statements and is never reported.
- A class that only declares fields is never a clone.
- `duplication_rate` is `1 - distinct shapes / hashed fragments`: the share of hashed
  definitions that are a repeat of another. In a repository whose only hashed functions are
  two copies of one, it is 50%, not 100%. The command file's "share of definitions in clone
  groups" describes a different number.

Each clone in the report carries a verdict from reachability: `across features`,
`within one feature`, or `one copy is unreachable`.

## Example

A three-file repository built to reproduce two failures measured on 2026-10-24. Create it
and run the sweep yourself:

```python
# app.py
import lib

if __name__ == "__main__":
    lib.run()
```

```python
# lib.py
import math


def to_rad(deg):
    return deg * math.pi / 180


def summarise(values):
    total = 0
    for v in values:
        total += v
    mean = total / len(values)
    return mean


def run():
    print(summarise([to_rad(1), to_rad(2)]))
```

```python
# make_plots.py - a script, run as `python make_plots.py`, with no main guard
import math


def to_rad(deg):
    return deg * math.pi / 180


def stats(values):
    total = 0
    for v in values:
        total += v
    mean = total / len(values)
    return mean


def plot(xs):
    return stats([to_rad(x) for x in xs])


plot([1, 2, 3])
```

`python scripts/sweep.py .` (0.7.0):

```
repository kind: application
definitions: 6   entry points: 1   unresolved call sites: 0

  core               3  reachable from every entry
  shared             0  reachable from some
  dead               3  reachable from nothing
  dead fraction   50.0%

feature-local (reachable from one entry only):
     3  app.__main__

duplication rate 50.0%  (1 repeated shapes):
    6 stmts  one copy is unreachable   lib.summarise, make_plots.stats
```

`--json` names the three: `"dead": ["make_plots.plot", "make_plots.stats", "make_plots.to_rad"]`.

Both headline numbers are wrong, in the two ways the real sweeps were wrong:

- **`dead 50.0%` is false.** `make_plots.py` runs every time someone types
  `python make_plots.py`. It has no main guard, so it is not an entry point, and everything
  only it reaches reads as dead - including the module-level `plot(...)` call that proves it
  runs.
- **The copied `to_rad` is missing.** It is two statements, below the threshold. The rename
  of `summarise` to `stats` was found because names are erased. The clone's verdict, "one
  copy is unreachable", inherits the first error and suggests deleting a copy that runs.

On 2026-10-24 the same shapes, at scale:

- **openarm_control** reported 21.6% dead. Most of it was `make_gif.py`, `make_plots.py` and
  six tactile scripts, none with a main guard.
- **manipulation_vision** had six one-line helpers copied verbatim across four files. None
  was reported.

## Before a verdict

The command file lists the checks; in short:

1. **Confirm the entry points.** List every file a person runs directly. Any without a main
   guard: treat what it reaches as live.
2. **Library?** `kind: library` means the dead set is the public API.
3. **Framework dispatch** (`HTMLParser.handle_*`, pydantic validators, dunders,
   `__post_init__`, Qt slots) is invisible. Read the dead list grouped by class.
4. **Deliberate copies** (snapshots, vendored scripts, files saying they are copies) are not
   clones. Open the top groups.
5. **Tests inflate duplication.** A suite that should be parametrised shows as many clones.
6. **Monorepos overlap at 1.00.** That is an artifact there.
7. **Small helpers.** Grep for short functions repeated across sibling files; the hash will
   not show them.

Report what survives with a file and line for each item.

## Direction (not implemented)

None of this exists in `scripts/` yet. It is where the diagnose side is meant to go, from
the 2026-10-24 sweeps.

- **Concentration as the headline.** Module-size inequality, fan-in inequality, and how far
  the directory tree disagrees with the import graph, instead of dead% and duplication%.
- **Named findings, not percentages.** Each one checkable by opening two files.
- **No dead figure until entry points are confirmed.** The report should list the entry
  points it found and the scripts it could not classify, and withhold the dead number until
  someone confirms them.
- **A plugin directory is a declared boundary.** Code loaded by a host is not dead.
- **"Shape collision", not "clone".** The detector erases identifiers; a collision of shapes
  is what it measures.
- **Small helpers.** The five-statement floor misses verbatim one-line copies. Whether to
  lower it, or hash verbatim text separately, is undecided.
