"""The model behind the picture, as Markdown (``/api/export?view=dynamics|blocks``): Dynamics as a
variable table, the flows per stock and the feedback loop list; Blocks as one row per control loop.
Each is read off the answer the page draws (``/api/graph``), so its rows are the parts and loops drawn,
in the panels' own words (``dynamics.equation``, ``block_fn``'s law)."""

from __future__ import annotations

import time

from .. import sensing
from ..durations import human

TITLE = {"dynamics": "the model (system dynamics)", "blocks": "the control loops (block diagram)"}


def _cell(x) -> str:
    return " ".join(str("" if x is None else x).split()).replace("|", "\\|") or "–"


def _table(head: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head),
            *("| " + " | ".join(_cell(x) for x in r) + " |" for r in rows), ""]


def _sensed(t) -> str:
    """How a part is measured: each sensor, and how often it reads."""
    out = []
    for s in (getattr(t, "sensors", None) or {}).values():
        every = (f"every {sensing.every_words(s.every)}" if s.every else f"on cron {s.cron}" if s.cron else "")
        out.append(f"sensor {s.name}, " + ("by hand" if s.manual else every or "pushed"))
    return "; ".join(out)


def file_name(name: str, view: str, system: str | None, at: float) -> str:
    return f"{name}-{system or 'all'}-{view}-{time.strftime('%Y-%m-%d', time.localtime(at))}.md"


def export(model, view: str, system: str | None, snap: dict, g: dict, flat=None) -> str:
    """The document for ``view``: ``g`` is the graph answer the page draws; ``flat`` the unfolded block diagram."""
    spec = getattr(model, "spec", None)
    at = time.strftime("%Y-%m-%d %H:%M", time.localtime(snap["at"]))
    out = [f"# {model.name}: {TITLE[view]}", "", *([getattr(spec, "purpose", ""), ""] if getattr(spec, "purpose", "") else []),
           f"- System: {system or 'everything'}", f"- Moment: {at} ({'live' if snap.get('live') else 'as of'})",
           f"- Window: {human(snap['window'])}", ""]
    return "\n".join(out + (_dynamics(model, spec, g) if view == "dynamics" else _blocks(snap, g, flat)))


def _dynamics(m, spec, g: dict) -> list[str]:
    label = {n["id"]: n.get("label") or n["id"] for n in g["nodes"]}
    part = lambda kind, name: (spec.measured(kind).get(name) if spec is not None else None)      # noqa: E731
    rows = []
    for n in g["nodes"]:
        k, role = n["kind"], n.get("role")
        if k in ("valve", "disturbance"):
            f = part("flow", n.get("flow") or n["label"])
            rows.append([n["label"], "flow", getattr(f, "unit", "") or "per hour",
                         "; ".join(x for x in (n.get("equation"), _sensed(f)) if x), n.get("rateText")])
        elif role in ("desired", "gap"):
            words = f"desired {n['of']} = {n['desired']}" if role == "desired" else \
                f"{n['of']} − desired {n['of']}" if n.get("excess") else f"desired {n['of']} − {n['of']}"
            rows.append([n["label"], "goal", "", f"{words} (goal {n['goal']}, {n['setpoint']})", n.get("valueText")])
        elif role == "decision":
            rows.append([n["label"], "auxiliary", "", f"the decision {n['rule']}: what it computes is its own", ""])
        elif k in ("stock", "auxiliary"):
            t = part(k, n["label"])
            eqn = getattr(t, "equation", None)
            words = "the integral of its flows" if k == "stock" else eqn.text if eqn is not None else \
                "from outside the model (exogenous)" if n.get("exogenous") else "no equation"
            rows.append([n["label"], k, n.get("unit"), "; ".join(x for x in (words, _sensed(t)) if x), n.get("valueText")])
    out = ["## Variables", "", *_table(["name", "kind", "unit", "equation or sensor", "now"], rows), "## Flows per stock", ""]
    stocks = [n["label"] for n in g["nodes"] if n["kind"] == "stock"]
    out += _table(["stock", "in", "out"], [[s, ", ".join(f.name for f in m.flows.values() if f.target == s),
                                           ", ".join(f.name for f in m.flows.values() if f.source == s)] for s in stocks])
    return out + ["## Feedback loops", "", *_table(["label", "name", "polarity", "path", "goal it closes", "drawn"],
                  [[c["label"], c["name"], c.get("polarity") or "?", " → ".join(label.get(x, x.split(":", 1)[-1]) for x in c["nodes"]),
                    ", ".join(dict.fromkeys(x.split(":", 1)[1] for x in c["nodes"] if x.startswith(("gap:", "desired:")))), where]
                   for c, where in side_list(g)])]


def side_list(g: dict) -> list[tuple[dict, str]]:
    """The Dynamics side list's loops (dynamics.js sdLoopList), in its order: of known polarity, then of unknown, then
    those inside a closed system (two parts or fewer drawn here), each with where it is drawn."""
    kind = {n["id"]: n["kind"] for n in g["nodes"]}
    seen = lambda c: {x for x in c["nodes"] if kind.get(x) not in (None, "system", "terminal")}      # noqa: E731
    order = lambda c: ({"R": 0, "B": 1}.get(c.get("polarity"), 2), int(c["label"][1:] or 0))      # noqa: E731
    loops = g.get("causalLoops") or []
    drawn = sorted((c for c in loops if len(seen(c)) >= 2), key=order)
    inside = [(c, "inside " + ", ".join(sorted(next((n["label"] for n in g["nodes"] if n["id"] == x), x) for x in c["nodes"]
                                               if kind.get(x) == "system")))
              for c in loops if len(seen(c)) < 2 and any(kind.get(x) == "system" for x in c["nodes"])]
    return [(c, "drawn") for c in drawn] + inside


def _blocks(snap: dict, g: dict, flat) -> list[str]:
    from ..blockdiagram import _hold
    spec = flat.s if flat is not None else None
    rank = {"off": 0, "open": 1, "unknown": 2, "holding": 3}            # the page's order: the ones that need someone first
    rows = []
    for name, lp in sorted((g.get("loops") or {}).items() if spec is not None else (), key=lambda x: rank.get(x[1].get("status"), 2)):
        goal, loop = spec.goals[name], spec.loop(name)
        says = lambda nid: (flat.nodes.get(nid) or {}).get("says", "")      # noqa: E731
        y = f"{goal.of.kind}.{goal.of.name}"
        pid = (flat.prod.get(y) or ("",))[0]
        pid = "proc:" + pid.split(":", 1)[1] if pid.startswith("demux:") else pid
        proc = flat.nodes.get(pid) or {}
        how = ("identified" if goal.process.get("identified") else "declared") if goal.process else "not identified"
        t = spec.measured(goal.of.kind).get(goal.of.name)
        rows.append([name, f"{goal.of.name} {_hold(goal)}", f"y {goal.of.name}" + (" (measured)" if loop.sensors else ""),
                     "; ".join(f"{c}: {says(f'blk:{c}')}" for c in loop.controllers),
                     ", ".join(loop.actuators) + (f" (sets {', '.join(loop.valves)})" if loop.valves else ""),
                     f"{proc.get('label', goal.of.name)}: {proc.get('fn', {}).get('expr', 'not drawn')}, {how}",
                     _sensed(t) or "not measured", lp.get("status") or "unknown"])
    return ["## Control loops", "", *_table(["goal", "reference", "measured output", "controller and its law", "actuator",
                                             "process", "sensor and period", "now"], rows)]
