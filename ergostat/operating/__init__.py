"""Operating states (SPEC §9.5, *Operating states*): situations the model declares under ``operating:``, each with a
rank and an optional pool, entered by the owner's typed act or by a goal's trip and left by the owner only. The state
in force caps the pool of every block that takes items. Folded from the record like any item: the built-in kind
``ergostat.operating`` (only when ``operating:`` is declared), one item per state, ``ergostat.operating/<state>``."""

from __future__ import annotations

from ..spec.ir import ItemKind

KIND = "ergostat.operating"
PREFIX = f"{KIND}."
ENTERED = f"{KIND}.entered"     # data: by (owner | run | trip), why, and for a trip goal and spell
LEFT = f"{KIND}.left"           # data: by, why; refused by the fold when recorded during a run (causedby set)
WATCHING = f"{KIND}.watching"   # about a goal (item: goal.<name>), data: {state}: where an unread clock starts
STATES = ["entered", "left"]


def item_of(state: str) -> str:
    return f"{KIND}/{state}"


def kind() -> ItemKind:
    return ItemKind(KIND, f"{KIND}/*", list(STATES), {ENTERED: "entered", LEFT: "left"}, ["by", "why", "since", "trips"],
                    {}, None, "an operating state of the model: entered by the owner, a run or a goal's trip, left by "
                    "the owner only; the state in force caps the pool of every block that takes items (built in, "
                    "SPEC §9.5)", sealed=True)


def apply(it, e: dict) -> str | None:
    """An operating event folded onto its item: why it was refused, or None. An ``entered`` on an item entered adds
    its trip; one after a ``left`` (or the first) starts afresh: nothing of the earlier entry is kept (lesson-5)."""
    d, was = e.get("data") or {}, it.state
    if e["type"] == ENTERED:
        if it.state != "entered" or "since" not in it.fields:
            it.fields.clear()
            it.fields.update({"by": d.get("by") or "owner", "why": d.get("why") or "", "since": e["time"], "trips": []})
        if d.get("goal") is not None and d.get("spell") is not None:
            it.fields["trips"] = [*it.fields.get("trips", []), {"goal": d["goal"], "spell": d["spell"], "event": e["id"]}]
        to = "entered"
    elif e["type"] == LEFT:
        if e.get("causedby"):
            if it.n == 1:                                    # (nothing entered it: it is not in force)
                it.state = "left"
            return f"recorded during a run ({str(e['causedby'])[:8]}): only the owner leaves a state"
        it.fields.update({"by": d.get("by") or "owner", "why": d.get("why") or "", "since": e["time"]})
        to = "left"
    else:
        return None                                          # (watching is about a goal, never about a state)
    if to != was:
        it.moves.append({"time": e["time"], "from": was, "to": to, "event": e["id"], "type": e["type"]})
        it.state, it.entered = to, e["time"]
    return None
