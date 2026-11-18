"""Free stand-ins for the world, so a template runs offline with nothing installed and no account.

    standin act [--fail SHARE]                  the item's work, pretended: prints a made-up result; fails at SHARE
    standin level --name INST --limit L         a level that creeps up: from 90% of the limit, 1% of it a second
    standin lower --name INST --limit L         the corrective action on it: takes a tenth of the limit off

Each says it is a stand-in in what it prints."""

from __future__ import annotations

import argparse
import json
import random
import sys

from .common import kept, now, say


def act(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="standin act")
    ap.add_argument("--fail", type=float, default=0.0)
    ap.add_argument("--say", default="done")
    a = ap.parse_args(argv)
    try:
        item = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        item = {}
    if random.random() < a.fail:
        print(f"stand-in: {item.get('id')} failed, as stand-ins sometimes do", file=sys.stderr)
        return 1
    title = (item.get("fields") or {}).get("title") or item.get("id") or "it"
    say({"result": f"stand-in {a.say}: {title}", "stand_in": True})
    return 0


def _level(argv: list[str], lower: bool) -> int:
    ap = argparse.ArgumentParser(prog="standin level")
    ap.add_argument("--name", required=True)
    ap.add_argument("--limit", type=float, required=True)
    ap.add_argument("--rise", type=float, default=0.01, help="the share of the limit it rises a second")
    ap.add_argument("--cut", type=float, default=0.1, help="the share of the limit one correction takes off")
    a = ap.parse_args(argv)
    t = now()
    with kept(a.name, "level") as s:
        v = float(s.get("value", a.limit * 0.9))
        v += max(0.0, t - float(s.get("at", t))) * a.rise * a.limit
        s["at"] = t
        if lower:
            cut = min(v, a.cut * a.limit)
            s["value"] = v - cut
            say({"moved": round(cut, 6), "note": "stand-in correction"})
            return 0
        s["value"] = v
    print(round(v, 6))
    return 0


def level(argv: list[str]) -> int:
    return _level(argv, False)


def lower(argv: list[str]) -> int:
    return _level(argv, True)
