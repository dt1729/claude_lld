# Modularization

Rules for where a module ends. Cycles and entry-point violations are enforced by
import-linter and absent here; what follows is what the tool cannot decide.

## Public is positional: root modules out, subfolders in

A package's public surface is the modules at its root. Anything in a subfolder is private,
whatever it is called. Depth, not designation: no naming convention to remember, and the
rule is checkable by a path.

```
detection/
  pipeline.py        # public
  calibration.py     # public
  lib/nms.py         # private: other packages may not import detection.lib.nms
  tests/
```

## Keep `__init__.py` empty

A barrel that re-exports the package makes every internal move a public change, and hides
which module a name really lives in.

```python
# good: callers import the module that owns the name
from detection.pipeline import run

# bad: detection/__init__.py re-exporting everything
from detection import run
```

## Split on reasons to change, not on length

Line count is a symptom with many causes; two reasons to change is the actual defect, because
each change risks the other behaviour.

> A 400-line module that changes only when the camera protocol changes is healthy.
> A 60-line module that changes when the protocol changes *and* when the report format
> changes is two modules.

## Keep computation pure and push I/O to the edge

A pure core is testable without fixtures and reusable in contexts the I/O does not suit.

```python
# good
def select_targets(dets: Sequence[Detection], cfg: Policy) -> list[Target]: ...
def run(path: Path, cfg: Policy) -> None:
    write(select_targets(read(path), cfg))

# bad: the rule is unreachable without a file on disk
def select_targets(path: Path, cfg: Policy) -> list[Target]:
    dets = json.loads(path.read_text())
```

## Do no work at import time

Import-time work makes collection order significant and failures appear as import errors far
from their cause.

```python
# good
def get_model(cfg: Settings) -> Model:
    return _load(cfg.model_path)

# bad
MODEL = _load(os.environ["MODEL_PATH"])   # fails at import, in every test session
```

## Declare a module's allowed imports where the module lives

An allowance recorded next to the code is read by whoever edits it; one recorded centrally is
read by nobody. The per-folder `CLAUDE.md` carries this list, and import-linter enforces it.

## Apply the deletion test before adding a module

A module that only forwards calls adds a name, a file and an indirection, and hides nothing.

```python
# bad: delete this and nothing reappears anywhere
def get_user_by_id(uid: str) -> User:
    return repo.get_user_by_id(uid)
```

## Depend on the narrower side

When two modules must know each other, the dependency points at the one with fewer reasons
to change; the volatile side imports the stable side.

```python
# good: policy (volatile) imports geometry (stable)
# bad:  geometry imports policy to special-case one caller
```
