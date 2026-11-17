"""What was turned away, remembered (SPEC §12e): a change refused at the gate (it worsens the fit), failed by the
judge, or that the judge could not tell from the model as it is (inconclusive) is not proposed again for the same
target until the record has grown enough for an estimate to say something new, or the model has changed. Each time
it is found again meanwhile, that is said on the item turned away (``repeats``, ``held_until``, ``held_back``), one
item with a count, not an item a time.

The **target** of a change is what it is a change to, and how it was found: its kind, its target (the parameters it
sets, the part it changes) and, for ergostat's own finders, the calibration or the rule that found it (a block's
proposals share one). The wait doubles with each turn-away for the same target on the same version of the model:
a quarter of the record the change was estimated on, at least ten minutes and the judge's hold-out, at most a day."""

from __future__ import annotations

import time

from ..durations import human as dur
from . import proposals as pr
from . import version as ver

HELD = ("refused", "failed", "inconclusive")
GROW = 0.25                 # the record grows by this share of the window it was found on before it is tried again
MIN_WAIT = 600.0            # ... at least this (s)
MAX_WAIT = 24 * 3600.0      # ... and at most this, however often it was turned away


def key(x: dict) -> str:
    """What a change is to, and how it was found (kept on its item as ``key`` when it is checked or turned away)."""
    if x.get("key"):
        return str(x["key"])
    kind = x.get("kind") or "structure"
    target = x.get("target") or ",".join(sorted(x.get("parts") or [])) or x.get("title") or ""
    how = x.get("code") or x.get("scope") or ("proposed" if x.get("made_by") not in (None, "ergostat", "owner") else "")
    return f"{kind}|{target}|{how}"


def key_raw(raw, by: str) -> str:
    """A block's proposal's target before it is checked: its kind and the first part it names."""
    raw = raw if isinstance(raw, dict) else {}
    parts = raw.get("parts") if isinstance(raw.get("parts"), list) else []
    return key({"kind": raw.get("kind") or "structure", "target": str(parts[0]) if parts else str(raw.get("title") or ""),
                "made_by": by})


def turned_away(x: dict) -> bool:
    """Turned away for what the record said of it: refused at the gate, failed, or inconclusive. A proposal refused
    for its form (no evidence, an edit that cannot be made, a model that does not compile) is not remembered."""
    return x.get("state") in ("failed", "inconclusive") or (x.get("state") == "refused" and bool(x.get("gated")))


def _when(x: dict) -> float:
    return float((x.get("verdict") or {}).get("at") or x.get("decided") or x.get("made") or x.get("created") or 0.0)


def held(p, spec, k: str, now: float | None = None) -> dict | None:
    """The change turned away last for this target, on this version of the model, while the record has not yet grown
    enough since: ``{"prior", "until", "wait", "times"}``; or None, it may be proposed."""
    now = now or time.time()
    v = ver.version(spec)
    mine = sorted((x for x in pr.stored(p).values() if turned_away(x) and x.get("version") == v and key(x) == k),
                  key=_when)
    if not mine:
        return None
    last = mine[-1]
    hold = getattr(spec.improve, "hold_out", 0.0) or 0.0
    base = max(MIN_WAIT, hold, GROW * float(last.get("window") or 0.0))
    wait = min(MAX_WAIT, base * 2 ** (len(mine) - 1))
    until = _when(last) + wait
    if now >= until:
        return None
    return {"prior": last, "until": until, "wait": wait, "times": len(mine)}


def said(n: int, until: float, wait: float | None = None) -> str:
    """What the item says: how often it was found again, and until when it is held back."""
    at = time.strftime("%Y-%m-%d %H:%M", time.localtime(until))
    return (f"proposed again {n} time{'s' if n != 1 else ''}, held back until {at}"
            + (f" (the record must grow by {dur(wait)} since it was turned away, or the model change)" if wait else ""))


def repeat(p, h: dict, title: str, token: str, by: str = "ergostat") -> dict:
    """The same target found again while held back: counted on the item turned away (once for each distinct
    proposal: ``token``, its title or the block's run), never a new item."""
    x = h["prior"]
    if (x.get("repeated") or {}).get("token") == token:
        return x
    n = int(x.get("repeats") or 0) + 1
    data = {"repeats": n, "held_until": h["until"], "held_back": said(n, h["until"], h["wait"]),
            "repeated": {"at": time.time(), "title": title, "by": by, "token": token}}
    pr.event(p, x["id"], x["state"], data)
    return {**x, **data}
