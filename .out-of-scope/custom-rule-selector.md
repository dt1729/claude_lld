# Rejected: a custom rule-card corpus with a selector command

**Proposed.** Store ~50 atomic rule cards with YAML front-matter (`id`, `tags`, `applies_to`,
`severity`), plus a `/rules` command that greps the front-matter and loads the cards matching
the current task and path.

**Rejected because** it reimplements progressive disclosure, which the harness already does.
A skill's `description` is the selector: the model loads `SKILL.md` when the description
matches, and reference files only when a pointer in the body fires. A hand-rolled retrieval
layer adds a moving part, a second source of truth, and no capability.

**Would reconsider if** rule selection needed to depend on something a description cannot
express, such as git history or per-file churn metrics.
