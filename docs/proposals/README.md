# Proposals

A proposal is a change to the plugin that is argued but not yet decided. It differs from the
two neighbouring folders on purpose:

| Folder | Holds |
| --- | --- |
| `docs/incidents.md` | something that went wrong, and what changed because of it |
| `docs/proposals/` | something that should change, with evidence, not yet accepted |
| `.out-of-scope/` | something rejected, with the reasoning, so it is not re-litigated |

A proposal arrives with measurements or it does not arrive. This repo's own rule is that a
rule with no incident behind it is a prediction; a proposal with no evidence behind it is the
same thing in a longer form.

| # | Title | Status | Source |
| --- | --- | --- | --- |
| [001](001-preconditions.md) | Precondition checking | **open** | applying v0.5.0 to `trackscope` |
| [001a](001a-where-contracts-execute.md) | Where a contract lives, and what the module carries | **decided** | 001 Appendix B |

## 001 in one paragraph

Every gate the plugin installs went green on a package with no input validation anywhere:
`Range: bytes=100-50` returned `Content-Length: -49`, `--hfov 180` built a camera with a
focal length of `5.9e-14` and drew every bearing without a word. The limit is structural, not
a missing rule - `detect_patterns.py` answers questions about *shape*, and "this function
divides by a number the caller controls" is a question about the relationship between a
parameter and what is done to it. The proposal adds a `Preconditions` section to the contract
where each parameter gets one of three verdicts - `reject`, `clamp`, `propagate` - and drives
the guard, the gate and the tests from that one table.

**Not accepted yet.** Step 1 of the proposal's own order - the contract section and its
validator, no Semgrep - is the piece that stands alone, and it is a breaking schema change:
adding a required section invalidates every contract in every repo already seeded.
