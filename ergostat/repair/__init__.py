"""The repair loop (SPEC §12r): triage (``capture``), the fix proposed (``fix``), and applying it (``apply``)."""

from __future__ import annotations

from ..spec.ir import ItemKind

FAILURE = "ergostat.failure"
STATES = ["noted", "open", "awaiting-approval", "applied", "dismissed", "verified", "regressed", "reverted"]
MOVES = {"opened": "open", "passed": "awaiting-approval", "applied": "applied", "apply-failed": "open", "dismissed": "dismissed",
         "verified": "verified", "regressed": "regressed", "reverted": "reverted"}   # (revert-failed: data only, no move)
VERIFY_MIN, VERIFY_MAX = 1, 50                  # settle's --verify: good runs after a fix, bounded (check, and settle)
BLOCKS = ("repair-fix", "repair-settle")        # the template's own (once: true keeps their names)


def failure_kind() -> ItemKind:
    """Sealed: only ergostat's own event types fold into it (``items.fold``), so no one else can write its fields."""
    return ItemKind(FAILURE, f"{FAILURE}/*", list(STATES), {f"{FAILURE}.{e}": s for e, s in MOVES.items()},
                    ["block", "error", "count", "tests", "risk"], {"input": "json"}, sealed=True,
                    description="a program's failing runs, one item a signature (its block, program, exception type and "
                    "innermost frame), triaged and repaired when the model uses repair (built in, SPEC §12r)",
                    fold={"count": "sum", "first_seen": "first"})
