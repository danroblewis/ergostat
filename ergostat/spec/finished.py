"""Which of a projection's states are finished (SPEC §5a, *Items*): one rule for the Items listing, the relations
(``precedence.py``), the estimates (``numbers/etamodel.py``), the state counts over time (``series.py``) and, with
``dead`` (``ends_of``), the process map's end (``process.py``). Message routing keeps its own on purpose
(``messages/route.py`` ``route_done_states``).

- **Declared**: the states ``messages: {done:}`` names for the projection, else those its own ``finished:`` names.
- **Inferred** (nothing declared): the states after the first that no item has left yet (``left``).
- Either way never a state an item waits in to be taken (the first, or one a block takes from), ``leased``, ``dead``
  or a state declared paused (``messages: {paused:}``): paused is its own list.
- **Lives on**: a projection with one state, or with nothing declared and nothing inferable, has no finished state (a pool
  is held, never done). ``dead`` says whether a dead letter ends its items (the projection is taken, so it has ``dead``).

The older rule (``itemindex.done_states``, the last state when every one has been left) stays for ``spec/about.py``
and the index's own unfinished count."""

from __future__ import annotations

from .ir import DEAD, LEASED


def finish_of(spec, kind: str | None, left: set[str]) -> dict:
    """``{finished, paused, dead, from: declared|inferred|none, lives_on, queue}`` for the projection named ``kind``."""
    k = (getattr(spec, "items", None) or {}).get(kind or "")
    states = list(k.states) if k is not None else []
    msgs = getattr(spec, "messages", None)
    paused = list((getattr(msgs, "paused", None) or {}).get(kind) or [])
    queue = list(dict.fromkeys(states[:1] + [s for b in getattr(spec, "blocks", {}).values()
                                             if b.takes and b.takes.kind == kind for s in b.takes.at]))
    never = set(queue) | {LEASED, DEAD} | set(paused)
    declared = list((getattr(msgs, "done", None) or {}).get(kind) or getattr(k, "finished", None) or [])
    if declared:
        finished, how = [s for s in declared if s not in never], "declared"
    else:
        finished, how = ([s for s in states[1:] if s not in left and s not in never] if len(states) > 1 else []), "inferred"
    if not finished and how == "inferred":
        how = "none"
    return {"finished": finished, "paused": paused, "dead": DEAD in states, "from": how,
            "lives_on": not finished, "queue": queue}


def ends_of(spec, kind: str | None, left: set[str]) -> list[str]:
    """Where an item's life ends: the projection's finished states and, a taken projection, ``dead``; none when it lives on. The
    states the Items list hides, and the process map's end."""
    f = finish_of(spec, kind, left)
    return [] if f["lives_on"] else [*f["finished"], *([DEAD] if f["dead"] else [])]
