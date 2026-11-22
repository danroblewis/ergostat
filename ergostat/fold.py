"""Systems drawn as parts: the control diagram folded by the model's tree of systems.

A system that is not open is drawn as one box, its ports the edges that cross its boundary
(each port named for the part inside it reaches, with that part's reading). Opening it puts its
parts back, inside an outline, with its own systems still boxed. Drilling into a system draws
only what is in it; what it reaches outside is drawn as terminals at its edge, named for the part
outside and the system that part is in. Folding is the cascade's view: a system seen from
outside is a block with inputs and outputs, and its loops inside are its own business.

Only a YAML model has the tree (``spec.within``); an older model is drawn as it was."""

from __future__ import annotations

from .remote import box as remote_box
from .remote import measures as remote_measures
from .spec.architecture import size, size_said

WORST = ("off", "stale", "open", "unknown", "holding")


def name_of(n: dict) -> str:
    """How a part is named at a system's edge: a flow by its own name, not its valve's."""
    return n.get("flow") if n.get("kind") in ("valve", "disturbance") and n.get("flow") else n.get("label", n["id"])


def value_of(n: dict) -> str:
    v = n.get("valueText") or n.get("rateText") or ""
    return "" if v.startswith("?") else v


def upkeep(spec, name: str) -> bool:
    """The system is ergostat's upkeep of the model (the modelling template's), not part of the system modelled."""
    return ((getattr(spec, "uses", None) or {}).get(name) or {}).get("template") == "modelling"


def default_open(spec, focus: str | None) -> set[str]:
    """A system that is alone at its level is opened: a box with nothing beside it says nothing."""
    out: set[str] = set()
    level = [focus]
    while level:
        nxt = []
        for parent in level:
            kids = spec.subsystems(parent)
            if len(kids) == 1 and kids[0] not in (getattr(spec, "remotes", None) or {}):   # a remote starts closed
                out.add(kids[0])
            nxt += [k for k in kids if k in out]
        level = nxt
    return out


def chain_of(spec, model, node_id: str) -> list[str]:
    """The node's systems, outermost first."""
    kind, _, rest = node_id.partition(":")
    name = rest.split(":")[0]
    if kind in ("gap", "desired"):                     # a goal's, drawn in the dynamics view: where its controller is
        part = model.controllers.get(name)
    elif kind == "decision":                           # a block drawn as a decision: in its own system
        b = spec.blocks.get(name)
        return list(reversed(spec.chain(b.system))) if b else []
    else:
        part = model.part(name) if kind != "cloud" else model.flows.get(name)
    tags = list(getattr(part, "systems", None) or [])
    return list(reversed(tags))


def fold(g: dict, model, open_: set[str] | None, focus: str | None = None, reads: dict | None = None) -> dict:
    """``reads``: when the sensors of what remotes' boxes show last read (``remote.measures.read_times``)."""
    spec = getattr(model, "spec", None)
    if spec is None or not spec.systems or g.get("kind") not in ("control", "dynamics"):
        return g
    if open_ is None:
        open_ = default_open(spec, focus)
    if "*" in open_:
        open_ = set(spec.systems)
    nodes = {n["id"]: n for n in g["nodes"]}
    chains = {i: chain_of(spec, model, i) for i in nodes}

    def rep(i: str) -> str:
        ch = chains[i]
        if focus:
            if focus not in ch:
                return f"term:{i}"
            ch = ch[ch.index(focus) + 1:]
        for s in ch:
            if s not in open_:
                return f"system:{s}"
        return i

    reps = {i: rep(i) for i in nodes}
    out_nodes: dict[str, dict] = {}
    for i, n in nodes.items():
        r = reps[i]
        if r == i:
            ch = chains[i]
            shown = [s for s in ch if s in open_ and (not focus or (focus in ch and ch.index(s) > ch.index(focus)))]
            out_nodes[i] = {**n, "systems": shown[::-1]}               # the outlines it is drawn inside
    boxes: dict[str, dict] = {}
    terms: dict[str, dict] = {}
    for i, r in reps.items():
        if r.startswith("system:") and r not in boxes:
            name = r.split(":", 1)[1]
            ch = spec.chain(name)                                      # innermost first
            boxes[r] = {"id": r, "kind": "system", "label": name, "description": spec.systems.get(name, ""),
                        "systems": [s for s in ch[1:] if s in open_ and s != focus and (not focus or focus in ch[1:])],
                        "ports": [], "loops": {}, "status": None, "inner": spec.inner_loops(name),
                        "subsystems": spec.subsystems(name), "parts": 0, "remote": remote_box(spec, name),
                        "size": size_said(size(spec, name)),             # parts, loops, depth (architecture.py)
                        "upkeep": upkeep(spec, name)}                    # the model's own upkeep: drawn last, set apart
        if r.startswith("system:"):
            boxes[r]["parts"] += 1
            boxes[r].setdefault("holds", []).append(i)            # (correspond.py: what it holds, as drawn)
        elif r.startswith("term:"):
            n = nodes[i]
            ch = chains[i]
            terms[r] = {"id": r, "kind": "terminal", "label": name_of(n), "of": n.get("kind"), "systems": [],
                        "in": ch[-1] if ch else None, "valueText": value_of(n)}

    def port(box: str, side: str, orig: str) -> str:
        n = nodes[orig]
        pid = f"{box}:{side}:{orig}"
        b = boxes[box]
        if not any(p["id"] == pid for p in b["ports"]):
            b["ports"].append({"id": pid, "side": side, "part": orig, "label": name_of(n), "kind": n.get("kind"),
                               "value": value_of(n), "named": n.get("label")})   # named: the part's own label (a valve's)
        return pid

    edges, seen = [], set()
    used_terms: set[str] = set()
    for e in g["edges"]:
        s, t = reps.get(e["source"], e["source"]), reps.get(e["target"], e["target"])
        if s == t or (s.startswith("term:") and t.startswith("term:")):
            continue
        if s.startswith("term:") or t.startswith("term:"):
            used_terms.add(s if s.startswith("term:") else t)
        ne = {**e, "source": s, "target": t}
        if s.startswith("system:"):
            ne["sourcePort"] = port(s, "out", e["source"])
        if t.startswith("system:"):
            ne["targetPort"] = port(t, "in", e["target"])
        if s != e["source"] or t != e["target"]:
            key = (s, ne.get("sourcePort"), t, ne.get("targetPort"), e["kind"])
            if key in seen:
                continue
            seen.add(key)
            ne["id"] = f"{e['id']}~"
        edges.append(ne)
    for lp_name, lp in (g.get("loops") or {}).items():
        ctl = f"controller:{lp_name}"
        r = reps.get(ctl, ctl)
        if r.startswith("system:"):
            st = lp.get("status") or "unknown"
            boxes[r]["loops"][st] = boxes[r]["loops"].get(st, 0) + 1
        lp["nodes"] = sorted({reps.get(x, x) for x in lp.get("nodes", [])})
    for c in g.get("causalLoops") or []:                 # each feedback loop's members, as drawn here
        ns = [reps.get(x, x) for x in c.get("nodes", [])]
        ns = [x for i, x in enumerate(ns) if not i or ns[i - 1] != x]
        while len(ns) > 1 and ns[0] == ns[-1]:
            ns.pop()
        c["nodes"] = ns
    loops = g.get("loops") or {}
    for b in boxes.values():                                 # the box as a control panel: the measures it shows
        name = b["label"]
        shown = remote_measures.refs(spec, name, loops)      # a remote's: its own rules (remote/measures.py)
        if shown is None:
            shown = [f"{'flow' if r.kind == 'flow' else 'stock'}:{r.name}" for r in spec.show.get(name, [])]
        if not shown and not b["remote"]:                    # by default its goals' measures, its own first
            mine = [(len(spec.chain(spec.goals[k].system)), k) for k in loops
                    if k in spec.goals and name in spec.chain(spec.goals[k].system)]
            shown = [f"stock:{spec.goals[k].of.name}" if spec.goals[k].of.kind != "flow" else f"flow:{spec.goals[k].of.name}"
                     for _, k in sorted(mine)][:5]
        b["measures"] = []
        for nid in dict.fromkeys(shown):
            n = nodes.get(nid, {})
            lname = nid.split(":", 1)[1]
            goal = next((k for k, lp in loops.items() if lp.get("stock") == lname), None)
            lp = loops.get(goal, {}) if goal else {}
            b["measures"].append({"part": nid, "label": lname, "value": n.get("valueText") or n.get("rateText") or "?",
                                  "unit": n.get("unit", ""), "points": (n.get("points") or [])[-40:],
                                  "goal": goal, "setpoint": lp.get("setpoint"), "status": lp.get("status")})
        if b["remote"]:
            remote_measures.mark(spec, b, reads)
    for b in boxes.values():
        b["status"] = next((w for w in WORST if b["loops"].get(w)), None)
        b["ports"].sort(key=lambda p: (p["side"], p["label"]))
    for e in edges:
        e["loops"] = [k for k, lp in (g.get("loops") or {}).items() if e["source"] in lp["nodes"] and e["target"] in lp["nodes"]]
    return {**g, "nodes": [*out_nodes.values(), *boxes.values(), *(terms[t] for t in sorted(used_terms))], "edges": edges,
            "open": sorted(open_), "focus": focus, "tree": {s: {"within": spec.within.get(s), "description": d,
                                                               **({"remote": True} if s in getattr(spec, "remotes", {}) else {})}
                                                           for s, d in spec.systems.items()}}
