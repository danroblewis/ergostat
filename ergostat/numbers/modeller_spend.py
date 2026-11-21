"""The AI tier's spend ledger (SPEC §12e): its daily cap, checked before every call and held through it.

``<p.dir>/modelling/ai-spend.jsonl``, appended under an ``fcntl`` lock on ``ai-spend.lock`` (as ``repair/fix.py
ledger``). Rows: ``{"id", "time", "reserved"}`` before a call, ``{"id", "usd", "estimated"?}`` after it, and
``{"refused", "reserved"}`` when the cap stopped one (read by the status line; the spend ignores it). An id is charged
its settled ``usd``, or its whole ``reserved`` until it is settled, and is dated only by its reservation's time, so a
settle row never enters or leaves the day on its own. A ledger that cannot be read means no call (it fails closed)."""

from __future__ import annotations

import contextlib
import fcntl
import json
import math
import time
import uuid
from pathlib import Path

DAY = 86400.0


class Capped(Exception):
    """No call: the cap, or a ledger that cannot be read (``unreadable``); the message says which."""

    def __init__(self, why: str, unreadable: bool = False):
        super().__init__(why)
        self.unreadable = unreadable


def _dir(p) -> Path:
    d = Path(p.dir) / "modelling"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _amount(x) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


def _bad(s: str):
    raise ValueError(f"not a number: {s}")


def rows(p, partial_ok: bool = False) -> list[dict]:
    """Every row, checked; ``Capped(unreadable)`` on any it cannot read. ``partial_ok``: a last line still being
    written (no newline yet) is left out, for a reader that does not hold the lock."""
    path = _dir(p) / "ai-spend.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
        if partial_ok and lines[-1]:
            lines = lines[:-1]
        out, seen = [], set()
        for n, line in enumerate(lines, 1):
            if not line and n == len(lines):
                continue
            r = json.loads(line, parse_constant=_bad)
            if not isinstance(r, dict):
                raise ValueError(f"line {n} is not a row")
            if "refused" in r:
                ok = _amount(r.get("refused")) and _amount(r.get("reserved"))
            elif "reserved" in r:
                ok = isinstance(r.get("id"), str) and _amount(r.get("time")) and _amount(r["reserved"])
            else:
                ok = isinstance(r.get("id"), str) and _amount(r.get("usd"))
            key = (r.get("id"), "reserved" in r)
            if not ok or ("refused" not in r and key in seen):
                raise ValueError(f"line {n}: {line[:120]}")
            seen.add(key)
            out.append(r)
        return out
    except (OSError, UnicodeError, ValueError) as e:
        raise Capped(f"the AI tier's spend ledger cannot be read ({e}): no AI call", unreadable=True) from None


def spent(p, now: float | None = None, got: list[dict] | None = None) -> float:
    """The day's spend: each id reserved within the last day, at its settled ``usd`` or else its whole reservation."""
    now = time.time() if now is None else now
    got = rows(p) if got is None else got
    settled = {r["id"]: r["usd"] for r in got if "usd" in r and "id" in r}
    return round(sum(settled.get(r["id"], r["reserved"]) for r in got
                     if "id" in r and "reserved" in r and r["time"] > now - DAY), 6)


def _append(path: Path, row: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


@contextlib.contextmanager
def held(p, reserved: float, daily: float):
    """One call within the cap: under the lock, the day's spend read, the call refused (``Capped``) if it plus
    ``reserved`` would pass ``daily``, else reserved, made (the body; it appends the call's cost dict to the list it is
    given) and settled, and only then the lock let go. A body that raises leaves its whole reservation charged."""
    if not (isinstance(reserved, int | float) and math.isfinite(reserved) and reserved > 0):
        raise Capped(f"this call's reservation (${reserved}) is not a positive amount: no AI call")
    d = _dir(p)
    with open(d / "ai-spend.lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        s = spent(p)
        if s + reserved > daily:
            _append(d / "ai-spend.jsonl", {"refused": time.time(), "reserved": reserved})
            raise Capped(f"the AI tier has spent ${s:.4f} of its ${daily:.2f} today; this call's ${reserved:.4f} "
                         "reservation would pass it: no AI call")
        i = uuid.uuid4().hex
        _append(d / "ai-spend.jsonl", {"id": i, "time": time.time(), "reserved": reserved})
        box: list[dict] = []
        yield box
        got = box[0] if box else {"usd": reserved, "estimated": True}
        usd = got.get("usd")
        _append(d / "ai-spend.jsonl", {"id": i, "usd": usd if _amount(usd) else reserved,
                                       **({"estimated": True} if got.get("estimated") or not _amount(usd) else {})})


def today(p, now: float | None = None) -> dict:
    """For the status line, without the lock: ``{"spent", "refused", "last"}`` (a refusal within the day; the latest
    reservation asked for), or ``{"unreadable": why}``."""
    now = time.time() if now is None else now
    try:
        got = rows(p, partial_ok=True)
    except Capped as e:
        return {"unreadable": str(e)}
    asked = [r["reserved"] for r in got if "reserved" in r]
    return {"spent": spent(p, now, got), "refused": any(r["refused"] > now - DAY for r in got if "refused" in r),
            "last": asked[-1] if asked else None}
