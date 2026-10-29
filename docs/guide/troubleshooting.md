# Troubleshooting

## The gate never refuses anything

Check in this order:

1. **Restarted since installing?** Plugin hooks do not run in the session that installed
   them.
2. **Is the file under a `src` path segment?** Nothing else is gated except test files.
   `lib/pkg/mod.py` and a flat `pkg/mod.py` are out of scope.
3. **Is the path excluded?** `__init__.py`, `conftest.py`, `setup.py`, and anything under a
   `tests`, `test`, `scripts`, `migrations`, `_generated` or `generated` segment.
4. **Is `LLD_GATE=off` in the environment** of the process that started Claude Code?
5. **Does `.lld/gate.log` exist?** No log at all means the hook is not running. The command
   is `python ...`; if only `python3` is on your `PATH`, it cannot start.
6. **Does the file parse?** The gate allows content that is not valid Python.

## The gate refused an edit to a file I did not design

The whole resulting file is checked, not the lines you changed. A `block` finding anywhere
in the file refuses the edit. Run
`python <plugin>/scripts/detect_patterns.py <file>` to see all of them, then fix the
blocking ones or finish the session with `LLD_GATE=off claude` while you migrate.

## A judgment finding keeps coming back

Add a row to `docs/contracts/_waivers.md`:

```markdown
| src/pkg/thing.py | 8 | 2026-10-29 | the instance is the seam tests substitute |
```

The path must match what the gate printed exactly, relative to the project root. The rule is
a bare number. Waivers never clear a `block` finding.

## Rule 37 refuses a new module whose contract validated

The contract's Interface block promises a name the write does not define, or a parameter
list that differs. Write every promised public name in the first write. A class constructor
is compared against `__init__`, or the annotated fields of a dataclass.

## Rule 37 calls a public name undocumented

It is public and the contract does not mention it. Add it to the Interface block, make it
private, or waive rule 37 for the module.

## Rule 38 refuses an edit that changes the interface

Once a contract has `<!-- derived -->` blocks, the gate regenerates them from the content you
are about to write and compares. Adding a public name, an import or a raise makes them
differ. `derive` cannot help yet: it reads the file on disk, which the refused write has not
changed. This is a limitation of 0.7.0, not a misuse.

Two ways through, neither good:

- Edit the derived block in the contract to what the new code will produce, repeat the write,
  then run `derive.py <module> --check` to confirm it matches.
- Make the change in a session started with `LLD_GATE=off`, then run `/lld-seed:derive` and
  restart with the gate on.

Finishing the interface before the first derive avoids most of this.

## derive left my hand-written sections in place

By design: the first run inserts each block at the top of its section and touches nothing
outside the markers. Delete the hand-written signatures, `May import` line and errors table
beneath the blocks; keep the prose that says what the derived facts mean.

## A script says `no contract at docs/contracts/...`

Scripts resolve the contract from the current directory. Run them from the project root, and
pass `--src-root` if your packages are not under `src/`.

## The sandbox cannot import the module

`ModuleNotFoundError` from `python src/pkg/tests/sandbox_mod.py` means the package is not on
the import path. Run it as a module from the directory that holds the package:
`cd src && python -m pkg.tests.sandbox_mod`, or install the package.

## `/lld-seed:diagram` exits 3

The `dataviz` skill was not found in `LLD_DATAVIZ`, `~/.claude/skills/dataviz`, or the
bundled skills directory. Point at it: `LLD_DATAVIZ=/path/to/dataviz`. The directory must
contain `references/palette.md`.

## The sweep says most of the repository is dead

Confirm the entry points before believing it. Scripts without an `if __name__ == "__main__"`
guard, code a framework dispatches, a library's public API, and a plugin directory loaded by
a host all read as dead. See [sweep.md](../reference/sweep.md#before-a-verdict).

## The sweep misses an obvious copy

Functions under five statements, counting the `def`, are never hashed. A one-line helper
copied into four files will not appear.

## Debugging the gate

`LLD_LOG_LEVEL=DEBUG` logs the inputs behind each decision to stderr and
`.lld/gate.log`. To replay a decision outside Claude Code, pipe a payload in:

```
echo '{"cwd": "'"$PWD"'", "tool_name": "Write", "tool_input": {"file_path": "'"$PWD"'/src/pkg/new.py", "content": "x = 1\n"}}' \
  | python <plugin>/scripts/require_contract.py
```
