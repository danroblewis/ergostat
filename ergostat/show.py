"""Text for the terminal: tables, the status, one part in detail, and a system drawn as lines."""

from __future__ import annotations

import os
import sys
import time

from .durations import human
from .state import fmt

COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
CODES = {"bad": "31", "warn": "33", "ok": "32", "dim": "2", "bold": "1", "accent": "36"}


def c(text: str, style: str) -> str:
    return f"\033[{CODES[style]}m{text}\033[0m" if COLOR and style in CODES else text


def ago(t: float | None, now: float | None = None) -> str:
    if not t:
        return "never"
    return human((now or time.time()) - t) + " ago"


def table(heads: list[str], rows: list[list[str]], empty: str = "none") -> str:
    if not rows:
        return c(empty, "dim")
    import re
    strip = re.compile(r"\033\[[0-9;]*m")
    widths = [max(len(strip.sub("", str(r[i]))) for r in [heads, *rows]) for i in range(len(heads))]

    def line(r, head=False):
        cells = []
        for i, x in enumerate(r):
            x = str(x)
            pad = widths[i] - len(strip.sub("", x))
            cells.append(x + " " * pad if i < len(r) - 1 else x)
        out = "  ".join(cells)
        return c(out, "dim") if head else out
    return "\n".join([line(heads, True), *(line(r) for r in rows)])


STATUS_STYLE = {"holding": "ok", "off": "bad", "open": "warn", "unknown": "dim"}


def status_word(s: str | None) -> str:
    return c(s or "?", STATUS_STYLE.get(s or "", "dim"))


def agent_tag(model, name: str | None) -> str:
    if not name:
        return c("unfilled", "warn")
    a = model.agents.get(name)
    return f"{name} {c('(' + a.kind + ')', 'dim')}" if a else c(f"{name} (unknown agent)", "bad")


def loop_line(lp: dict, name: str) -> str:
    val = f"{lp['stock']} {fmt(lp['value'])}"
    err = "" if lp["error"] in (None, 0) else f"  off by {fmt(abs(lp['error']))}"
    return f"{name}  {status_word(lp['status'])}  {val}, setpoint {lp['setpoint']}{err}"


def system_lines(model, snap: dict, parts: set[str]) -> str:
    """A system in text: each loop as a chain, then the flows no loop covers."""
    out = []
    covered = set()
    for lp in model.loops():
        if lp.controller.name not in parts:
            continue
        s = snap["loops"][lp.name]
        out.append(c("loop ", "dim") + loop_line(s, lp.name))
        stock = f"[{lp.stock} {fmt(snap['stocks'].get(lp.stock, {}).get('value'))}]"
        sensors = ", ".join(f"({x} · {model.sensors[x].agent or '-'})" for x in lp.sensors) or c("(no sensor)", "warn")
        ctl = f"<{lp.name} {lp.controller.setpoint} · {lp.controller.agent or '-'}>"
        valves = ", ".join(f"⋈ {v} · {model.valves[v].agent or '-'}" for v in lp.valves) or c("⋈ (no valve)", "warn")
        out.append(f"  {stock} ─▶ {sensors} ─▶ {ctl} ─▶ {valves} ─▶ {c('back to ' + lp.stock, 'dim')}")
        covered |= set(lp.flows)
        for g in lp.gaps:
            out.append("  " + c("cannot close: " + g, "warn"))
    rest = [f for f in model.flows.values() if f.name in parts and f.name not in covered]
    if rest:
        out.append(c("flows outside any loop", "dim"))
        for f in rest:
            fl = snap["flows"][f.name]
            sym = "~" if f.disturbance else "⋈"
            rate = f"{fmt(fl['rate'])}/h" if fl["rate"] is not None else "?/h"
            out.append(f"  {f.source or '○'} ─{sym} {f.name} ({rate}, {fl['how']})─▶ {f.target or '○'}")
    loose = [s for s in model.stocks if s in parts and not any(lp.stock == s for lp in model.loops())]
    if loose:
        out.append(c("stocks no loop holds: ", "dim") + ", ".join(f"{s} {fmt(snap['stocks'][s]['value'])}" for s in loose))
    return "\n".join(out) or c("nothing in this system", "dim")


def spark(points: list[tuple[float, float]], width: int = 24) -> str:
    if len(points) < 2:
        return ""
    vals = [v for _, v in points][-width:]
    lo, hi = min(vals), max(vals)
    bars = "▁▂▃▄▅▆▇█"
    if hi == lo:
        return bars[3] * len(vals)
    return "".join(bars[int((v - lo) / (hi - lo) * (len(bars) - 1))] for v in vals)
