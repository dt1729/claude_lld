# Enforcement templates

Copy these into a repo governed by `lld-seed`. They own every rule a tool can decide, so the
markdown never restates one; `skills/python-style/SKILL.md` maps concerns to the codes here.

| File | Owns |
| --- | --- |
| `ruff.toml` | Formatting, imports, naming, complexity, argument and branch counts, blind excepts, boolean positional arguments |
| `mypy.ini` | Annotations, optionality, exhaustiveness |
| `.importlinter` | Dependency direction, cycles, the entry-point boundary |
| `.pre-commit-config.yaml` | Runs all of the above, plus the anti-pattern detector, before a commit exists |

## Install

```bash
cp ruff.toml mypy.ini .importlinter .pre-commit-config.yaml <repo>/
pip install pre-commit ruff mypy import-linter pytest
pre-commit install
```

Then fill the `<pkg>` placeholders in `.importlinter` with your real package names. The other
three work unmodified; adjust `per-file-ignores` paths in `ruff.toml` if your tests do not
live under `**/tests/**`.

## Tuning

Change a threshold only with a reason recorded in `docs/incidents.md`. Every number in
`ruff.toml` started as a guess, and the first one measured against real code turned out to be
wrong — see incident 001.
