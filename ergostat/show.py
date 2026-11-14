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
    from .state import setpoint_text
    val = f"{lp['stock']} {fmt(lp['value'])}"
    err = "" if lp["error"] in (None, 0) else (f"  off by {fmt(abs(lp['error']))}" if lp["status"] == "off"
                                                else f"  within its tolerance of {fmt(lp['tolerance'])}")
    return f"{name}  {status_word(lp['status'])}  {val}, setpoint {setpoint_text(lp)}{err}"


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
        if lp.open_loop:                                 # watched, not fed back: the controller runs on time
            a = model.agents.get(lp.controller.agent or "")
            out.append(f"  ⏲ {a.schedule if a else '?'} ─▶ {ctl} ─▶ {valves} ─▶ {stock} ─▶ {sensors} "
                       + c("watches it (open loop: nothing fed back)", "dim"))
        else:
            out.append(f"  {stock} ─▶ {sensors} ─▶ {ctl} ─▶ {valves} ─▶ {c('back to ' + lp.stock, 'dim')}")
        covered |= set(lp.flows)
        for g in lp.gaps:
            out.append("  " + c("cannot close: " + g, "warn"))
    rest = [f for f in model.flows.values() if f.name in parts and f.name not in covered]
    for title, group in (("disturbances (nothing controls them)", [f for f in rest if f.disturbance]),
                         ("flows outside any loop", [f for f in rest if not f.disturbance])):
        if group:
            out.append(c(title, "dim"))
        for f in group:
            fl = snap["flows"][f.name]
            sym = "~" if f.disturbance else "⋈"
            end = model.stocks.get(f.target or "") or model.stocks.get(f.source or "")
            unit = f" {end.unit}/h" if end and end.unit else "/h"
            rate = f"{fmt(fl['rate'])}{unit}" if fl["rate"] is not None else f"?{unit}"
            by = f" · the doing of {f.agent}" if f.disturbance and f.agent else ""
            out.append(f"  {f.source or '○'} ─{sym} {f.name} ({rate}, {fl['how']}{by})─▶ {f.target or '○'}")
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


def _sp(setpoint: str) -> str:
    return setpoint.replace("<=", "≤").replace(">=", "≥").replace("==", "=").strip()


def block_text(model, snap: dict, readings: dict, name: str) -> str:
    """One loop as a classic negative-feedback block diagram, in text:

                                               d: logs-written 757/h (est.)
                                                │
     r: ≤ 80 ─▶(Σ)─e─▶[ controller ]─u─▶[ valve ]─▶(+)─▶[ stock 65.6 % ]──┬──▶ y
                ▲−                                                         │
                └──────────────── ym ────[ sensor reads 65.6 ]◀────────────┘
    """
    lp = model.loop(name)
    s = snap["loops"][name]
    c_ = lp.controller
    ctl = f"[ {name} · {model.agents[c_.agent].kind if c_.agent in model.agents else 'unfilled'} ]"
    v = lp.valves[0] if lp.valves else None
    pos = readings.get(f"valve/{v}") if v else None
    mx = model.valves[v].max if v else None
    lim = f" ≤ {fmt(mx)} a run" if mx else ""
    vb = (f"[ {v}{lim} ]" if pos is None else f"[ {v} open {fmt(pos)}{lim} ]") if v else "[ no valve ]"
    st = snap["stocks"].get(lp.stock, {})
    unit = model.stocks[lp.stock].unit if lp.stock in model.stocks else ""
    sb = f"[ ∫ {lp.stock} {fmt(st.get('value'))}{(' ' + unit) if unit else ''} ]"
    on_stock = [x for x in lp.sensors if model.sensors[x].measures == lp.stock]
    sen = (on_stock or lp.sensors or [None])[0]                       # H: the sensor on the stock itself
    hb = f"[ {sen} reads {fmt(readings.get(sen))} ]" if sen else "[ no sensor ]"
    # to a loop, any flow of its stock it does not drive is a disturbance: declared ones, and other
    # agents' valves; an inflow joins the plant with +, an outflow with −
    dists = [f for f in model.flows_of(lp.stock) if f.name not in lp.flows and lp.stock in (f.target, f.source)]
    dists.sort(key=lambda f: f.target != lp.stock)
    r = f"r: {_sp(c_.setpoint)} "
    e = f"e={fmt(s['error'])}" if s.get("error") is not None else "e"
    u = "u" if pos is None else f"u={fmt(pos)}"
    if lp.open_loop:                                     # time drives it: nothing compared, nothing fed back
        a = model.agents.get(c_.agent or "")
        r = f"t: {a.schedule if a else 'its schedule'} "
        left = f"{r}─▶{ctl}─{u}─▶{vb}─▶"
    else:
        left = f"{r}─▶(Σ)─{e}─▶{ctl}─{u}─▶{vb}─▶"
    drains = bool(v) and model.flows[model.valves[v].flow].source == lp.stock
    dsign = ("+" if dists[0].target == lp.stock else "−") if dists else ""
    joint = (f"({'−' if drains else '+'}{dsign})─▶") if (dists or drains) else ""
    row = left + joint + sb + "──┬──▶ y"
    sum_at = len(r) + 3                                  # the column of Σ
    tee = len(row) - len("┬──▶ y")
    lines = []
    if dists:
        d = dists[0]
        rate = snap["flows"].get(d.name, {})
        col = len(left) + 1
        v = model.valve_of(d.name)
        source = next((x.name for x in model.loops() if v and v.name in x.valves), None)
        who = f" (u of loop {source}, measured)" if source else f" (valve {v.name} · {v.agent})" if v and v.agent else ""
        lines.append(" " * col + f"d: {d.name}{who} {fmt(rate.get('rate'))}{(' ' + unit) if unit else ''}/h"
                     + (" (est.)" if rate.get("estimated") else "") + f" ({dsign})"
                     + (f" +{len(dists) - 1} more" if len(dists) > 1 else ""))
        lines.append(" " * (col + 2) + "│")
    # feedforward: a sensor the controller reads on a disturbance, acting before d shows in e
    ff = [x for x in c_.reads if x in model.sensors and any(model.sensors[x].measures == d.name for d in dists)]
    if ff and not lp.open_loop:
        lines.insert(0, " " * (sum_at + 4) + f"feedforward: {ff[0]} reads {fmt(readings.get(ff[0]))}/h now ─▶ C")
    lines.append(row)
    if lp.open_loop:
        watched = f"ym ─── {hb}◀"
        pad = max(tee - 2 - len(watched), 2)
        lines.append(" " * tee + "│")
        lines.append(" " * 2 + watched + "─" * pad + "┘")
        lines.append(" " * 2 + f"(watched against r: {_sp(c_.setpoint)}, not fed back)")
        head = f"loop {name}  {status_word(s['status'])}  open loop"
        return head + "\n" + "\n".join("  " + x for x in lines)
    lines.append(" " * sum_at + "▲−" + " " * (tee - sum_at - 2) + "│")
    mid = " ym "
    inner = tee - sum_at - 1
    body = mid + "─" * 4 + hb + "◀"
    pad = max(inner - len(body), 2)
    lines.append(" " * sum_at + "└" + "─" * (pad // 2) + body + "─" * (pad - pad // 2) + "┘")
    head = f"loop {name}  {status_word(s['status'])}"
    return head + "\n" + "\n".join("  " + x for x in lines)
