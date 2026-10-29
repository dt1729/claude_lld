# Enforcement templates

`templates/enforcement/` holds the tool configuration for a repository governed by
`lld-seed`. Each tool owns the rules it can decide, so no skill restates them.

**Prevents:** prose rules that a linter could have enforced, and claims about complexity
limits with no configuration behind them (there were none before 0.5.0).

| File | Owns |
| --- | --- |
| `ruff.toml` | formatting, imports, naming, complexity (`C901` at 10), argument, branch, statement and return counts (6, 12, 50, 8), blind excepts, boolean positional arguments, annotations |
| `mypy.ini` | `strict`, `warn_unreachable`; tests relaxed on untyped defs |
| `.importlinter` | no cycles between features, layer direction, subfolders private to their package (rule 16) |
| `.pre-commit-config.yaml` | runs ruff, ruff-format, the standard hygiene hooks, mypy, pytest, and two `lld` detectors |

The mapping from each concern to its rule code is in
[skills/python-style/SKILL.md](../../skills/python-style/SKILL.md#what-is-enforced-mechanically).

## Install

```bash
cp templates/enforcement/{ruff.toml,mypy.ini,.importlinter,.pre-commit-config.yaml} <repo>/
pip install pre-commit ruff mypy import-linter pytest
cd <repo> && pre-commit install
```

## Edit before the first commit

The template README says three of the four files work unmodified. Only `ruff.toml` and
`mypy.ini` do. Two need editing:

**`.importlinter`.** Replace every `<pkg>`, `<feature_a>`, `<feature_b>` and
`<other_feature>` with real package names, and list one `forbidden` contract per pair of
packages whose internals must stay private.

**`.pre-commit-config.yaml`.** The local hooks were copied from this plugin's own config and
point at paths that exist only here:

| Hook | As shipped | Change to |
| --- | --- | --- |
| `mypy` | `args: [scripts]` | your package directory, e.g. `[src]` |
| `pytest` | `python -m pytest scripts/tests -q` | your test command |
| `lld-contract-conformance` | `python scripts/detect_gaps.py` | `python <plugin>/scripts/detect_gaps.py`. Despite its name it runs rule 35, not rule 37 |
| `lld-anti-patterns` | `python scripts/detect_patterns.py`, excluding `^scripts/tests/` | `python <plugin>/scripts/detect_patterns.py`, excluding your tests |

`<plugin>` is wherever the plugin's `scripts/` directory lives: a clone of this repository,
or the plugin install directory.

The template has no test-quality hook. This repository's own config runs one; copy it if you
want rules 27-36 at commit time and not only through the gate:

```yaml
      - id: lld-test-quality
        name: lld test quality
        entry: python <plugin>/scripts/detect_tests.py
        language: system
        files: (^|/)tests?/.*\.py$|(^|/)test_.*\.py$
```

Neither config runs `derive.py --check` or `conditions.py --check`. Run them in CI, per
module with a contract.

## Thresholds

Change a number only with a reason recorded in `docs/incidents.md`. Every threshold started
as a guess, and the first one measured against real code was wrong (incident 001).
