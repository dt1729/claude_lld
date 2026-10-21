---
name: commits
description: Write commits that explain a change rather than restate it - what to put in one commit, what the subject and body owe a reader, and when the history is the only place a decision survives. Use when committing, writing a commit message, splitting work into commits, or reviewing a history.
---

# Commits

A commit message is read exactly once, by someone who has just found the line that broke
production and is looking at `git blame`. Everything else about it is secondary.

That reader can already see **what** changed; the diff is right there. What they cannot
recover is **why**, and what you considered and rejected. A message that restates the diff
tells them nothing they did not have.

## One reason to change per commit

The unit is a reason, not a file count and not a day's work. Two reasons in one commit means
neither can be reverted alone, and `git bisect` lands on a change that did two things.

```
good   Add the contract gate                      one reason
good   Fix the gutter wrapping in the demo        one reason
bad    Add the gate and fix the demo gutter       revert takes both
bad    End of day                                 no reason at all
```

A refactor that enables a fix is **two** commits: the refactor with no behaviour change,
then the fix. The reviewer can then read the second one.

## The subject says what changed

One line, imperative, no full stop, under about 70 characters. It completes the sentence
"this commit will…".

```
good   Stop the gate blocking exception hierarchies
good   Remove Depth from contracts
bad    Fixed stuff
bad    Update contracts.py        names the file, not the change
bad    WIP                        a reason not yet found
```

Name the behaviour, not the file. The file is in the diff.

## The body says why, and what you rejected

This is the part that earns its keep. Four things belong here, in this order, and any that
do not apply are simply left out:

1. **What was wrong before.** The failure, not the feature. *"The gate only resolved the
   immediate base, so every exception subclass was blocked."*
2. **Why this fix and not the obvious one.** The rejected alternative is the single most
   valuable sentence in a history, because the next reader will think of it too.
3. **What this does not fix.** A known limit recorded here is a limit; one left unsaid is a
   bug report waiting.
4. **Evidence.** The test count, what you ran, what it said.

Wrap at 72 characters so `git log` stays readable in a terminal.

## Record the decision where it survives

A decision made in a chat window is gone next week. A decision in the commit body is attached
to the lines it explains, forever, and `git blame` leads to it with no search.

So when a change encodes a judgment - a threshold, a rule that does not apply, a seam placed
here rather than there - the body is where it goes. If the judgment turns out wrong later,
the body is also the evidence of what you believed at the time, which is what a post-mortem
needs and nobody ever has.

## Commit when a unit of work is finished

Not at the end of a session, and not when someone asks. A finished unit is: it works, its
tests pass, and you could explain it in one sentence. If you cannot write a subject line for
it, it is not one unit - which is the signal to split it, not to write a vaguer subject.

Leaving finished work uncommitted pending review is how an afternoon's work becomes one
unreviewable commit.

## Never

- **Never `--no-verify`.** The hooks are the gate. A hook that fails has found something;
  skipping it hides the finding and keeps the defect.
- **Never commit a secret**, not even to a branch you will rebase. It is in the reflog, in
  every clone, and in the pack file.
- **Never mix a format pass with a change.** The change becomes invisible in the diff. Format
  separately or not at all.
- **Never write a message you would not want quoted** in the post-mortem that cites it.

## What a good one looks like

```
Stop the gate blocking the exception hierarchies the guidance requires

FORMAT.md requires per-condition error types deriving from a package base;
rule 04 blocked every one of them, unwaivably, because it resolved only the
immediate base class. Following the guidance made the gate unusable.

_local_exception_types takes the transitive closure of classes deriving from
Exception, and rules 04 and 05 skip them. An exception tree is the one case
where inheriting from your own concrete class is correct.

Three regression tests, including one proving a non-exception concrete base
still blocks: the exemption is for exception trees, not inheritance generally.

137 tests, ruff and mypy --strict green.
```

Subject names the behaviour. First paragraph is the failure. Second is the fix and why it is
the right one. Third is the limit of the exemption, written down before anyone asks. Fourth
is the evidence.
