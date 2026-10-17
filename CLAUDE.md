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

## Target environment

Claude Code 2.1.268, Python 3.12. Avoid manifest fields newer than 2.1.268, notably
`userConfig.options` (2.1.271+).
