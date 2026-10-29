# The gate

A `PreToolUse` hook that refuses implementation writes which skipped the design step, and
test writes that cannot fail.

**Prevents:** a new module that nobody designed, an anti-pattern landing in a package because
nobody was looking, and a test that passes whatever the code does.

## Wiring

`hooks/hooks.json` registers one hook:

| Field | Value |
| --- | --- |
| Event | `PreToolUse` |
| Matcher | `Write\|Edit\|MultiEdit` |
| Command | `python "${CLAUDE_PLUGIN_ROOT}/scripts/require_contract.py"` |
| Timeout | 10 seconds |

The command calls `python`, not `python3`. The script needs Python 3.12 and nothing outside
the standard library.

Hooks from a plugin installed mid-session do not run until Claude Code restarts.

## What it decides

The script reads the hook payload on stdin, works out the file content the call would
produce (applying the `Edit` or `MultiEdit` to the current file), and answers on stdout with
`allow` or `deny`. The decision depends on the path:

| Path | Checked against | Refused when |
| --- | --- | --- |
| A test file anywhere: `test_*.py`, `*_test.py`, or a `tests/` segment | test rules 27-33, 36 | any `block` finding |
| A **new** `.py` under a `src` path segment | the contract | no contract, or it does not validate |
| Any `.py` under a `src` segment, new or existing | rules 1-10, 12-15, 19-24; 37 and 38 if a contract exists | any `block` finding, or a `judge` finding with no waiver |
| Anything else | nothing | never |

Out of scope even under `src/`: `__init__.py`, `conftest.py`, `setup.py`, and any path with
a `tests`, `test`, `scripts`, `migrations`, `_generated` or `generated` segment.
`__init__.py` is excluded from the gate, though rule 15 (barrel `__init__.py`) still fires
when `detect_patterns.py` is run on it directly.

Three consequences:

- **Only a new file needs a contract.** An existing module with no contract can be edited;
  it is checked against the anti-pattern rules only.
- **The whole resulting file is checked, not the diff.** An edit to one line of a legacy
  module is refused for a `block` finding fifty lines away.
- **A repository with no `src/` directory is not gated**, apart from its test files. The
  sweep reads any layout; the gate does not.

The contract for `src/detection/pipeline.py` is `docs/contracts/detection.pipeline.md`,
resolved against the payload's `cwd` (falling back to `CLAUDE_PROJECT_DIR`, then `.`).

## The two tiers

| Tier | Meaning | How to clear it |
| --- | --- | --- |
| `block` | the AST decides it | change the code (or the contract) |
| `judge` | the shape is suggestive, not proof | change the code, or record a waiver |

Rule 37 and rule 38 run only when the module has a contract; rule 38 only when that contract
already carries `<!-- derived -->` blocks.

## Examples

Real output from a scratch repository with `src/shapes/`.

A new module with no contract:

```
06:10:12 INFO    lld.gate checking Write src/shapes/circle.py (new module)
06:10:12 INFO    lld.gate deny src/shapes/circle.py: new module, contract missing (1 ms)
```

The reason the model sees:

```
No contract for src/shapes/circle.py.

This is a new module, so the design step has not happened yet. Write
docs/contracts/shapes.circle.md following the new-module skill (step 2), then repeat this
write. Fill Responsibility, Interface, Preconditions, Seam, Dependencies, Errors, Tests and
Deletion test; if the Deletion test answer is 'nothing', do not create it.
```

The contract now exists and promises `area` and `perimeter`; the write defines only `area`:

```
These anti-patterns are decided by the AST and cannot be waived:
  line 0: [37] perimeter - the contract promises perimeter, which the module does not define
```

The write now defines `perimeter`, but also calls `print` and adds an undocumented
two-method class. One `block` finding and two `judge` findings; the reason prints the waiver
row to add:

```
These anti-patterns are decided by the AST and cannot be waived:
  line 13: [19] print - print in a package module: use logging.getLogger(__name__) and a level chosen by who must act

These shapes need your judgment. Fix them, or record why they stand:
  line 4: [08] Tiler - class with only __init__ and tile: a function unless this instance is a seam that gets substituted, or holds state between calls
  line 4: [37] Tiler - Tiler is public but the contract never mentions it: document it, or make it private so it is not a promise

To record a judgment, append a row to docs/contracts/_waivers.md using the format `| path | rule | date | reason |`, for example:
  | src/shapes/circle.py | 8 | 2026-10-29 | why this stands |
The reason is read by a human later, so make it one you would defend.
```

The log line for that decision:

```
06:19:08 INFO    lld.gate deny src/shapes/circle.py: 1 blocking, 2 awaiting judgment - rules [8, 19, 37] (4 ms)
```

A test with no assertion, at `src/shapes/tests/test_circle.py`:

```
A test that cannot fail does not test anything:
  line 1: [27] test_area_builds - test asserts nothing: it passes whatever the code does
```

## The waiver ledger

`docs/contracts/_waivers.md`, one Markdown table row per judgment:

```markdown
| path | rule | date | reason |
| --- | --- | --- | --- |
| src/shapes/square.py | 8 | 2026-10-29 | Tiler is the seam the renderer substitutes in tests |
```

- `path` is the module path relative to the project root, exactly as the gate prints it.
- A waiver clears one rule on one module. It never clears a `block` finding.
- Rows that do not parse are ignored, not guessed at.
- At three or more waivers on one module, every refusal for it adds: *"Repeated exceptions
  on one module are evidence about the module. Redesign it rather than adding another."*
  It does not block on its own.

## Switches and logs

| Variable | Effect | Read by |
| --- | --- | --- |
| `LLD_GATE=off` | allow every call without inspecting it | the hook process, at start |
| `LLD_LOG_LEVEL` | `DEBUG`, `INFO` (default), `WARNING`, `ERROR`; unknown values fall back to `INFO` | the hook only; the CLIs take `--log-level` instead |
| `LLD_LOG_FILE` | write the gate log here instead of `.lld/gate.log` | the hook |

No CLI writes `.lld/gate.log`; they log to stderr only.

The hook reads its environment from the Claude Code process that launched it, so
`LLD_GATE=off` belongs on the command line that starts the session:
`LLD_GATE=off claude`.

`.lld/gate.log` under the project records one line per decision, with the rules that fired
and the elapsed time. `DEBUG` adds the inputs behind each decision. Add `.lld/` to your
`.gitignore`.

Logs go to stderr and the log file, never stdout: stdout carries the JSON decision.

## When it stands aside

The gate allows the call, rather than blocking the session, when:

- stdin is not valid JSON;
- the resulting content cannot be determined (an `Edit` with a non-string field);
- the resulting content does not parse as Python;
- an `OSError` stops it reading the file, contract or ledger (logged at WARNING).

## Replaying a decision

The hook is a plain script: JSON in, JSON out. Run it without Claude Code to see what it
would decide:

```
echo '{"cwd": "'"$PWD"'", "tool_name": "Write", "tool_input": {"file_path": "'"$PWD"'/src/shapes/circle.py", "content": "x = 1\n"}}' \
  | python <plugin>/scripts/require_contract.py
```

stdout is the decision; the log lines go to stderr and `.lld/gate.log`.

## Status

The hook has been exercised with real payloads through the exact command the manifest
declares; every example on this page came from that. It has not been observed intercepting
a write inside a live Claude Code session. Until it has, treat "the gate would have refused
this" as a claim about the script, not about your session, and check `.lld/gate.log`.
