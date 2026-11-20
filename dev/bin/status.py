"""One screen of the factory for the coordinator, from its record; run in the instance's folder.

    status.py      in flight, blocked (on what), failed (why), the queue, research, proposed lessons, spend today and
                   first-pass yield
    status.py session GAP [ROLE] [N]
                   a session's conversation (run/sessions/, sessions.py): each message, each tool call with its input
                   summarised, each result cut short. Without N, the role's latest; without ROLE, the gap's sessions
                   listed and its latest shown"""

from __future__ import annotations

import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import measure  # noqa: E402
import resources  # noqa: E402
import sessions  # noqa: E402

FLIGHT = ("planned", "building", "in-review", "queued")
WAITING = ("open", "replan", "ready", "fix", "built", "approved")


def since(t) -> str:
    h = (time.time() - float(t or 0)) / 3600
    return "" if not t else f"{h * 60:.0f}m" if h < 1 else f"{h:.1f}h"


def first(text) -> str:
    return (str(text or "").strip().splitlines() or [""])[0][:90]


def blocked_on(g: dict, by: dict) -> str:
    f = g["fields"]
    kids = [i for i, x in by.items() if g["id"] in fac.ids(x["fields"].get("parent"))] if g["state"] == "split" else []
    waits = [d for d in [*fac.ids(f.get("depends_on")), *kids] if by.get(d, {}).get("state") != "merged"]
    research = [r for r in f.get("research") or [] if g["state"] in ("open", "replan")]
    return "; ".join(x for x in (f.get("blocked_reason"), ", ".join(f"{d} ({by.get(d, {}).get('state', 'unknown')})"
                                                                     for d in waits), ", ".join(research)) if x)


def session(cfg: dict, args: list[str]) -> int:
    if not args or len(args) > 3 or (len(args) == 3 and not args[2].isdigit()):
        print("usage: status.py session GAP [ROLE] [N]", file=sys.stderr)
        return 2
    found = sessions.find(cfg, args[0], args[1] if len(args) > 1 else None, int(args[2]) if len(args) > 2 else None)
    if not found:
        print(f"no session of {' '.join(args)} in {fac.rel(fac.run_dir(cfg, 'sessions'))}/", file=sys.stderr)
        return 1
    if len(args) == 1:
        print("\n".join(f"  {p.stem}  ({p.stat().st_size // 1024} KB)" for p in found) + "\n")
    print(sessions.readable(found[-1]))
    return 0


def main() -> int:
    cfg = fac.config()
    if sys.argv[1:2] == ["session"]:
        return session(cfg, sys.argv[2:])
    fac.cli(cfg)
    gaps = fac.items("gap")
    by = {g["id"]: g for g in gaps}
    out = []

    def section(title: str, rows: list[str]) -> None:
        out.append(f"{title} ({len(rows)})")
        out.extend(rows[:12] + ([f"  ... and {len(rows) - 12} more"] if len(rows) > 12 else []) or ["  -"])

    section("In flight", [f"  {g['id']:<40} {g['state']:<10} {since((g['fields'].get('lease') or {}).get('taken'))}"
                          for g in gaps if g["state"] in FLIGHT])
    live = [g for g in gaps if g["state"] not in ("merged", "parked")]
    section("Blocked", [f"  {g['id']:<40} waits on {w}" for g in live if (w := blocked_on(g, by))])
    why = lambda f: f.get("where_it_stopped") or f.get("last_error") or f.get("findings")  # noqa: E731
    section("Failed", [f"  {g['id']:<40} {g['state']:<12} {first(why(g['fields']))}"
                       for g in gaps if g["state"] in ("parked", "queue-failed", "dead")])
    section("Queue", [f"  {s:<9} {len(n)}: {', '.join(n[:6])}{' ...' if len(n) > 6 else ''}"
                      for s in WAITING if (n := [g["id"][4:] for g in gaps if g["state"] == s])])
    research = fac.items("research")
    section("Research", [f"  {r['id']:<40} {r['state']:<9} {first(r['fields'].get('summary') or r['fields'].get('question'))}"
                         for r in sorted(research, key=lambda r: r["state"] == "answered")])
    section("Lessons proposed (ergostat inbox)", [f"  {x['id']:<40} {first(x['fields'].get('text') or x['fields'].get('name'))}"
                                                  for x in fac.items("lesson", "proposed")])
    try:
        fpy = f"{measure.reading('first-pass-yield'):.0%}"
    except SystemExit:
        fpy = "no value yet"
    try:
        spend = f"${fac.spent_today(cfg):.2f} of ${fac.daily_cap():g}"
    except Exception as e:  # noqa: BLE001 - said, as the sessions would refuse
        spend = f"cannot be told ({type(e).__name__}: {e}): sessions refuse"
    out.append(f"Spend today {spend}; first-pass yield (14 days) {fpy}")
    try:
        out.append(resources.line(cfg))
    except Exception as e:  # noqa: BLE001 - said, as the gates would hold
        out.append(f"Resources cannot be told ({type(e).__name__}: {e}): the gates hold new sessions")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
