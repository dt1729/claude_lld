---
description: Generate or refresh per-folder CLAUDE.md guidance, idempotently
argument-hint: "[path] (default: whole repo)"
---

Generate or refresh per-folder `CLAUDE.md` guidance for `$1` (default: the whole repository).

Each generated file carries **only what is local to that folder**. Rules live in the plugin
skills and are never copied into a folder file: duplicated rules drift, and once two copies
disagree neither is trusted.

## 1. Choose the folders

Walk the tree from the target path. A folder qualifies when it holds at least two `.py`
files, or holds one and has subpackages.

Skip entirely: `.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.mypy_cache`,
`.ruff_cache`, `.pytest_cache`, `build`, `dist`, `*.egg-info`, `migrations`, and any folder
whose name starts with `_generated`. Skip `tests/` folders: their guidance is the contract of
the package they test.

If the walk finds more than 25 qualifying folders, list them and ask which to generate before
writing anything. A sweep that writes 60 files nobody reads is worse than none.

## 2. Read before writing

For each folder, read enough to describe it accurately. Do not infer a responsibility from
the folder's name.

- Every root module's public names and their signatures.
- Imports, to establish what it actually depends on and what depends on it.
- The contracts in `docs/contracts/` matching those modules, which already state
  responsibility, seam and invariants. Prefer the contract's wording over your own reading
  of the code: the contract records intent, the code records the current attempt.
- The existing `CLAUDE.md`, if any, specifically its `<!-- manual -->` blocks.

## 3. Write the content

Use `templates/FOLDER-CLAUDE.md.template` from the plugin. Fill every placeholder:

- **Responsibility** — one sentence. If it needs "and", say so explicitly in the file: the
  folder is two packages and that is worth recording.
- **Public interface** — the root modules and what each exposes. Not an export list; say what
  a caller gets.
- **May import / Imported by** — from the imports you read, not from what you would prefer.
  Where the real dependencies violate the entry-point boundary, record the violation rather
  than the ideal, and flag it.
- **Local invariants** — the facts types do not carry: ordering, lifecycle, units, ownership,
  thread-safety. These are the reason the file exists; a folder file with no invariants is
  usually a folder file nobody needed.
- **Rules that bite hardest here** — at most three pointers into the plugin skills, chosen
  for this folder. An I/O adapter points at the adapter entry; a pure-computation package
  points at depth and the deletion test.

Target 20 to 40 lines. A folder file longer than that is carrying rules that belong in the
plugin, or a responsibility that belongs in two folders.

## 4. Merge, do not overwrite

Never write the file directly. Write the generated content to a temporary file, then:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/merge_claude_md.py" <folder>/CLAUDE.md --generated <temp>
```

The script carries every `<!-- manual -->` block from the existing file into the new one and
reports `updated` or `unchanged`. It is idempotent: a second run with the same inputs changes
nothing, which is how you can tell the content was derived rather than freshly invented.

## 5. Report

Print one table: folder, action (`created` / `updated` / `unchanged`), and line count. Then
state anything you could not determine — a folder whose responsibility was not inferable, a
dependency that violates the boundary, a package with no contracts. Those are findings, not
noise; they are the reason to run this over a repo you did not write.

Do not report success for a folder you skipped.
