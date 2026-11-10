"""Sales may record awards and hand over accessible deals, without approval powers.

Document/company scope and all commercial-position checks remain at the callers.
This role set must not be reused for approvals, reversals or delivery release.
"""

AWARD_ROLES = frozenset({
    "Sales User", "BS Scoped Sales", "Sales Manager",
    "Commercial Controller", "Managing Director",
})
