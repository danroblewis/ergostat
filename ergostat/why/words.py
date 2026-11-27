"""The answer in words: one paragraph to paste to a stakeholder, and the lines ``ergostat why ITEM`` prints."""

from __future__ import annotations

from ..durations import human

WORDS = {"work": "unfinished work", "person": "a person", "pool-full": "a full pool", "gate": "a gate refusing runs",
         "lease": "a lease", "block": "a block", "closed": "a closed goal or intake", "parked": "a parked or dead item",
         "nothing": "nothing takes it", "cycle": "a cycle", "missing": "a missing item", "unknown": "not known"}


def _now(a: dict) -> str:
    n = a.get("now") or {}
    if not n.get("state"):
        return f"{a['item']} has no state"
    return f"{a['item']} has been in {n['state']}" + (f" for {human(n['for'])}" if n.get("for") is not None else "")


def summary(a: dict) -> str:
    """One paragraph: where it is and for how long, what holds it (through what), who must act and how."""
    if not a["known"]:
        return f"{a['item']}: the record cannot say why it is not done: " + "; ".join(a["missing"]) + "."
    if a["done"]:
        return f"{_now(a)}, which its projection counts as finished: it is done."
    r = a.get("root")
    from .within import words
    if r is None:
        return (f"{_now(a)}.{words(a.get('place'))} What holds it could not be worked out: "
                + ("; ".join(a["missing"]) or "nothing found") + ".")
    n = a["now"] or {}
    usual = f" ({n['said']})" if n.get("usual") else ""
    through = "" if len(r["path"]) < 2 or r["kind"] == "cycle" else \
        f" It waits on {', which waits on '.join(r['path'][1:])}."
    more = f" ({len(a['roots']) - 1} other cause{'s' if len(a['roots']) > 2 else ''} found too.)" if len(a["roots"]) > 1 else ""
    return (f"{_now(a)}{usual}.{through}{words(a.get('place'))} The cause, {WORDS.get(r['kind'], r['kind'])}: {r['says']}. Next: "
            f"{r['owner']} to {r['action']}" + (f" (`{r['command']}`)" if r.get("command") else "") + f".{more}"
            + (" Not known: " + "; ".join(a["missing"]) + "." if a["missing"] and r["kind"] != "unknown" else ""))


def lines(a: dict) -> list[str]:
    """``ergostat why ITEM``: the summary, then each part on its own line."""
    out = [summary(a), ""]
    n = a.get("now") or {}
    if n.get("said"):
        out.append(f"  now       {n.get('state')}: {n['said']}")
    for i, r in enumerate(a.get("roots") or []):
        out.append(f"  {'cause' if i == 0 else 'also':<9} {r['kind']}: {r['says']}")
        if len(r["path"]) > 1:
            out.append(f"  {'':<9} through {' → '.join(r['path'])}")
        out.append(f"  {'':<9} next: {r['owner']}: {r['action']}" + (f"  $ {r['command']}" if r.get("command") else ""))
    for e in a.get("evidence") or []:
        out.append(f"  evidence  {e['says']}" + (f"  {e['link']}" if e.get("link") else ""))
    for m in a.get("missing") or []:
        out.append(f"  missing   {m}")
    return out
