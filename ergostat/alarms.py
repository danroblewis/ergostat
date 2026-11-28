"""An ``alarm`` block's raisings as events (SPEC §9.2, *Alarms*): the engine, which evaluates it, records on change only

- ``alarm.raised`` when its output turns on: what it watched, the value, its threshold, why, and when;
- ``alarm.cleared`` when it turns off again (back within its bound, or its input unknown), with how long it lasted.

Both are about the raising's own object, ``ergostat.alarm/<block>/<raise id>`` (the raise event's id), folded into the
built-in projection ``ergostat.alarm``: one object per raising, raised then cleared, its page its history, the Events
page's ``type.startswith('alarm.')`` every raising of every alarm. One object per raising (not one per alarm block)
reads best: each has its own value, threshold, raised, cleared and how long, never overwritten by the next, and an
alarm block's raisings are an id range (``prefix: block``), listed on its projection's page by block.

What is raised now is kept in ``<state>/alarms.json`` (written on change, under a lock, by every engine of a sharded
record for its own blocks): the snapshot's "raised since" reads the raise from it, and an engine started again reads it
back, so a raising open when it stopped goes on (no second ``alarm.raised``) or is cleared on its first pass. A block
gone from the model is cleared too. Nothing acknowledges an alarm: none exists in ergostat."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading
import time
from pathlib import Path

ALARM = "ergostat.alarm"
STATES = ["raised", "cleared"]
TYPES = ("alarm.raised", "alarm.cleared")
STATE = "alarms.json"
SOURCE = "ergostat"


def kind():
    from .spec.ir import ItemKind
    return ItemKind(ALARM, f"{ALARM}/*", list(STATES), dict(zip(TYPES, STATES, strict=True)),
                    ["block", "watches", "value", "bound", "raised", "cleared", "lasted"], {}, None,
                    "one raising of an alarm block: what it watched, the value and the threshold it crossed, why, when "
                    "it was raised and cleared, and how long it lasted (built in, SPEC §9.2)",
                    sealed=TYPES, finished=["cleared"], prefix="block")


def id_of(block: str, raise_id: str) -> str:
    return f"{ALARM}/{block}/{raise_id}"


def read_state(state_dir) -> dict[str, dict]:
    """The raisings open now, by block: ``{block: {id, item, raised, value, watches, bound, why}}``."""
    try:
        got = json.loads((Path(state_dir) / STATE).read_text())
    except (OSError, ValueError, TypeError):
        return {}
    return {k: v for k, v in got.items() if isinstance(v, dict) and v.get("item")} if isinstance(got, dict) else {}


def bound_of(b) -> str:
    from .state import fmt
    return " and ".join(f"{k} {fmt(float(b.params[k]))}" for k in ("above", "below") if b.params.get(k) is not None)


def _why(b, value, watches: str) -> str:
    p, v = b.params, value
    side = ("above", p.get("above")) if p.get("above") is not None and v is not None and v > float(p["above"]) else \
        ("below", p.get("below"))
    held = f" for {float(p['for']):g}s" if p.get("for") else ""
    return f"{watches} at {v:g}, {side[0]} {float(side[1]):g}{held}" if v is not None and side[1] is not None else \
        f"{watches} out of bounds ({bound_of(b)})"


class Alarms:
    """The engine's, one for its life: ``seen(block, on, value, now, out)`` after each step of an alarm block."""

    def __init__(self, p):
        self.p = p
        self.dir = getattr(p, "dir", None)
        self.open: dict[str, dict] = read_state(self.dir) if self.dir else {}
        self.lock = threading.Lock()
        self.spec_seen = None

    def seen(self, b, on: bool, value, now: float, add, causedby: str | None = None) -> dict | None:
        """Block ``b``'s output is ``on`` now: the event of a change (raised or cleared), recorded by ``add(type,
        **kw)``; None when it did not change (the common case: one dict lookup)."""
        if on == (b.name in self.open):
            return None
        with self.lock:
            if on == (b.name in self.open):
                return None
            if on:
                rid = hashlib.sha1(f"{b.name}\0{now!r}".encode()).hexdigest()[:32]   # (its raise, its id)
                watches = ", ".join(str(r) for r in b.reads())
                x = {"id": rid, "item": id_of(b.name, rid), "raised": now, "value": value, "watches": watches,
                     "bound": bound_of(b), "why": _why(b, value, watches)}
                self.open[b.name] = x
                self._write({b.name: x})
                data = {"block": b.name, "watches": watches, "value": value, "bound": x["bound"], "why": x["why"],
                        "raised": now, **{k: float(b.params[k]) for k in ("above", "below", "for")
                                          if b.params.get(k) is not None}}
                return add("alarm.raised", id=rid, item=x["item"], source=SOURCE, causedby=causedby, data=data)
            x = self.open.pop(b.name)
            self._write({b.name: None})
        return add("alarm.cleared", item=x["item"], source=SOURCE, causedby=x["id"],
                   data=self._cleared(x, now, value, "back within its bound" if value is not None else
                                      "its input is unknown: no longer said raised"))

    def prune(self, spec, now: float, add) -> None:
        """Once per model: a raising whose block is no longer an alarm of it, cleared."""
        if self.spec_seen is spec:
            return
        self.spec_seen = spec
        gone = [n for n in list(self.open) if getattr(spec.blocks.get(n), "type", None) != "alarm"]
        for n in gone:
            with self.lock:
                x = self.open.pop(n, None)
                if x is None:
                    continue
                self._write({n: None})
            add("alarm.cleared", item=x["item"], source=SOURCE, causedby=x["id"],
                data=self._cleared(x, now, None, "its block is no longer an alarm of the model"))

    @staticmethod
    def _cleared(x: dict, now: float, value, why: str) -> dict:
        lasted = round(now - float(x.get("raised") or now), 3)
        return {"block": x["item"].split("/")[1], "cleared": now, "lasted": lasted, "cleared_why": why,
                **({"value": value} if value is not None else {})}

    def _write(self, changes: dict[str, dict | None]) -> None:
        """``alarms.json`` updated for these blocks alone (another shard's kept), under its lock."""
        if self.dir is None:
            return
        path = Path(self.dir) / STATE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path.with_suffix(".lock"), "w") as lk:
                fcntl.flock(lk, fcntl.LOCK_EX)
                was = read_state(self.dir)
                for k, v in changes.items():
                    if v is None:
                        was.pop(k, None)
                    else:
                        was[k] = v
                if not was:
                    path.unlink(missing_ok=True)
                    return
                tmp = path.with_suffix(f".{os.getpid()}.tmp")
                tmp.write_text(json.dumps(was))
                os.replace(tmp, path)
        except OSError:
            pass


def link(item: str) -> str:
    return f"/{item}"


def since_text(t: float) -> str:
    return time.strftime("%H:%M", time.localtime(float(t)))
