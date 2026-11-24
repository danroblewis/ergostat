"""Failures that cluster on a field hold only that group (SPEC §9.5, *Faults*): ``takes: {..., faults: {hold-by:
[vpn]}}``. A circuit breaker for each value of each field named, per block: closed while its items succeed; **open**
(held: not taken, a failing run given back uncounted) once ``FAILS`` runs in a row on that value, of at least ``ITEMS``
items, failed within ``WINDOW``; **half-open** after a back-off, when one item of it is taken as a probe (none while an
item of it is leased); a success releases it, a probe's failure doubles the back-off (``BACKOFF`` first, at most
``MOST``). An item with no value for the field is never held by this rule.

The ends counted are this engine's runs of the block: an ack is a success; a counted nack or a counted expiry is a
failure; one given back uncounted (stopped, gone, or through an outage of its ``healthy``) is neither.

The hold is events about the block: ``ergostat.group.held`` (``block``, ``field``, ``value``, the evidence: ``failed``,
``items``, ``since``; ``began``, ``waiting``: its items waiting then, ``backoff``, ``probe_at``, ``why``), a failed
probe's ``ergostat.group.probed`` (``item``, ``backoff``, ``probe_at``) and the end, ``ergostat.group.released``
(``item``: the success, ``why``, ``since``, ``until``, ``held`` seconds), each caused by the hold. An engine that
starts takes the open holds up from the record, their back-off with them."""

from __future__ import annotations

import json
import math
import threading
import time

from .fold import held as leased

HELD, PROBED, RELEASED = "ergostat.group.held", "ergostat.group.probed", "ergostat.group.released"
SOURCE = "ergostat"
WINDOW = 600.0        # seconds: failures older than this are not evidence
FAILS = 3             # failures in a row on one value (no success between) to hold it
ITEMS = 2             # of at least this many items (one item failing again and again holds nothing)
BACKOFF = 60.0        # seconds from the hold to its first probe
MOST = 1800.0         # the back-off doubles on each failed probe, at most this
FIELDS = 8            # hold-by names at most this many fields
KEPT = 50             # failures kept per value (the newest)


def compile_hold_by(c, f, at, w: str) -> list[str]:
    """``hold-by: FIELD`` or ``[FIELD, ...]``: item fields, at most ``FIELDS``."""
    x = f.get("hold-by")
    if x is None:
        return []
    x = [x] if isinstance(x, str) else x
    if (not isinstance(x, list) or not x or len(x) > FIELDS
            or not all(isinstance(n, str) and n.strip() and n == n.strip() for n in x)):
        c.err(f"{w}.hold-by: an item field's name, or a list of 1 to {FIELDS} of them (hold-by: [vpn])", at, "bad-takes")
        return []
    return list(dict.fromkeys(x))


def value(fields: dict, f: str) -> str | None:
    """An item's value for a hold-by field, as text; None (never held by it) when it has none."""
    v = (fields or {}).get(f)
    if v is None or v == "" or v == [] or v == {}:
        return None
    return v if isinstance(v, str) else json.dumps(v, sort_keys=True)


def _num(x, default: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError, OverflowError):
        return default
    return v if math.isfinite(v) and v >= 0 else default


class Groups:
    def __init__(self, eng):
        self.e = eng
        self.lock = threading.Lock()
        self.fails: dict[tuple, list] = {}   # (block, field, value) → [(time, item)]: its failures since its last success
        self.on: dict[tuple, dict] = {}      # (block, field, value) → {event, backoff, at: next probe, probe: its run}
        self.taken_up: set[str] = set()

    @staticmethod
    def keys(b, fields) -> list[tuple]:
        by = getattr(b.takes, "hold_by", None) if b is not None and b.takes else None
        return [(b.name, f, v) for f in by or () if (v := value(fields, f)) is not None]

    # ---- in the dispatcher's look (its lock held)

    def only(self, b, got: list, every: list, now: float) -> list:
        """Of the items a block may take (in its order), those not held: a held group's items are left out, but one, a
        probe, when its back-off is over and no item of it is leased. A hold the evidence calls for is opened first."""
        by = b.takes.hold_by if b.takes else []
        with self.lock:
            for k, h in [(k, h) for k, h in self.on.items() if k[0] == b.name and k[1] not in by]:
                self._release(k, h, None, now, f"hold-by: {k[1]} is not in the model now")
            if not by:
                return got
            self._take_up(b.name)
            for k, f in list(self.fails.items()):
                f = self.fails[k] = [x for x in f if x[0] > now - WINDOW]
                if not f:
                    self.fails.pop(k)                    # (no evidence left: forgotten, however many values come)
                elif k[0] == b.name and k[1] in by and k not in self.on and len(f) >= FAILS \
                        and len({i for _, i in f}) >= ITEMS:
                    self._hold(b, k, f, every, now)
            held = {k: h for k, h in self.on.items() if k[0] == b.name}
            if not held:
                return got
            busy = {k for i in every if (ls := leased(i.fields)) and ls.get("block") == b.name
                    for k in self.keys(b, i.fields)}
            due = {k for k, h in held.items() if h["at"] <= now and k not in busy}
            out = []
            for it in got:
                ks = [k for k in self.keys(b, it.fields) if k in held]
                if ks and not all(k in due for k in ks):
                    continue
                due -= set(ks)
                out.append(it)
            return out

    def _hold(self, b, k: tuple, f: list, every: list, now: float) -> None:
        waiting = sum(1 for i in every if i.state in b.takes.at and not leased(i.fields) and k in self.keys(b, i.fields))
        since = f[0][0]
        why = (f"{waiting} item{'' if waiting == 1 else 's'} held: {k[1]}={k[2]}, {len(f)} of {len(f)} failed since "
               f"{time.strftime('%H:%M', time.localtime(since))}")
        ev = self.e.p.events.add(HELD, item=b.name, source=SOURCE, data={
            "block": b.name, "field": k[1], "value": k[2], "failed": len(f), "items": len({i for _, i in f}),
            "since": since, "began": now, "waiting": waiting, "backoff": BACKOFF, "probe_at": now + BACKOFF, "why": why})
        self.on[k] = {"event": ev, "backoff": BACKOFF, "at": now + BACKOFF, "probe": None}
        self.e.say(f"{b.name}: {why}: probed in {BACKOFF:g}s")

    def _take_up(self, block: str) -> None:
        """Once a block: the holds an earlier engine recorded and never released, with their latest back-off."""
        if block in self.taken_up:
            return
        self.taken_up.add(block)
        for ev in self.e.p.events.query(n=None, item=block, type="ergostat.group.*"):
            d = ev.get("data") or {}
            k = (block, d.get("field"), d.get("value"))
            if not isinstance(k[1], str) or not isinstance(k[2], str):
                continue
            h = self.on.get(k)
            if ev["type"] == HELD:
                back = _num(d.get("backoff"), MOST)
                self.on[k] = {"event": ev, "backoff": back, "at": _num(d.get("probe_at"), time.time() + back),
                              "probe": None}
            elif h is not None and ev.get("causedby") == h["event"]["id"]:
                if ev["type"] == RELEASED:
                    self.on.pop(k, None)
                elif ev["type"] == PROBED:
                    h["backoff"] = _num(d.get("backoff"), MOST)
                    h["at"] = _num(d.get("probe_at"), time.time() + h["backoff"])

    def taken(self, b, fields, run: str) -> None:
        """An item taken: when its group is held, it is the probe; the next waits another back-off at least."""
        now = time.time()
        with self.lock:
            for k in self.keys(b, fields):
                if (h := self.on.get(k)) is not None:
                    h["probe"], h["at"] = run, max(h["at"], now + h["backoff"])

    # ---- at a run's end (the ends' lock held)

    def fault(self, b, fields) -> str | None:
        """Why a failing run of this item is not to count: its group is held. None: it is not."""
        with self.lock:
            for k in self.keys(b, fields):
                if (h := self.on.get(k)) is not None:
                    return f"held: {k[1]}={k[2]} ({h['event']['data'].get('why', '')})"
        return None

    def ended(self, b, fields, item: str, run: str, ok: bool | None) -> None:
        """A run's end: ``ok`` True a success (releases its groups), False a failure (evidence; a probe's lengthens
        the back-off), None neither."""
        now = time.time()
        with self.lock:
            for k in self.keys(b, fields):
                h = self.on.get(k)
                probe = h is not None and h["probe"] == run
                if probe:
                    h["probe"] = None
                if ok is True:
                    self.fails.pop(k, None)
                    if h is not None:
                        self._release(k, h, item, now, f"{item} succeeded")
                elif ok is False:
                    self.fails[k] = [*self.fails.get(k, []), (now, item)][-KEPT:]
                    if probe:
                        h["backoff"] = min(h["backoff"] * 2, MOST)
                        h["at"] = now + h["backoff"]
                        self.e.p.events.add(PROBED, item=b.name, source=SOURCE, causedby=h["event"]["id"], data={
                            "block": b.name, "field": k[1], "value": k[2], "item": item, "ok": False,
                            "backoff": h["backoff"], "probe_at": h["at"]})
                        self.e.say(f"{b.name}: the probe {item} failed: {k[1]}={k[2]} stays held, probed again in "
                                   f"{h['backoff']:g}s")

    def _release(self, k: tuple, h: dict, item: str | None, now: float, why: str) -> None:
        since = _num(h["event"]["data"].get("began"), h["event"]["time"])
        self.e.p.events.add(RELEASED, item=k[0], source=SOURCE, causedby=h["event"]["id"], data={
            "block": k[0], "field": k[1], "value": k[2], "item": item, "why": why, "since": since, "until": now,
            "held": round(max(0.0, now - since), 1)})
        self.on.pop(k, None)
        self.e.say(f"{k[0]}: {k[1]}={k[2]} released: {why} (held {(now - since) / 60:.1f} min)")
