# Rejected: restating lint rules in the guidance files

**Proposed.** Write the full set of best practices into markdown, including line length,
import order, naming case, complexity limits and type annotation requirements.

**Rejected because** context is a budget. Every always-loaded line competes with the rules
that actually need judgment, and compliance falls as the rule count rises. Anything ruff or
mypy can decide is enforced there and named, not restated.

**Would reconsider if** a rule is mechanically checkable in principle but has no implementation
in the Python toolchain. Such rules live in the prose with an `enforced-by: none` note so they
can be migrated out when tooling catches up.
