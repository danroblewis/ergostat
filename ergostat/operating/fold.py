"""The operating state in force (SPEC §9.5), read from the record: the states entered, the highest-ranked of them,
and the least pool any of them sets. What cannot be read counts as the worst case: pool 0."""

from __future__ import annotations

from . import KIND


def entered(p, spec) -> list:
    """The items of the states entered now (raises when the record cannot be read)."""
    from ..spec import items as its
    return [it for it in its.project(p.events, spec, KIND, transcript=False) if it.state == "entered"]


def in_force(p, spec) -> tuple[str | None, int | None, str]:
    """``(top, pool, why)``: the highest-ranked state entered, the smallest pool among all the states entered (None:
    none sets one), and why, naming the state that sets it. A state entered that the model no longer declares counts
    as pool 0 (and above every rank) until the owner leaves it. A record that cannot be read gives pool 0."""
    try:
        got = entered(p, spec)
    except Exception as e:
        return None, 0, f"the operating record could not be read ({type(e).__name__}: {e}): pool 0 until it can"
    top, pool, why, best = None, None, "", None
    for it in got:
        name = it.id.split("/", 1)[1]
        st = spec.operating.get(name)
        rank, cap = (st.rank, st.pool) if st else (float("inf"), 0)
        if best is None or rank > best:
            top, best = name, rank
        if cap is not None and (pool is None or cap < pool):
            pool = cap
            why = f"operating state {name} entered" + ("" if st else " (no longer declared: pool 0 until it is left)")
    return top, pool, why
