# claude_lld

Development guidance for the `lld-seed` plugin itself. Users of the plugin never read this
file; it is not loaded when the plugin is installed elsewhere.

## What this repo is

A Claude Code plugin that forces low-level design before implementation in Python repos.
Read `SCOPE.md` for the problem and the division of labour, `GLOSSARY.md` for the vocabulary.
The vocabulary is not negotiable mid-sentence: use module, interface, depth, seam, adapter.

## Layout

| Path | Contents |
| --- | --- |
| `.claude-plugin/` | `plugin.json`, `marketplace.json`. Nothing else goes here |
| `skills/<name>/SKILL.md` | One skill per directory, reference files beside it |
| `commands/` | Slash commands |
| `hooks/hooks.json` | Hook wiring; scripts live in `scripts/` |
| `templates/` | Files the generator writes into target repos |
| `docs/assets/` | README banner and demo. `editor.html` holds the demo's design in CSS; regenerate with `scripts/make_banner.py` and `scripts/make_demo.py` |
| `.out-of-scope/` | Rejected ideas with reasoning. Read before proposing a feature |

## House rules

- **The plugin name is `lld-seed`, not `claude-lld`.** Names starting with `claude-` are
  reserved and fail validation. The repo name and the plugin name differ on purpose.
- **Guidance reaches the model only through skills.** A `CLAUDE.md` at a plugin root is not
  loaded as context when the plugin is installed. This file exists for working *on* the repo.
- **Write no rule a tool can enforce.** Before adding prose, check whether ruff, mypy or
  import-linter can decide it. If they can, configure it there and name the code instead.
- **Eliminate no-ops.** Never write an instruction the model already follows by default; it
  spends context and dilutes the rules that do change behaviour.
- **Every rule carries a one-line rationale and a good/bad pair.** A rule without a failure
  it prevents is decoration.
- **Reference files load on demand.** Keep each `SKILL.md` short and route from it. Front-load
  trigger words in the `description`, because the description decides when the skill fires.
- Run `claude plugin validate .` after touching any manifest.

## Git

- **Commit at every completed unit of work, without being asked.** A phase, a skill, a
  reference file, a working script. Do not leave finished work uncommitted waiting for a
  review that may not come for hours.
- One logical change per commit. Adding a skill and fixing a cross-link are two commits.
- Subject line says what changed; body says why, and names what was rejected when the
  choice was contested.
- Work on a branch, not `main`. Merging is the user's call.
- Push only when asked.

## Logging

The rules these scripts follow are the ones the plugin ships in `skills/logging/`. They apply
to this repo too: it is the first place the guidance has to survive contact with real code.

- Scripts log through the `lld` logger tree, configured once in each script's `main`.
  Never configure logging at import.
- **Nothing writes to stdout.** The hook's stdout carries its JSON decision; logs go to
  stderr and to `.lld/gate.log`. There is a test that proves it, and it must stay passing.
- `LLD_LOG_LEVEL` sets the level (default INFO), `LLD_LOG_FILE` redirects the file. Both are
  read in `main`, never deeper, which is the rule the gate itself enforces on other code.
- INFO records one line per decision with the rules that fired and the elapsed time. DEBUG
  adds the inputs behind it. An unknown level degrades to INFO rather than failing.

## Where rules come from

`docs/incidents.md` records every observed failure and what changed because of it. Prefer
adding a rule because something went wrong over adding one because something might. A rule
with no incident behind it is a prediction, and predictions are the first thing to cut when
the corpus needs pruning.

## Target environment

Claude Code 2.1.268, Python 3.12. Avoid manifest fields newer than 2.1.268, notably
`userConfig.options` (2.1.271+).
