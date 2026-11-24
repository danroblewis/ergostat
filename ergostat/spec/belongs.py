"""A part's system and its name within it (SPEC §2a, *A part's system*): recorded where the part is made, never read
back out of its full name.

A library instance names its parts ``INSTANCE-NAME`` and a remote its parts ``REMOTE-NAME``; the instance or the
remote is the system the part belongs to, and ``NAME`` its short name. The record rides on the part's ``where`` (the
``use:`` or ``remotes:`` line, one copy a part), so the loader's ``defined`` holds it and the compiled model's
``belongs`` maps each reference (``stock.pings-waiting``) to it. A hand-written part has none, whatever its name."""

from __future__ import annotations

import copy
from typing import NamedTuple

KIND = {"systems": "system", "items": "item", "parameters": "parameter", "auxiliaries": "auxiliary",
        "variables": "auxiliary", "stocks": "stock", "flows": "flow", "goals": "goal", "blocks": "block",
        "agents": "agent"}


class Belongs(NamedTuple):
    system: str             # the instance or remote that made it
    short: str              # its name within that system


def own(where, system: str, short: str):
    """A copy of ``where`` that says the part belongs to ``system`` as ``short``."""
    w = copy.copy(where)
    w.belongs = Belongs(system, short)
    return w


def of(where) -> Belongs | None:
    return getattr(where, "belongs", None)


def recorded(defined: dict) -> dict[str, Belongs]:
    """Each part's reference → its system and short name, from the loader's ``defined`` (section, name) → where."""
    return {f"{KIND[s]}.{n}": b for (s, n), w in defined.items() if s in KIND and (b := of(w)) is not None}


PARTS = ("systems", "parameters", "auxiliaries", "stocks", "flows", "goals", "blocks", "agents")


def by_name(spec) -> dict[str, Belongs]:
    """Each name drawn → its owner, only where every part of that name has the same one (a name two parts share
    with different owners, or one owned and one not, has none here, so its full name is shown)."""
    belongs = getattr(spec, "belongs", None) or {}
    out: dict[str, Belongs | None] = {}
    for section in PARTS:
        for n in getattr(spec, section, None) or {}:
            b = belongs.get(f"{KIND[section]}.{n}")
            out[n] = b if out.get(n, b) == b else None
    return {n: b for n, b in out.items() if b is not None}
