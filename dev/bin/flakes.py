"""The one writer of a flake's state (flake.seen, flake.main-broken): each write decided on the item as it stands, read
again under one lock (run/flakes.lock), and recorded at once with `ergostat event --add`, so a test still failing on
main stays main-broken, a second break keeps the first repair clock, and a flake fixed then seen again starts anew."""

from __future__ import annotations

import fcntl
import json
import sys
from contextlib import contextmanager

import fac

REMAKE_CLEARS = ("main_fixed_at", "fixed_by", "green_passes")   # a fixed flake seen again: its old life's fields


@contextmanager
def held():
    with open(fac.run_dir(fac.config()) / "flakes.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def read(iid: str) -> dict | None:
    """The item as the record has it; {} when there is none yet; None when it cannot be read (said on stderr)."""
    r = fac.ergostat("item", iid, "--json", check=False)
    if r.returncode and r.stderr.strip().startswith("no item"):
        return {}
    try:
        if r.returncode:
            raise ValueError(f"exit {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}")
        return json.loads(r.stdout)
    except ValueError as e:
        print(f"flakes: {iid} could not be read ({e}); written as said", file=sys.stderr)
        return None


def plan(event: str, item: dict | None, data: dict) -> tuple[str, str, object]:
    """(the event to write, its form: data or patch, its value), from what was said and the item as it stands."""
    state, fields = (item or {}).get("state"), (item or {}).get("fields") or {}
    if state == "main-broken" and event == "flake.seen":
        return "flake.measured", "data", data                       # counted; still main's
    if state == "main-broken" and event == "flake.main-broken":
        return event, "data", {k: v for k, v in data.items() if k != "main_broken_at"}   # the first clock kept
    if state == "fixed":                                          # made again: a new count, its fixed fields gone
        new = {**data, "times": 1}
        return event, "patch", [{"op": "add", "path": "/" + k.replace("~", "~0").replace("/", "~1"),
                                 "value": sorted(set(v)) if isinstance(v, list) else v} for k, v in new.items()] + [
            {"op": "remove", "path": f"/{k}"} for k in REMAKE_CLEARS if k in fields]
    return event, "data", data


def say(event: str, test: str, as_: str | None = None, **data) -> str:
    """``event`` (flake.seen or flake.main-broken) about flake/<test>, written as plan() decides; the event written."""
    iid = f"flake/{fac.slug(test, 80)}"
    with held():
        wrote, form, value = plan(event, read(iid), {"test": test, **data})
        fac.ergostat("event", "--add", wrote, "--item", iid, f"--{form}", json.dumps(value, default=str),
                     *(["--as", as_] if as_ else []))
    return wrote
