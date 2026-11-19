"""``ergostat impact BLOCK|CHANGE``: the impact report of a fix or a change (SPEC §12n), in the terminal."""

from __future__ import annotations

import sys
import time
from types import SimpleNamespace

from ..durations import DurationError, human, parse_duration
from ..show import c, table
from .common import at_of, open_project, out_json
from .numbers import sig


def _when(t: float | None, now: float) -> str:
    return "–" if t is None else "now" if abs(t - now) < 1 else f"+{human(t - now)} ({time.strftime('%a %H:%M', time.localtime(t))})"


def cmd_impact(args) -> int:
    from ..numbers import impact as im
    p = open_project(args)
    try:
        since = at_of(SimpleNamespace(at=args.since)) if getattr(args, "since", None) else None
        r = im.report(p, args.name, since, at=at_of(args),
                      within=parse_duration(args.within, "--within") if args.within else None, times=args.times,
                      penalty=parse_duration(args.penalty, "--penalty") / 3600.0 if args.penalty else None,
                      tests=args.tests, commit=args.commit, runs=args.runs, budget=args.budget)
    except (im.ImpactError, DurationError) as e:
        print(str(e), file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        return out_json(r)
    now = r["at"]
    print(c(r["said"], "bold"))
    for x in r["notes"] + ([r["stopped"]] if r["stopped"] else []):
        print(c(f"  {x}", "dim"))
    if r["broken"]:
        print(c("\nwhat broke", "bold"))
        for x in r["broken"]["flows"]:
            print(f"  {x['said']}")
        for s in r["broken"]["stocks"]:
            up = c("  building up", "warn") if s["building"] else ""
            print(f"  {s['ref'][6:]}: {sig(s['at_failure'])} when it began, {sig(s['now'])} now{up}")
    print(c(f"\ngoals, projected {human(r['horizon'])} ahead with the loops running", "bold"))
    fix = ("AS IT IS", "WITH IT") if r["kind"] == "change" else ("WITHOUT THE FIX", "FIXED NOW")
    print(table(["GOAL", "HOLDS", f"OFF {fix[0]}", "TIME OFF", fix[1], "RISK"],
                [[g, f"{x['of']} {x['hold']}", _when(x["off_at"], now), human(x["hours_off"] * 3600) if x["hours_off"] else "",
                  human(x.get("hours_off_fixed_now", 0) * 3600) if x.get("hours_off_fixed_now") else "", x.get("said") or ""]
                 for g, x in r["goals"].items()], "the model has no goals"))
    ro = r["rollout"]
    if ro:
        print(c(f"\nrolling it out (a busy hour costs {human(ro['penalty'] * 3600)})", "bold"))
        print(table(["ROLL OUT", "GOAL-OFF", "PEAK", "MOVED", "RECOVERS IN", "BUSY", "COST"],
                    [[_when(o["at"], now) + (" *" if o is ro["best"] or o["at"] == ro["best"]["at"] else ""),
                      human(o["hours_off"] * 3600) if o["hours_off"] else "0", "" if o["peak"] is None else f"{o['peak']:.3g}",
                      f"{o['moved']:.3g}",
                      "–" if o["recovery"] is None else human(o["recovery"] * 3600), f"{o['busy']:.0%}", f"{o['cost']:.3g}h"]
                     for o in ro["options"]], ""))
        print(f"  {ro['said']}")
    f = r["fields"]
    t = f["touches"]
    print(c("\nchange management", "bold"))
    print(f"  touches     blocks: {', '.join(t['blocks']) or '–'}; goals: {', '.join(t['goals']) or '–'}; "
          f"commands: {', '.join(t['commands']) or '–'}")
    print(f"  writes      {'nothing: read-only' if f['read_only'] else ', '.join(f'{a['name']} ({a['gate']})' for a in t['actions'])}")
    print(f"  rollback    {f['rollback']['said']}")
    print(f"  risk        {f['risk']['level']}: {'; '.join(f['risk']['why'])}")
    print(f"  confidence  {f['confidence']['said']}")
    for x in f["confidence"]["parts"]:
        fit = f", R² {x['r2'] or 0:.2f}, skill {x['skill']:.2f}" if x.get("skill") is not None else ""
        print(c(f"              {x['ref']}: {x['how']}{fit}", "dim"))
    return 0
