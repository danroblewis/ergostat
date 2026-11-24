"""The Guide: a short sequence of frames, each one line of text and a tiny model drawn by the real
renderers (the dynamics view, ``dynamics.py``; the blocks view, ``blockdiagram.py``), so that the
diagram does the explaining. Why (what we control and what we want), system dynamics (what is),
control (what we control); the project's own model is the last frame, drawn by the page itself.

Every frame's model is a real model, compiled as a project's is. A frame that builds a diagram up
may leave parts of it out (``drop``) or cut a signal (``cut``): what was cut enters from outside
the frame as an input with its own symbol, so nothing is drawn that the model does not have. Where
a frame shows behaviour over time, ``plot`` gives the few equations the page integrates (Euler):
each rate or auxiliary a sum of terms, each term a coefficient times a product of variables, and
inputs that step at given times. The equations are the frame's own, a teaching model's, not the
project's (whose equations, when it writes them, are replayed by ergostat/numbers)."""

from __future__ import annotations

import tempfile
import textwrap
from functools import lru_cache
from pathlib import Path

NO_SNAPSHOT = {"stocks": {}, "flows": {}, "loops": {}}

CUSTOMERS = """
    stocks:
      customers:
        unit: people
"""

# the control frames' model: customers held at a setpoint by a proportional controller turning ad spend
HELD = """
    stocks:
      customers:
        unit: people
        sensor:
          manual: true
    auxiliaries:
      ad-spend:
        unit: k$
    flows:
      signups:
        to: customers
        driven-by: +auxiliary.ad-spend
    goals:
      enough:
        stock: customers
        hold: "== 100"
    blocks:
      marketing:
        type: proportional
        goal: enough
        gain: 0.5
        out: auxiliary.ad-spend
"""

WANTED = HELD.replace('"== 100"', '">= 100"')      # a floor: its loop's sign is known (a level held is not)

CHURN = """
      churn:
        from: customers
"""

CASCADE = """
    systems:
      campaign:
        description: the inner loop, holding the signup rate its setpoint asks for
    stocks:
      customers:
        unit: people
        sensor:
          manual: true
    auxiliaries:
      ad-spend:
        unit: k$
        system: campaign
    flows:
      signups:
        system: campaign
        to: customers
        driven-by: +auxiliary.ad-spend
        sensor:
          manual: true
    goals:
      enough:
        stock: customers
        hold: "== 100"
      signup-rate:
        system: campaign
        flow: signups
        hold: "== 10"
    blocks:
      marketing:
        type: proportional
        goal: enough
        gain: 0.5
        out: goal.signup-rate
      ads:
        system: campaign
        type: proportional
        goal: signup-rate
        gain: 2
        out: auxiliary.ad-spend
"""


def _run(stocks: dict, rates: dict, aux: dict | None = None, inputs: dict | None = None, series=None, label: str = "") -> dict:
    """One run of a frame's equations. ``rates``: flow → (from, to, terms); ``aux``: name → terms;
    ``inputs``: name → [[t, value], ...], each value holding from its time on; ``series``: what is
    plotted, each [variable, its label, dashed]."""
    return {"stocks": stocks, "flows": {f: {"from": a, "to": b, "terms": t} for f, (a, b, t) in rates.items()},
            "aux": aux or {}, "inputs": inputs or {}, "label": label,
            "series": [{"of": v, "label": lb, "dash": d} for v, lb, d in (series or [[next(iter(stocks)), "", False]])]}


def _plot(runs: list[dict], until: float, y: str, x: str = "weeks", dt: float = 0.05, band=None) -> dict:
    return {"runs": runs, "until": until, "dt": dt, "x": x, "y": y, **({"band": band} if band else {})}


FRAMES = [
    # ---------------------------------------------------------------- why
    {"id": "want", "part": "why", "text": "You control the knob. You want the stock.",
     "views": [{"view": "dynamics", "model": CUSTOMERS + """
    flows:
      signups:
        to: customers
    auxiliaries:
      ad-spend:
        unit: k$
""", "only": ["stock:customers", "stock:ad-spend"]}]},
    {"id": "between", "part": "why",
     "text": "Between them is the rest of the system. System dynamics draws what is: the goal as a desired level and a gap "
             "that drives the flow, or 'no feedback' when nothing acts on it. A goal not holding says so on its gap: "
             "'off by 36' in red, its balancing loop's marker red too. Control draws what we control.",
     "views": [{"view": "dynamics", "model": WANTED}, {"view": "blocks", "model": WANTED}]},
    # ---------------------------------------------------------------- system dynamics: what is
    {"id": "fills", "part": "dynamics",
     "text": "A stock fills through its inflow. Its value is in its unit ('unit ?' when the model gives none).",
     "views": [{"view": "dynamics", "model": CUSTOMERS + """
    flows:
      signups:
        to: customers
"""}],
     "plot": _plot([_run({"customers": 0}, {"signups": (None, "customers", [[10, []]])})], 20, "customers")},
    {"id": "levels", "part": "dynamics", "text": "Add an outflow: when outflow equals inflow, the stock holds.",
     "views": [{"view": "dynamics", "model": CUSTOMERS + """
    flows:
      signups:
        to: customers
      churn:
        from: customers
"""}],
     "plot": _plot([_run({"customers": 0}, {"signups": (None, "customers", [[10, []]]),
                                            "churn": ("customers", None, [[1, ["churn-now"]]])},
                         inputs={"churn-now": [[0, 4], [8, 10]]})], 20, "customers")},
    {"id": "links", "part": "dynamics", "text": "A link carries information, not material, so it is drawn lighter than the pipe. "
                                                "It has a sign: more customers, more churn (+).",
     "views": [{"view": "dynamics", "loops": False, "model": CUSTOMERS + """
    auxiliaries:
      churn-fraction:
        unit: per week
    flows:
      signups:
        to: customers
      churn:
        from: customers
        driven-by: [+stock.customers, +auxiliary.churn-fraction]
"""}],
     "plot": _plot([_run({"customers": 0}, {"signups": (None, "customers", [[10, []]]),
                                            "churn": ("customers", None, [[1, ["churn-fraction", "customers"]]])},
                         aux={"churn-fraction": [[0.2, []]]})], 20, "customers")},
    {"id": "balancing", "part": "dynamics", "text": "That closes a loop. B balances: the stock seeks a level.",
     "views": [{"view": "dynamics", "model": CUSTOMERS + """
    auxiliaries:
      churn-fraction:
        unit: per week
    flows:
      signups:
        to: customers
      churn:
        from: customers
        driven-by: [+stock.customers, +auxiliary.churn-fraction]
    loops:
      churn:
        through: [flow.churn]
"""}],
     "plot": _plot([_run({"customers": 0}, {"signups": (None, "customers", [[10, []]]),
                                            "churn": ("customers", None, [[1, ["churn-fraction", "customers"]]])},
                         aux={"churn-fraction": [[0.2, []]]})], 20, "customers")},
    {"id": "reinforcing", "part": "dynamics",
     "text": "R reinforces: customers bring customers. The loop that dominates sets the behaviour.",
     "views": [{"view": "dynamics", "model": CUSTOMERS + """
    auxiliaries:
      churn-fraction:
        unit: per week
    flows:
      signups:
        to: customers
        driven-by: +stock.customers
      churn:
        from: customers
        driven-by: [+stock.customers, +auxiliary.churn-fraction]
    loops:
      word-of-mouth:
        through: [flow.signups]
      churn:
        through: [flow.churn]
"""}],
     "plot": _plot([_run({"customers": 20}, {"signups": (None, "customers", [[1, []], [0.28, ["customers"]]]),
                                             "churn": ("customers", None, [[0.2, ["customers"]]])}, label="R dominates"),
                    _run({"customers": 20}, {"signups": (None, "customers", [[1, []], [0.1, ["customers"]]]),
                                             "churn": ("customers", None, [[0.2, ["customers"]]])}, label="B dominates",
                         series=[["customers", "", True]])], 20, "customers")},
    # ---------------------------------------------------------------- control: what we control
    {"id": "block", "part": "control", "text": "A block is a function: input u in, output y out. P is the process.",
     "views": [{"view": "blocks", "model": HELD, "drop": ["blk:marketing", "sum:enough", "ref:enough", "sen:stock.customers"]}],
     "plot": _plot([_run({"customers": 0}, {"signups": (None, "customers", [[1, ["u"]]])},
                         inputs={"u": [[0, 0], [2, 10]]}, series=[["customers", "y", False], ["u", "u", True]])], 20, "customers")},
    {"id": "controller", "part": "control", "text": "A controller C acts on the error: e = r − y.",
     "views": [{"view": "blocks", "model": HELD, "drop": ["sen:stock.customers"], "cut": [["sen:stock.customers", "sum:enough"]]}]},
    {"id": "closed", "part": "control", "text": "Close the loop: a sensor H reads the output back, and the output follows the setpoint.",
     "views": [{"view": "blocks", "model": HELD}],
     "plot": _plot([_run({"customers": 0}, {"signups": (None, "customers", [[1, ["ad-spend"]]])},
                         aux={"ad-spend": [[0.5, ["r"]], [-0.5, ["customers"]]]}, inputs={"r": [[0, 0], [2, 100]]},
                         series=[["customers", "y", False], ["r", "r", True]])], 20, "customers")},
    {"id": "disturbance", "part": "control", "text": "A disturbance d pushes the output away; the loop pushes it back.",
     "views": [{"view": "blocks", "model": HELD.replace("    goals:", CHURN + "    goals:")}],
     "plot": _plot([_run({"customers": 100}, {"signups": (None, "customers", [[1, ["ad-spend"]]]),
                                              "churn": ("customers", None, [[1, ["d"]]])},
                         aux={"ad-spend": [[0.5, ["r"]], [-0.5, ["customers"]]]}, inputs={"r": [[0, 100]], "d": [[0, 0], [6, 20], [10, 0]]},
                         series=[["customers", "y", False], ["r", "r", True]])], 20, "customers", band=[6, 10, "d"])},
    {"id": "cascade", "part": "control",
     "text": "A cascade: the outer controller sets the inner loop's setpoint. Open the inner block (+).",
     "views": [{"view": "blocks", "model": CASCADE, "open": [], "opens": ["campaign"]}]},
]

PARTS = {"why": "Why", "dynamics": "System dynamics: what is", "control": "Control: what we control", "yours": "Yours"}
YOURS = {"id": "yours", "part": "yours", "text": "Your system, both ways."}


def _compile(text: str):
    from . import spec as sp
    from .spec.legacy import to_model
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ergostat.yaml"
        path.write_text("name: guide\n" + textwrap.dedent(text))
        spec, problems = sp.read(path)
    errors = [p for p in problems if p.level == "error"]
    if errors:
        raise ValueError("a guide frame's model does not compile: " + "; ".join(map(str, errors)))
    return to_model(spec, problems)


def _dynamics(m, v: dict) -> dict:
    from . import graph
    from .dynamics import dynamics
    g = dynamics(graph.control(m, NO_SNAPSHOT, graph.select(m)), m)
    if v.get("only"):                            # parts side by side, nothing between them yet
        keep = set(v["only"])
        g["nodes"] = [n for n in g["nodes"] if n["id"] in keep]
        g["edges"] = []
        g["causalLoops"] = []
    if v.get("loops") is False:                  # the links, before the loop they close is named
        g["causalLoops"] = []
        for e in g["edges"]:
            e["causal"] = []
    for n in g["nodes"]:
        n["bare"] = True                         # no readings: a frame shows structure, its graph the behaviour
    return g


def _reveal(g: dict, drop: set[str], cut: set[tuple[str, str]]) -> dict:
    """The diagram with some parts left out and some signals cut: a signal whose source is left out,
    or that is cut, enters as an input (its own symbol), so the frame shows only what it has."""
    nodes, inputs, edges = [n for n in g["nodes"] if n["id"] not in drop], [], []
    parent = {n["id"]: n.get("parent") for n in g["nodes"]}
    for e in g["edges"]:
        if e["target"] in drop:
            continue
        if e["source"] in drop or (e["source"], e["target"]) in cut:
            sig = e.get("signal") or {}
            nid = f"in:{e['id']}"
            port = f"{nid}|out|{e['targetPort'].rsplit('|', 1)[-1]}"
            inputs.append({"id": nid, "kind": "input", "role": "input", "label": f"{sig.get('sym', '')} {sig.get('sub', '')}".strip(),
                          "fn": {"sym": sig.get("sym", ""), "sub": sig.get("sub", "")}, "ins": [],
                          "outs": [{"id": port, "side": "E"}], "parent": parent.get(e["target"]),
                          "says": f"{sig.get('what', 'a signal')}, from outside this frame"})
            e = {**e, "id": f"{e['id']}:in", "source": nid, "sourcePort": port, "feedback": False}
        edges.append(e)
    return {**g, "nodes": inputs + nodes, "edges": edges}          # (inputs first: laid out on the left)


def _blocks(m, v: dict, open_=None) -> dict:
    from .blockdiagram import diagram
    g = diagram(m, {}, set(open_) if open_ is not None else None)
    return _reveal(g, set(v.get("drop", [])), {tuple(c) for c in v.get("cut", [])})


@lru_cache(maxsize=1)
def frames() -> dict:
    out = []
    for f in FRAMES:
        views = []
        for v in f["views"]:
            m = _compile(v["model"])
            if v["view"] == "dynamics":
                views.append({"view": "dynamics", "graph": _dynamics(m, v)})
            else:
                view = {"view": "blocks", "graph": _blocks(m, v, v.get("open"))}
                if v.get("opens"):                # the same diagram with its inner block open: shown on a click
                    view["opened"] = _blocks(m, v, v["opens"])
                views.append(view)
        out.append({k: f[k] for k in ("id", "part", "text")} | {"views": views, "plot": f.get("plot")})
    return {"parts": PARTS, "frames": [*out, YOURS]}
