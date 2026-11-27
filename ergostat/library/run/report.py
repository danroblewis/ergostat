"""A report on a schedule: its clock (a sensor), its writer (a block), and a free report of the model (the
stand-in renderer).

    due --projection K --cron EXPR              1 when a scheduled time has passed since the newest report, else 0
    report --projection K --cron EXPR [--render CMD] [--folder reports] [--title T] [--flow flow.x]
    summary                               the model now, as Markdown: the goals off, then every projection's items by state

The writer runs the renderer (given the block's input on standard input) and keeps what it prints, as Markdown, in
``<folder>/<K>-<when>.md`` (``when``: the scheduled time it is for, to the day for a daily schedule, else to the
minute), then records the item ``K/<when>`` (``K.written``, with ``report: file:...``)."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from .common import block_input, items, note, project, root, say

DAY = 86400.0


def newest(p, kind: str) -> float | None:
    its = items(p, kind)
    return max((i.first for i in its), default=None)


def fire_since(cron: str, since: float, t: float) -> float | None:
    """The latest scheduled time in (since, t], if any."""
    from ...cron import Cron
    c = Cron(cron)
    got, x = None, since
    for _ in range(2000):                 # (a schedule of every minute over a day and a half at most)
        nx = c.next_after(x)
        if nx > t:
            break
        got, x = nx, nx
    return got


def stamp(cron: str, at: float) -> str:
    daily = cron.split()[0].isdigit() and cron.split()[1].isdigit()
    return datetime.fromtimestamp(at).strftime("%Y-%m-%d" if daily else "%Y-%m-%dT%H-%M")


def due(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="due")
    ap.add_argument("--projection", dest="kind", required=True)
    ap.add_argument("--cron", required=True)
    a = ap.parse_args(argv)
    t = time.time()
    last = newest(project(), a.kind)
    since = max(last if last is not None else t - DAY, t - 1.5 * DAY)
    print(1 if fire_since(a.cron, since, t) is not None else 0)
    return 0


def summary(argv: list[str]) -> int:
    from ...spec.explain import Explainer
    p = project()
    spec = p.model.spec
    e = Explainer(spec, p)
    out = [f"# {spec.name}: {datetime.now().strftime('%A %d %B %Y, %H:%M')}", ""]
    off = [g for g in spec.goals if e.status.get(g) == "off"]
    out += ["## Goals off", ""] + ([f"- **{g}**: {spec.goals[g].description or spec.goals[g].of} "
                                    f"(now {e.signals.get(str(spec.goals[g].of))}, wanted {spec.goals[g].hold})"
                                    for g in off] or ["- none: every goal holds"]) + [""]
    out += ["## Items", ""]
    from ...spec import items as its
    for k in spec.items:
        if k.startswith("ergostat."):
            continue
        got = its.project(p.events, spec, k)
        if not got:
            continue
        by: dict = {}
        for i in got:
            by[i.state or "-"] = by.get(i.state or "-", 0) + 1
        out.append(f"- {k}: " + ", ".join(f"{n} {s}" for s, n in by.items()))
    print("\n".join(out))
    return 0


def report(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="report")
    ap.add_argument("--projection", dest="kind", required=True)
    ap.add_argument("--cron", required=True)
    ap.add_argument("--render", default="")
    ap.add_argument("--folder", default="reports")
    ap.add_argument("--title", default="")
    ap.add_argument("--flow")
    ap.add_argument("--timeout", type=float, default=300.0)
    a = ap.parse_args(argv)
    given = block_input()
    t = time.time()
    p = project()
    last = newest(p, a.kind)
    at = fire_since(a.cron, max(last if last is not None else t - DAY, t - 1.5 * DAY), t) or t
    when = stamp(a.cron, at)
    if a.render.strip():
        r = subprocess.run(a.render, shell=True, input=json.dumps(given), capture_output=True, text=True, timeout=a.timeout)
        if r.returncode != 0:
            note(f"the renderer exited {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}")
            say({"out": a.flow, "moved": 0} if a.flow else {"moved": 0})
            return 1
        text = r.stdout
    else:
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            summary([])
        text = buf.getvalue()
    folder = root() / a.folder
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / f"{a.kind}-{when}.md"
    f.write_text(text, encoding="utf-8")
    rel = f.relative_to(root()) if f.is_relative_to(root()) else Path(f)
    say({"event": f"{a.kind}.written", "item": f"{a.kind}/{when}",
         "data": {"report": f"file:{rel}", "title": a.title or f"{a.kind} {when}", "for": round(at, 3),
                  "chars": len(text)}})
    say({"out": a.flow, "moved": 1} if a.flow else {"moved": 1})
    return 0
