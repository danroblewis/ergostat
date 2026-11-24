"""An action's gate scheduled by the declared operating state in force (SPEC §12k, *Gates by declared state*), and the
owner's bypass leases on a class.

- ``resolve``: the one answer to "what is this action's gate now", for the request, the act and the class table.
- ``standing``: the bypasses standing now, folded in ``seq`` order from ``ergostat.bypass.*``.
- ``lock``: ``flock`` on ``<state dir>/operating.lock``. Entering or leaving a declared state and granting or ending a
  bypass take it exclusive; the gate's decisions take it shared. Each acquisition opens the file afresh (flock
  conflicts are per open file), and none of these takes it again while holding it."""

from __future__ import annotations

import contextlib
import fcntl
import math
import os
import re
import time
from pathlib import Path

from ..spec.ir import BYPASS
from .risk import ORDER

DEFAULT, ELSE = "normal", "else"          # the state a model starts in (none entered), and a map's every-other-state cell
GRANTED, ENDED = f"{BYPASS}.granted", f"{BYPASS}.ended"
MOST = 86400.0                            # a bypass lasts at most a day, at its grant and again when it is read
CLASS = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class BypassError(ValueError):
    """A bypass that cannot be granted or ended as asked."""


def now() -> float:
    return time.time()


@contextlib.contextmanager
def lock(p, exclusive: bool):
    fd = os.open(Path(p.dir) / "operating.lock", os.O_CREAT | os.O_RDWR, 0o600)   # a fresh open file, every time
    try:
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        os.close(fd)


def resolve(action, state: str | None, bypasses: dict, at: float) -> tuple[str, str]:
    """``(gate, why)``. A plain gate is itself. For a map: an unread state (None), or a state with no cell and no
    ``else``, is ``deny``; else the state's cell, or, while the action's class has a bypass standing (``until > at``),
    the looser of that cell and the default state's."""
    m = getattr(action, "states", None)
    if not m:
        return action.gate, f"its gate is {action.gate}"
    if state is None:
        return "deny", "the operating state cannot be read"
    cell = m.get(state, m.get(ELSE))
    if cell not in ORDER:
        return "deny", f"under {state} no cell is written, and no else"
    until, base = bypasses.get(action.cls or action.name), m.get(DEFAULT, m.get(ELSE))
    if isinstance(until, int | float) and not isinstance(until, bool) and until > at and base in ORDER:
        g = ORDER[min(ORDER.index(cell), ORDER.index(base))]
        return g, f"under {state} {cell}; a bypass until {time.strftime('%H:%M', time.localtime(until))}: {g}"
    return cell, f"under {state} {cell}"


def state(p, spec) -> str | None:
    """The declared state in force by name, ``normal`` when none is entered; None when it cannot be read or is a name
    the model does not declare."""
    from ..operating import fold
    try:
        s = fold.current(p, spec)
    except Exception:                                    # noqa: BLE001 - unread is the strictest case (lesson-3)
        return None
    return s if s == DEFAULT or s in spec.operating else None


def reading(p, spec, action) -> dict:
    """What a gate decision reads, for a map gate: the state, the bypasses standing, and what ``resolve`` makes of
    them. Taken under ``lock(p, False)`` by the caller."""
    st, t = state(p, spec), now()
    g, why = resolve(action, st, standing(p, t), t)
    return {"state": st, "gate": g, "why": why}


def standing(p, at: float) -> dict[str, float]:
    """Each class with a bypass standing at ``at``, to its end. Folded in ``seq`` order, never by time: a grant starts a
    fresh lease (nothing of an earlier one kept), an end ends it. A grant that cannot be read (data not a map, ``until``
    missing or not a finite number) stands for nothing, and ends an earlier one; ``until`` is held to the grant's
    time + 24 h. A record that cannot be read: none standing."""
    try:
        held: dict[str, float] = {}
        for e in sorted(p.events.query(n=None, type=f"{BYPASS}.*"), key=lambda e: e["seq"]):
            cls = str(e.get("item") or "").removeprefix(f"{BYPASS}/")
            if e["type"] not in (GRANTED, ENDED) or not CLASS.match(cls):
                continue
            held.pop(cls, None)
            d, t = e.get("data"), e.get("time")
            u = d.get("until") if isinstance(d, dict) and e["type"] == GRANTED else None
            if all(isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x) for x in (u, t)):
                held[cls] = min(float(u), float(t) + MOST)
        return {k: u for k, u in held.items() if u > at}
    except Exception:                                    # noqa: BLE001 - unreadable: no bypass (lesson-3)
        return {}


def classes(spec) -> set[str]:
    """The classes a bypass may be granted on: those of an action with a map gate."""
    return {a.cls or a.name for a in spec.actions.values() if a.states}


def _owner(env) -> None:
    if (os.environ if env is None else env).get("ERGOSTAT_RUN"):
        raise BypassError("a bypass is the owner's act: refused from a run (ERGOSTAT_RUN is set)")


def grant(p, spec, cls: str, seconds: float, note: str | None = None, by: str = "owner", env=None) -> dict:
    _owner(env)
    if not CLASS.match(cls) or cls not in classes(spec):
        raise BypassError(f"{cls!r}: not the class of an action with a gate by state "
                          f"({', '.join(sorted(classes(spec))) or 'none'})")
    if isinstance(seconds, bool) or not isinstance(seconds, int | float) or not 0 < seconds <= MOST:
        raise BypassError("--for: more than 0 and at most 24h")
    with lock(p, exclusive=True):
        return p.events.add(GRANTED, item=f"{BYPASS}/{cls}", source="owner",
                            data={"until": time.time() + seconds, "by": by, "note": note, "ended": None, "ended_by": None})


def end(p, cls: str, by: str = "owner", env=None) -> dict:
    """End a standing bypass: any class with one, even one no longer map-gated (ending only ever tightens)."""
    _owner(env)
    if not CLASS.match(cls):
        raise BypassError(f"{cls!r}: not a class name")
    with lock(p, exclusive=True):
        if cls not in standing(p, now()):
            raise BypassError(f"{cls}: no bypass standing")
        return p.events.add(ENDED, item=f"{BYPASS}/{cls}", source="owner", data={"ended": time.time(), "ended_by": by})
