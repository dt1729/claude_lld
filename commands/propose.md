---
description: Turn a verified sweep finding on someone else's repository into a pull request or issue they would accept
argument-hint: "<owner/repo> [pr|issue]"
---

Clone `$1`, sweep it, verify one finding against the source, and propose a change the
maintainer can merge without taking anything on trust. Default to a pull request; fall back
to an issue only when the right change is a design decision that is theirs to make.

## The bar

A stranger's pull request lands when it is a concrete, tested change with no sales pitch. An
issue that says "a tool found 8% duplication" gets closed, and it makes the tool look like
spam. So:

- One finding per proposal. The strongest one, not the longest list.
- The finding is verified in the source, not in the sweep output. Open the files. Diff the
  copies. Confirm the dead function has no caller a framework would supply.
- Classify the repository first. A library's unused public API is not dead code. A deliberate
  copy with a header explaining itself is not a clone. If the strongest finding dissolves on
  reading, stop and say so; nothing goes out.
- A pull request carries its own evidence: the diff, the tests that ran, and the tests that
  could not run here and why. Never claim a suite passed that did not.
- One sentence on how it was found. No link to the plugin unless the maintainer asks.
- Offer the exit: "happy to drop this if the copies were deliberate."

## Steps

1. `git clone --depth 1 https://github.com/$1` into a scratch directory, then
   `python "${CLAUDE_PLUGIN_ROOT}/scripts/sweep.py" <dir> --json`.
2. Read the dead list grouped by module and class, and the top clone groups by size times
   sites. Apply the checks in `/lld-seed:sweep` ("Before a verdict").
3. Pick the one finding that is (a) in production code, (b) verifiable by opening two files,
   and (c) fixable in one commit. Typical shapes that have landed:
   - the same methods byte-identical across sibling classes, with no shared base;
   - a helper copied across scripts in the same directory;
   - functions with no caller, no framework hook, and no export.
4. For a pull request: branch, make the change, run the tests that exercise the touched
   files, run the repository's own linter on them. Commit with a message that states the
   behaviour is unchanged and which tests ran. `gh repo fork --clone=false`, push the branch
   to the fork, `gh pr create --head <you>:<branch>`.
5. For an issue: name the files, the line counts, and the specific change you would make,
   so the maintainer can say yes or no in one reply.
6. Record what was sent, where, and the finding behind it, so the next proposal to the same
   maintainer does not repeat it.

## Description template

```
<Classes or files> each carry the same <what>, byte for byte. This moves it into
<where>; each <unit> keeps <what stays specific>.

- No behaviour change intended; <n> lines removed, <m> added.
- <One design note a reviewer would ask about.>

Verification: <test modules> pass unchanged (<n> tests). <What could not run here and why>;
please run the full suite before merging.

Found while measuring duplication across repositories with a call-graph tool; happy to
drop this if the copies were deliberate.
```
