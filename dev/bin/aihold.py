"""The AI hold: a session that ends on the provider's usage-limit message ("You've hit your weekly limit · resets
Nov 25, 3pm (UTC)") holds every AI role, factory-wide, until the reset it names (run/ai_hold.json). Its run is given
back uncounted (fac.session raises Limited), never an attempt, a kill-rule count, a park or a dead letter. While the
hold stands no AI-role lease is taken (the goal ai-not-held closes the -when blocks; fac.ai_holds gives back a run that
took one in the sensor's lag); the merge queue and the suites read neither. At the reset it lifts by itself: each held
item was put off till then, and is taken again in its block's order. A reset time that cannot be read holds for
UNREAD_HOLD and says so (the next session after it finds the limit again, or not); a hold file that cannot be read
holds too, never "no hold".

    aihold.py held        1 while the hold stands (or its file cannot be read), else 0 (the sensor)"""

from __future__ import annotations

import fcntl
import json
import math
import re
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import fac

UNREAD_HOLD = 3600.0                   # seconds held when the reset time cannot be read
MOST_DAYS = 8                          # a reset farther off than this is a misreading (a weekly limit's is within 7)
LIMIT = re.compile(r"you(?:'|’| ha)ve hit your [\w -]*limit", re.I)
RESETS = re.compile(r"resets\s+(?:(?P<mon>[A-Za-z]{3})[a-z]*\.?\s+(?P<day>\d{1,2}),?\s+(?:at\s+)?)?"
                    r"(?P<h>\d{1,2})(?::(?P<mi>\d{2}))?\s*(?P<ap>am|pm)?(?:\s*\((?P<tz>[^)\s]+)\))?", re.I)
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


class Limited(SystemExit):
    """The run's session stopped on the usage limit: the lease is given back uncounted (its nack printed first) and the
    run exits 0. A SystemExit, so no `except Exception` (fac.guarded, the kill rule) counts it; every finally runs."""

    def __init__(self, hold: dict):
        super().__init__(0)
        self.hold = hold


def limited(text: str, anywhere: bool = False) -> bool:
    """Whether ``text`` is the usage-limit message: a session's result that begins with it (never one that only quotes
    it, a review of this file), or, ``anywhere``, a failure's output (Claude Code's own stderr) that holds it."""
    text = str(text or "").strip()
    return bool(LIMIT.search(text) if anywhere else LIMIT.match(text))


def reset_at(text: str, now: float) -> float | None:
    """The reset time the message names, as a time; None when it cannot be read (no time, an unknown zone, a date that
    does not exist, or one farther off than MOST_DAYS)."""
    m = RESETS.search(text or "")
    if not m or not (m["ap"] or m["mi"]):
        return None
    try:
        tz = ZoneInfo(m["tz"]) if m["tz"] else datetime.now().astimezone().tzinfo
        h, mi = int(m["h"]), int(m["mi"] or 0)
        h = h % 12 + (12 if m["ap"].lower() == "pm" else 0) if m["ap"] else h
        base = datetime.fromtimestamp(now, tz)
        if m["mon"]:
            at = base.replace(month=MONTHS.index(m["mon"].lower()) + 1, day=int(m["day"]), hour=h, minute=mi,
                              second=0, microsecond=0)
            at = at.replace(year=at.year + 1) if at < base - timedelta(days=1) else at
        else:
            at = base.replace(hour=h, minute=mi, second=0, microsecond=0)
            at = at + timedelta(days=1) if at <= base else at
    except (ValueError, KeyError, OSError):                 # (ZoneInfoNotFoundError is a KeyError; a bad hour, day)
        return None
    return at.timestamp() if at.timestamp() - now <= MOST_DAYS * 86400 else None


def _file(cfg: dict):
    return fac.run_dir(cfg) / "ai_hold.json"


def held(cfg: dict, now: float | None = None) -> dict | None:
    """The hold standing now ({until, why}), or None. A file that cannot be read holds for UNREAD_HOLD from now."""
    now = time.time() if now is None else now
    p = _file(cfg)
    if not p.exists():
        return None
    try:
        h = json.loads(p.read_text())
        until = float(h["until"])
        if not math.isfinite(until):
            raise ValueError(until)
    except (OSError, ValueError, KeyError, TypeError) as e:
        return {"until": now + UNREAD_HOLD, "why": f"{p.name} cannot be read ({type(e).__name__}): held"}
    return {**h, "until": until} if until > now else None


def record(cfg: dict, said: str, now: float | None = None) -> dict:
    """One factory-wide hold till the reset ``said`` names (unreadable: UNREAD_HOLD, said so), read and written under
    the hold's lock; a hold standing to a later time is kept (never shortened)."""
    now = time.time() if now is None else now
    at = reset_at(said, now)
    why = (f"the provider's usage limit: {' '.join(said.split())[:200]}" + ("" if at is not None else
           f" (its reset time cannot be read: held {UNREAD_HOLD / 3600:g}h, and looked at again then)"))
    new = {"until": now + UNREAD_HOLD if at is None else at, "why": why, "at": now, "readable": at is not None}
    with open(fac.run_dir(cfg) / "ai_hold.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            was = held(cfg, now)
            if was and was["until"] > new["until"]:
                return was
            tmp = _file(cfg).with_suffix(".tmp")
            tmp.write_text(json.dumps(new))
            tmp.replace(_file(cfg))
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    print(f"AI held till {stamp(new['until'])}: {why}", file=sys.stderr)
    return new


def stamp(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(t))


def give_back(hold: dict, now: float | None = None) -> None:
    """The run's lease given back uncounted, put off till the hold's end."""
    now = time.time() if now is None else now
    fac.nack(f"the AI is held till {stamp(hold['until'])}: {hold['why']}",
             after=f"{max(1, math.ceil(hold['until'] - now))}s", count=False)


def stop(cfg: dict, said: str) -> None:
    """A session stopped on the limit: the hold recorded, the run's lease given back uncounted, and the run ended."""
    h = record(cfg, said)
    give_back(h)
    raise Limited(h)


def holds(cfg: dict) -> bool:
    """While the hold stands, an AI run takes no item: it gives it back uncounted, till the reset."""
    h = held(cfg)
    if h:
        give_back(h)
    return h is not None


if __name__ == "__main__":
    if sys.argv[1:] != ["held"]:
        raise SystemExit(__doc__)
    print(1 if held(fac.config()) else 0)
