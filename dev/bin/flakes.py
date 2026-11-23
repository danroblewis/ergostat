"""The one writer of a flake's state (flake.seen, flake.main-broken, flake.fixed): each write decided on the item as it
stands, read again under one lock (run/flakes.lock), and recorded at once with `ergostat event --add`, so a test still
failing on main stays main-broken, a second break keeps the first repair clock, a flake fixed then seen again starts
anew, and a seen flake is fixed after `[gates] flake_fixed_after` green queue runs in a row that say it PASSED."""

from __future__ import annotations

import fcntl
import json
import sys
from contextlib import contextmanager

import fac

REMAKE_CLEARS = ("main_fixed_at", "fixed_by", "fixed_on", "green_passes")   # a fixed flake seen again: its old fields
GREEN_MOST = 50                                    # seen flakes read per green run, and flake_fixed_after's ceiling


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
            {"op": "remove", "path": f"/{k}"} for k in REMAKE_CLEARS if k in fields and k not in new]
    return event, "data", data


def say(event: str, test: str, as_: str | None = None, **data) -> str:
    """``event`` (flake.seen or flake.main-broken) about flake/<test>, written as plan() decides; the event written."""
    iid = f"flake/{fac.slug(test, 80)}"
    data |= {"green_passes": 0} if event == "flake.seen" else {}   # (seen again: the green runs counted anew)
    with held():
        wrote, form, value = plan(event, read(iid), {"test": test, **data})
        fac.ergostat("event", "--add", wrote, "--item", iid, f"--{form}", json.dumps(value, default=str),
                     *(["--as", as_] if as_ else []))
    return wrote


def fixed_after(cfg: dict) -> int:
    """`[gates] flake_fixed_after`: the green runs in a row that fix a seen flake (default 5; 1 to GREEN_MOST, else
    refused: nothing is counted)."""
    n = (cfg.get("gates") or {}).get("flake_fixed_after", 5)
    if type(n) is not int or not 1 <= n <= GREEN_MOST:
        raise ValueError(f"[gates] flake_fixed_after: a whole number 1-{GREEN_MOST}, not {n!r}")
    return n


def outcomes(suites: dict) -> dict[str, str]:
    """Each test's outcome in a green run's unit and browser logs (fac.outcomes, on their -rp PASSED lines): fail in
    either, else pass in either. A suite not run, not green, stopped or whose log cannot be read says nothing, so its
    tests are unknown, never a pass."""
    got: dict[str, str] = {}
    for name in ("unit", "browser"):
        s = suites.get(name)
        if not isinstance(s, dict) or s.get("rc") != 0 or s.get("stopped_by") or not s.get("log"):
            continue
        try:
            with open(s["log"], errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        for t, r in fac.outcomes(text, sorted({t for _, t in fac.OUTCOME.findall(text)})).items():
            got[t] = "fail" if "fail" in (r, got.get(t)) else r
    return got


def green(suites: dict, on: str) -> list[str]:
    """After a green landing on main ``on`` (its ``suites``, each with its log): each seen flake not quarantined (at
    most GREEN_MOST, by id) whose test the logs say PASSED counts one more green run in a row (`green_passes`, a patch
    testing the value read, under the lock); at flake_fixed_after it is flake.fixed (fixed_by green-runs, fixed_on
    ``on``). Unknown or failed: unchanged (a flake.seen sets the count to 0). Returns the flakes fixed."""
    n, out, said = fixed_after(fac.config()), [], outcomes(suites)
    for it in sorted(fac.items("flake", "seen"), key=lambda x: x["id"])[:GREEN_MOST]:
        with held():
            now = read(it["id"])                       # (again, under the lock: a seen or a quarantine since)
            fields = (now or {}).get("fields") or {}
            was = fields.get("green_passes", 0)
            if not now or now.get("state") != "seen" or fields.get("quarantined") or type(was) is not int \
                    or said.get(fields.get("test")) != "pass":
                continue
            if was + 1 >= n:
                fac.ergostat("event", "--add", "flake.fixed", "--item", it["id"], "--data",
                             json.dumps({"green_passes": was + 1, "fixed_by": "green-runs", "fixed_on": on}))
                out.append(it["id"])
                continue
            fac.ergostat("event", "--add", "flake.measured", "--item", it["id"], "--patch", json.dumps(
                ([{"op": "test", "path": "/green_passes", "value": was}] if "green_passes" in fields else [])
                + [{"op": "add", "path": "/green_passes", "value": was + 1}]))
    return out
