"""The repair loop (SPEC §12r): triage (``capture``), the fix proposed (``fix``), and applying it (``apply``)."""

from __future__ import annotations

from ..spec.ir import ItemKind

FAILURE = "ergostat.failure"
STATES = ["noted", "open", "awaiting-approval", "applied", "superseded", "dismissed"]
MOVES = {"opened": "open", "passed": "awaiting-approval", "applied": "applied", "apply-failed": "open",
         "dismissed": "dismissed", "superseded": "superseded"}
FROM = {"opened": ("noted", "applied", "superseded"), "superseded": ("noted", "open")}   # moved only from these
BLOCKS = ("repair-fix", "repair-settle")        # the template's own (once: true keeps their names)


def failure_kind() -> ItemKind:
    """Sealed: only ergostat's own event types fold into it (``items.fold``), so no one else can write its fields."""
    return ItemKind(FAILURE, f"{FAILURE}/*", list(STATES), {f"{FAILURE}.{e}": s for e, s in MOVES.items()},
                    ["block", "error", "count", "tests", "risk"], {"input": "json"}, sealed=True,
                    description="a program's failing runs, one item a signature (its block, program, exception type and "
                    "innermost project frame, from a Python, Node, Java or Go trace), triaged and repaired when the "
                    "model uses repair; a good run's swallowed error is noted, never opened (built in, SPEC §12r)",
                    fold={"count": "sum", "first_seen": "first", "swallowed": "sum"},
                    moves_from={f"{FAILURE}.{e}": s for e, s in FROM.items()})
