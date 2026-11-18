"""The event collector: a sensor on an arrival flow.

    collect --name INST --kind K [--command CMD | --url URL | --stand-in RATE] [--id-field id] [--event arrived]
            [--event-field event] [--cursor-field F] [--path a.b] [--header 'K: V'] [--field F] [--changes] [--window 10m]

Each poll reads records (a JSON array, an object holding one under ``--path``, or one JSON object per line) from
the command (run in the project's folder, the cursor in ``$ERGOSTAT_CURSOR``), the URL (``{cursor}`` in it
replaced; headers may name environment variables, ``Authorization: Bearer $TOKEN``) or, given neither, the stand-in (a
feed made up at RATE records an hour, free and offline). Each record is about the item ``K/<its id>``; it is said once, as
``K.<its event-field, or --event>`` with the record as its data, and never again (de-duplicated by id and event,
the last 20,000 kept), unless ``--changes`` and the record changed (``K.changed``). With ``--cursor-field`` only
records past the greatest cursor seen are taken. The number printed last is the new items per hour over
``--window`` (what the flow's rate is)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import urllib.parse
import urllib.request

from .common import kept, note, now, say

KEEP = 20000


def records_of(text: str, path: str | None) -> list[dict]:
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        data = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    data.append(json.loads(line))
                except ValueError:
                    note(f"not JSON: {line[:120]}")
    for k in (path.split(".") if path else []):
        data = data.get(k) if isinstance(data, dict) else None
    if isinstance(data, dict):
        data = next((data[k] for k in ("items", "data", "results", "records", "values") if isinstance(data.get(k), list)),
                    [data])
    return [r for r in (data or []) if isinstance(r, dict)]


def from_command(cmd: str, cursor, timeout: float) -> str:
    env = {**os.environ, "ERGOSTAT_CURSOR": "" if cursor is None else str(cursor)}
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env)
    if p.returncode != 0:
        raise SystemExit(f"the source exited {p.returncode}: {(p.stderr or p.stdout).strip()[:300]}")
    return p.stdout


def from_url(url: str, cursor, headers: list[str], timeout: float) -> str:
    url = url.replace("{cursor}", urllib.parse.quote("" if cursor is None else str(cursor)))
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ergostat-collect"})
    for h in headers:
        k, _, v = h.partition(":")
        req.add_header(k.strip(), os.path.expandvars(v.strip()))
    with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 (the owner's own URL)
        return r.read().decode("utf-8", "replace")


WHO = ["ana", "ben", "chen", "dee", "eli", "fay"]
WHAT = ["can you look at", "question about", "please review", "help with", "status of", "a note on"]
TOPIC = ["the build", "search", "the release", "the dashboard", "billing", "the docs", "the on-call rota"]


def stand_in(mem: dict, kind: str, rate: float, answer_after: float | None) -> list[dict]:
    """A made-up feed: about ``rate`` new records an hour (at least one on the first poll), each answered after
    about ``answer_after`` seconds when given (a record with ``event: answered``)."""
    t = now()
    s = mem.setdefault("stand_in", {"n": 0, "last": t - 3600.0 / max(rate, 1e-9), "owed": 0.0, "open": {}})
    s["owed"] += (t - s["last"]) * rate / 3600.0
    s["last"] = t
    out = []
    rnd = random.Random(int(t * 1000))
    while s["owed"] >= 1.0:
        s["owed"] -= 1.0
        s["n"] += 1
        n = s["n"]
        out.append({"id": str(n), "title": f"{rnd.choice(WHAT)} {rnd.choice(TOPIC)}", "from": rnd.choice(WHO),
                    "at": round(t, 3), "stand_in": True})
        if answer_after:
            s["open"][str(n)] = t + answer_after * (0.5 + rnd.random())
    for i, due in list(s["open"].items()):
        if due <= t:
            out.append({"id": i, "event": "answered", "at": round(t, 3), "stand_in": True})
            del s["open"][i]
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="collect")
    ap.add_argument("--name", required=True)
    ap.add_argument("--kind", required=True)
    ap.add_argument("--command", help="the source: a command printing records")
    ap.add_argument("--url", help="the source: an HTTP endpoint answering with records")
    ap.add_argument("--stand-in", type=float, default=120.0, metavar="RATE",
                    help="with neither: a made-up feed of about RATE records an hour")
    ap.add_argument("--answer-after", type=float, help="the stand-in's records are answered after about this many seconds")
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--event", default="arrived")
    ap.add_argument("--event-field", default="event")
    ap.add_argument("--cursor-field")
    ap.add_argument("--path")
    ap.add_argument("--header", action="append", default=[])
    ap.add_argument("--field", action="append", default=[], help="a record's field to keep (each one; default: all)")
    ap.add_argument("--changes", action="store_true")
    ap.add_argument("--window", type=float, default=600.0, help="seconds")
    ap.add_argument("--timeout", type=float, default=25.0)
    a = ap.parse_args(argv)
    keep_fields = [f.strip() for x in a.field for f in x.split(",") if f.strip()] or None
    with kept(a.name, "collect") as mem:
        cursor = mem.get("cursor")
        if not a.command and not a.url:
            recs = stand_in(mem, a.kind, a.stand_in, a.answer_after)
        else:
            try:
                text = from_command(a.command, cursor, a.timeout) if a.command else from_url(a.url, cursor, a.header, a.timeout)
            except (OSError, subprocess.TimeoutExpired) as e:   # (urllib's errors are OSErrors)
                why = getattr(e, "reason", None) or getattr(e, "code", None) or e
                raise SystemExit(f"cannot read {a.url or a.command}: {why}") from None
            recs = records_of(text, a.path)
        seen: dict = mem.setdefault("seen", {})
        arrivals: list = mem.setdefault("arrivals", [])
        t = now()
        for r in recs:
            rid = r.get(a.id_field)
            if rid is None or str(rid) == "":
                note(f"a record with no {a.id_field}: {json.dumps(r)[:120]}")
                continue
            rid = str(rid).replace(" ", "-")
            if a.cursor_field and r.get(a.cursor_field) is not None:
                c = r[a.cursor_field]
                if cursor is not None and _le(c, cursor):
                    continue
            ev = str(r.get(a.event_field) or a.event) if a.event_field else a.event
            data = {k: v for k, v in r.items() if k != a.event_field and (keep_fields is None or k in keep_fields)}
            digest = hashlib.sha1(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:12]
            key = f"{rid} {ev}"
            if key in seen:
                if a.changes and seen[key] != digest:
                    say({"event": f"{a.kind}.changed", "item": f"{a.kind}/{rid}", "data": data})
                    seen[key] = digest
                continue
            seen[key] = digest
            say({"event": f"{a.kind}.{ev}", "item": f"{a.kind}/{rid}", "data": data})
            if ev == a.event:
                arrivals.append(t)
        if a.cursor_field:
            cs = [r[a.cursor_field] for r in recs if r.get(a.cursor_field) is not None]
            if cs:
                top = max(cs, key=_key)
                mem["cursor"] = top if cursor is None or not _le(top, cursor) else cursor
        if len(seen) > KEEP:
            for k in list(seen)[: len(seen) - KEEP]:
                del seen[k]
        arrivals[:] = [x for x in arrivals if x > t - a.window]
        print(round(len(arrivals) * 3600.0 / a.window, 6))
    return 0


def _key(x):
    try:
        return (0, float(x), "")
    except (TypeError, ValueError):
        return (1, 0.0, str(x))


def _le(a, b) -> bool:
    return _key(a) <= _key(b)
