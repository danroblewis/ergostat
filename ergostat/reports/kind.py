"""The built-in item kind ``ergostat.report`` (SPEC §12m)."""

from __future__ import annotations

from ..spec.ir import ItemKind

REPORT = "ergostat.report"
STATES = ["drafted", "reviewed", "submitted", "dismissed"]
MOVES = {"reviewed": ("drafted",), "submitted": ("drafted", "reviewed"), "dismissed": ("drafted", "reviewed")}


def report_kind() -> ItemKind:
    on = {f"{REPORT}.{s}": s for s in STATES}
    return ItemKind(REPORT, f"{REPORT}/*", list(STATES), on, ["title", "origin", "occurrences", "labels"], {}, None,
                    "a report of something wrong with ergostat itself, drafted and scrubbed for the owner to read and "
                    "submit to ergostat's GitHub project by hand; never sent by ergostat (built in, SPEC §12m)")


def builtin() -> dict[str, ItemKind]:
    return {REPORT: report_kind()}
