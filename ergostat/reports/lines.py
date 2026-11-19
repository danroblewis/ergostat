"""A block's ``report`` line (SPEC §12m): something ergostat could not express or do, said by the block that found it
(the modelling loop's improver or redesigner, typically), drafted as a report for the owner.

    {"report": "a flow's rate cannot read another flow's delayed value"}
    {"report": {"says": "...", "details": "...", "parts": ["flow.x"], "findings": ["code"], "repro": "YAML"}}

One report a block and sentence: said again, it is counted, not drafted again."""

from __future__ import annotations

import hashlib

from . import record

ORIGIN_BLOCKS = ("improver", "redesigner")      # the modelling loop's blocks: their reports are the modelling loop's
SAYS_MAX = 400


def take(run, obj: dict) -> None:
    """A block run's report line: drafted (or counted), or refused with why."""
    r = obj.get("report")
    if isinstance(r, str):
        r = {"says": r}
    if not isinstance(r, dict) or not isinstance(r.get("says"), str) or not r["says"].strip():
        return run.refuse(obj, 'a report line: {"report": "what ergostat could not express or do"}, or {"report": '
                               '{"says": ..., "details": ..., "parts": [...], "findings": [...], "repro": ...}}')
    says = r["says"].strip()
    if len(says) > SAYS_MAX:
        return run.refuse(obj, f"a report's says: one sentence, at most {SAYS_MAX} characters (more goes in details)")
    block = run.b.name
    rid = record.item_of("said-" + hashlib.sha1(f"{block}\n{says.lower()}".encode()).hexdigest()[:10])
    p = run.e.p
    run.flush()
    if record.get(p, rid) is not None:
        record.seen(p, rid)
    else:
        lists = {k: [str(x) for x in r.get(k) or []] if isinstance(r.get(k), list) else None for k in ("parts", "findings")}
        record.draft(p, says, origin="modelling" if any(w in block for w in ORIGIN_BLOCKS) else "agent", by=block,
                     details=str(r["details"]) if r.get("details") else None, parts=lists["parts"],
                     findings=lists["findings"], repro=str(r["repro"]) if r.get("repro") else None, rid=rid)
    run.counts["reports"] = run.counts.get("reports", 0) + 1
    return None
