"""The system dynamics view of a system: the stock-and-flow diagram as Sterman's *Business Dynamics*,
Vensim and Stella draw it (SPEC §1a, §12a). Stocks, flows (each with its valve), clouds, auxiliaries,
and the connectors between them, each with its polarity where it is known; no sensors, controllers or
agents. Drawn from the control graph (``graph.control``) and the model's causal links
(``spec/causal.py``), never written, and nothing in the model is changed:

- a block is a decision rule: it is not drawn, and what it reads is connected straight to what it
  moves or sets, the signs along the way multiplied (not known when any of them is not);
- a goal is drawn the system dynamics way, as goal-seeking structure: a desired level (an auxiliary
  holding the value wanted, ``desired backlog = 0``) and the discrepancy that drives the correction
  positively, as Sterman defines it: for a ceiling the excess (``excess backlog`` = actual − desired:
  the actual feeding it +, the desired level −), for a floor (or a level held) the gap (``ideas gap``
  = desired − actual: the actual −, the desired +); the discrepancy feeds what its decisions move. A
  block that sets a goal's setpoint (a cascade) feeds its desired level. When the decision switches
  (on above a ceiling, off once back under), that is said in the panel, not drawn;
- every feedback loop is given, beside its members and polarity, its members as drawn and a label as
  Sterman numbers them (R1, B2, and ?3 for one whose polarity is not known);
- after folding (``finish``): a connector out of a closed module into an open system is drawn from
  a shadow variable ``<name>`` inside the receiving system, as Vensim and Stella draw a link from
  another view (a line between two parts both drawn is drawn as itself); a shadow is an input
  only, so a connector out to a part not drawn ends in a stub naming it, and a pipe out to one
  ends in a cloud (the part named beneath)."""

from __future__ import annotations

from . import sensing
from .state import fmt

SP = {"<=": "≤", ">=": "≥", "==": "=", "<": "<", ">": ">"}


def _sp(text: str) -> str:
    """``<= 20`` as ``≤ 20``."""
    text = (text or "").strip()
    for a, b in SP.items():
        if text.startswith(a):
            return b + text[len(a):]
    return text


def excess(spec, goal: str) -> bool:
    """Whether a goal's discrepancy is drawn as the excess (actual − desired): for a ceiling, so the
    corrective outflow it drives reads +."""
    g = spec.goals.get(goal) if spec is not None else None
    return bool(g and g.hold.op in ("<=", "<"))


def switching(spec, goal: str) -> str:
    """When the decisions serving a goal act, as on-off (bang-bang) control switches: "on while
    backlog > 0; off once backlog ≤ 0" (the release point an ``until`` names, else the goal's)."""
    g = spec.goals[goal]
    of = g.of.name
    ons = [b for b in spec.blocks.values() if b.type == "onoff" and b.params.get("goal") == goal]
    if not ons or g.hold.op == "==":
        return ""
    v = fmt(g.hold.value)
    on = {"<=": ">", "<": "≥", ">=": "<", ">": "≤"}[g.hold.op]
    rel = [b.params["until"] for b in ons if b.params.get("until")]
    off = _sp(str(rel[0])) if rel else _sp(str(g.hold))
    return f"on while {of} {on} {v}; off once {of} {off}"


def equation(spec, flow: str) -> str:
    """What a flow's rate is, as far as the model says: a number declared, the decision that sets it,
    or the causes it is declared to follow (a sign each, no size yet), unless the model writes its
    equation (SPEC §7b); ergostat writes none of its own, so the rest say what is not known yet, and why."""
    f = spec.flows.get(flow) if spec is not None else None
    if f is None:
        return ""
    if f.equation is not None:
        return f"{f.equation.text} (per hour, written)"
    if f.rate is not None:
        return f"{fmt(f.rate)} per hour, declared: a constant"
    out = []
    setter = spec.actuator_of(flow)
    if setter is not None:
        out.append(f"set by the decision {setter.name}: as much as it moves each time it acts")
    if f.driven_by:
        now = [str(r) for r in f.driven_by if str(r) in f.instant]
        signed = all(str(r) in f.polarity for r in f.driven_by)
        out.append(("not known yet: a declared cause with a sign, its size not estimated" if signed else
                     "not known yet: a declared cause, its sign not given and its size not estimated")
                    if len(f.driven_by) == 1 else
                    ("not known yet: declared causes with a sign each, their sizes not estimated" if signed else
                     "not known yet: declared causes, not all signed, their sizes not estimated"))
        if now:
            out.append(f"at once with {', '.join(r.split('.', 1)[1] for r in now)}: no stock between")
    if not out:
        out.append("not known: nothing in the model drives it" + ("; it is measured" if f.sensors else ", and it is not measured"))
    return "; ".join(out)


def _drawn_id(part: str, as_target: bool = False, via: str = "") -> str | None:
    """The node a model part is drawn as. A goal is its gap, except where a block sets its
    setpoint: there it is its desired level."""
    kind, _, name = part.partition(".")
    if kind in ("stock", "auxiliary"):
        return f"stock:{name}"
    if kind == "flow":
        return f"flow:{name}"
    if kind == "goal":
        return f"desired:{name}" if as_target and via == "acts" else f"gap:{name}"
    return None


def labels(loops: list[dict]) -> dict[str, str]:
    """Each loop's label as Sterman numbers them, by polarity, the shortest (the most basic) first, the
    ones the model names before the rest of a length: R1, R2, B1, ?1."""
    count: dict[str, int] = {}
    out = {}
    for c in sorted(loops, key=lambda c: (len(c.get("parts") or c.get("nodes") or []), " via " in c["name"], c["name"])):
        letter = c.get("polarity") or "?"
        count[letter] = count.get(letter, 0) + 1
        out[c["name"]] = f"{letter}{count[letter]}"
    return out


def _decisions(spec, ls) -> set[str]:
    """The machine blocks drawn as a decision (an auxiliary in its own right): those that read
    several things and move several, where drawing each reading into each thing moved would take more
    lines than a decision between them."""
    ins: dict[str, set[str]] = {}
    outs: dict[str, set[str]] = {}
    for x in ls:
        if x.target.startswith("block.") and not x.source.startswith("block."):
            ins.setdefault(x.target, set()).add(x.source)
        if x.source.startswith("block."):
            outs.setdefault(x.source, set()).add(x.target)
    found = set()
    for name, b in spec.blocks.items():
        part = f"block.{name}"
        i = len(ins.get(part, ())) + sum(1 for x in ls if x.target == part and x.source.startswith("block."))
        o = len(outs.get(part, ()))
        if b.machine and i >= 2 and o >= 2 and i * o > i + o:
            found.add(part)
    return found


def _connectors(spec) -> tuple[dict[tuple[str, str], dict], set[str]]:
    """Every information link to draw, between drawn parts: the model's causal links with the blocks
    taken out (each path through blocks becomes one link, its signs multiplied; a decision stands
    between what it reads and what it moves), and each goal's desired level feeding its gap."""
    from .spec.causal import links
    ls = links(spec)
    decide = _decisions(spec, ls)
    out_of: dict[str, list] = {}
    for x in ls:
        out_of.setdefault(x.source, []).append(x)
    out: dict[tuple[str, str], dict] = {}

    def add(src: str | None, dst: str | None, sign, rules: list[str], drv: bool = False) -> None:
        if not src or not dst or src == dst:
            return
        old = out.get((src, dst))
        if old is None:
            out[(src, dst)] = {"sign": sign, "rules": list(rules), "drivenBy": drv}   # (declared with driven-by: dashed)
            return
        old["drivenBy"] = old["drivenBy"] or drv
        if old["sign"] != sign:
            old["sign"] = None                           # two ways round disagree: not known
        old["rules"] += [r for r in rules if r not in old["rules"]]

    def into(block: str, sign, src: str | None, rules: list[str], seen: set[str]) -> None:
        name = block.split(".", 1)[1]
        if block in decide:
            add(src, f"decision:{name}", sign, rules)
            return
        through(block, sign, src, rules + [name], seen | {block})

    def through(block: str, sign, src: str | None, rules: list[str], seen: set[str]) -> None:
        for x in out_of.get(block, []):
            s = None if sign is None or x.sign is None else sign * x.sign
            if x.target.startswith("block."):
                if x.target not in seen:
                    into(x.target, s, src, rules, seen)
            else:
                add(src, _drawn_id(x.target, True, "acts"), s, rules)

    for x in ls:
        if x.kind == "material" or x.source.startswith("block."):
            continue
        if x.target.startswith("block."):
            into(x.target, x.sign, _drawn_id(x.source), [], set())
        else:
            add(_drawn_id(x.source), _drawn_id(x.target, True, x.kind), x.sign, [], x.kind == "influence")
    for d in decide:
        through(d, 1, f"decision:{d.split('.', 1)[1]}", [d.split(".", 1)[1]], {d})
    for g in spec.goals:
        add(f"desired:{g}", f"gap:{g}", 1, [])
    flip = {f"gap:{g}" for g in spec.goals if excess(spec, g)}   # an excess (actual − desired): every sign at it turned
    for (a, b), c in out.items():
        if c["sign"] is not None and (a in flip) != (b in flip):
            c["sign"] = -c["sign"]
    return out, decide


def _loop_nodes(c: dict, decide: set[str]) -> list[str]:
    """A causal loop's members as drawn, in its order: blocks left out (a decision kept), a goal as
    its gap (and its desired level before it, where the loop comes in through the setpoint)."""
    nodes: list[str] = []
    links = c.get("links") or []
    for i, p in enumerate(c["parts"]):
        if p.startswith("goal."):
            came = links[i - 1]["kind"] if links else ""
            if came == "acts":
                nodes.append(f"desired:{p.split('.', 1)[1]}")
            nodes.append(f"gap:{p.split('.', 1)[1]}")
        elif p in decide:
            nodes.append(f"decision:{p.split('.', 1)[1]}")
        else:
            nid = _drawn_id(p)
            if nid:
                nodes.append(nid)
    dedup = [n for i, n in enumerate(nodes) if not i or nodes[i - 1] != n]
    if len(dedup) > 1 and dedup[0] == dedup[-1]:
        dedup.pop()
    return dedup


def dynamics(g: dict, model) -> dict:
    """The control graph ``g`` (``graph.control``) drawn as system dynamics draws it."""
    spec = getattr(model, "spec", None)
    keep = [n for n in g["nodes"] if n["kind"] not in ("sensor", "controller")]
    nodes = []
    for n in keep:
        n = {**n, "sd": True, "agent": None}
        if n["kind"] == "cloud" and spec is not None and n["id"].endswith(":in"):   # an inflow from outside: from where
            src = sensing.comes_from(spec, n.get("flow") or "")
            if src:
                n["from"] = src
        if n["kind"] in ("valve", "disturbance"):
            n["valve"] = n.get("label")
            n["label"] = n.get("flow") or n["label"]
            if spec is not None:
                n["equation"] = equation(spec, n["label"])
        nodes.append(n)
    loops = g.get("loops") or {}
    ctl = {n["id"].split(":", 1)[1]: n for n in g["nodes"] if n["kind"] == "controller"}
    for name, c in ctl.items():                            # each goal served here: its desired level and its gap
        goal = spec.goals.get(name) if spec else None
        if c.get("openLoop") or (spec and goal is None):
            continue
        of = goal.of.name if goal else (loops.get(name) or {}).get("stock", name)
        lp = loops.get(name) or {}
        sp = _sp(str(goal.hold) if goal else lp.get("setpoint") or "")
        want = fmt(goal.hold.value) if goal else sp.lstrip("≤≥=<> ")
        where = c.get("systems", [])
        sw = switching(spec, name) if goal else ""
        nodes.append({"id": f"desired:{name}", "kind": "auxiliary", "label": f"desired {of}", "sd": True, "role": "desired",
                      "goal": name, "of": of, "setpoint": sp, "desired": want, "valueText": want, "switching": sw,
                      "systems": where, "description": goal.description if goal else c.get("description", "")})
        err = lp.get("error", c.get("error"))
        over = excess(spec, name)
        if over and err is not None:
            err = -err
        nodes.append({"id": f"gap:{name}", "kind": "auxiliary", "label": f"excess {of}" if over else f"{of} gap", "sd": True,
                      "role": "gap", "excess": over, "goal": name, "of": of, "setpoint": sp, "desired": want, "switching": sw,
                      "value": err, "valueText": fmt(err) if err is not None else "", "offBy": c.get("offBy"), "systems": where})
    conns, decide = _connectors(spec) if spec is not None else ({}, set())
    for part in sorted(decide):                            # a decision: a machine block reading several, moving several
        b = spec.blocks[part.split(".", 1)[1]]
        nodes.append({"id": f"decision:{b.name}", "kind": "auxiliary", "label": b.name, "sd": True, "role": "decision",
                      "rule": b.name, "description": b.description, "valueText": "",
                      "systems": list(reversed(spec.chain(b.system)))})
    ids = {n["id"] for n in nodes}
    edges = [e for e in g["edges"] if e["kind"] == "pipe" and e["source"] in ids and e["target"] in ids]
    if spec is not None:
        for (src, dst), c in sorted(conns.items()):
            if src in ids and dst in ids:
                sign = None if c["sign"] is None else "+" if c["sign"] > 0 else "-"
                e = {"id": f"connector:{src}->{dst}", "source": src, "target": dst, "kind": "connector", "polarity": sign,
                     "rules": c["rules"], "drivenBy": c["drivenBy"]}
                if src.startswith(("gap:", "desired:")):
                    e["goalSeeking"] = True                  # (laid out with its flow, as a controller was: layouts.js)
                edges.append(e)
    else:                                                    # an older model: its influences, and each controller's action
        for e in g["edges"]:
            if e["kind"] == "influence" and e["source"] in ids and e["target"] in ids:
                edges.append({**e, "id": "connector:" + e["id"].split(":", 1)[1], "kind": "connector", "rules": [], "drivenBy": True})
        for e in g["edges"]:
            if e["kind"] == "action" and e["source"].startswith("controller:"):
                name = e["source"].split(":", 1)[1]
                if f"gap:{name}" in ids and e["target"] in ids:
                    edges.append({"id": f"connector:gap:{name}->{e['target']}", "source": f"gap:{name}", "target": e["target"],
                                  "kind": "connector", "polarity": None, "rules": [], "goalSeeking": True})
        for name in ctl:
            st = (loops.get(name) or {}).get("stock")
            if f"gap:{name}" in ids and f"stock:{st}" in ids:
                edges.append({"id": f"connector:stock:{st}->gap:{name}", "source": f"stock:{st}", "target": f"gap:{name}",
                              "kind": "connector", "polarity": "-", "rules": []})
                edges.append({"id": f"connector:desired:{name}->gap:{name}", "source": f"desired:{name}",
                              "target": f"gap:{name}", "kind": "connector", "polarity": "+", "rules": [], "goalSeeking": True})
    # a decision with nothing drawn to read or to move, and a goal nothing acts on, are no structure
    # here (a gap would feed nothing): the goal is said on what it is about
    ends = {(e["source"], "out") for e in edges} | {(e["target"], "in") for e in edges}
    lone = {n["id"] for n in nodes if n.get("role") == "decision" and not {(n["id"], "in"), (n["id"], "out")} <= ends}
    edges = [e for e in edges if e["source"] not in lone and e["target"] not in lone]
    nodes = [n for n in nodes if n["id"] not in lone]
    acting = {e["source"] for e in edges if e["source"].startswith("gap:")}
    idle = {n["id"] for n in nodes if n.get("role") in ("gap", "desired") and f"gap:{n['goal']}" not in acting}
    for n in nodes:
        if n.get("role") == "gap":
            of = next((x for x in nodes if x["id"] in (f"stock:{n['of']}", f"flow:{n['of']}")), None)
            # what serves the goal anywhere in the model (its controllers, each with its top system), drawn here or not
            by = [{"block": b, "system": (spec.chain(spec.blocks[b].system) or [None])[-1]}
                  for b in spec.loop(n["goal"]).controllers] if spec is not None and n["goal"] in spec.goals else []
            if of is not None:
                of.setdefault("goals", []).append({"name": n["goal"], "setpoint": n["setpoint"], "desired": n["desired"],
                                                   "by": by, "acted": n["id"] not in idle or bool(by)})
    nodes = [n for n in nodes if n["id"] not in idle]
    edges = [e for e in edges if e["source"] not in idle and e["target"] not in idle]
    causal = [{**c, "nodes": _loop_nodes(c, decide)} for c in g.get("causalLoops") or []]
    tags = labels(causal)
    for c in causal:
        c["label"] = tags[c["name"]]
    return finish({**g, "kind": "dynamics", "nodes": nodes, "edges": edges, "causalLoops": causal})


def finish(g: dict) -> dict:
    """After folding (``fold.py``): shadows, stubs and clouds where lines would cross a system's
    edge (``shadows``), each line's loops (the causal loops it is a link of, by the parts it joins
    in the model), and the systems' boxes left plain (a module's name and its ports, no control
    panel)."""
    if g.get("tree") is not None:
        g = shadows(g)
    pairs = {}
    for c in g.get("causalLoops") or []:
        ns = c["nodes"]
        pairs[c["name"]] = {(a, b) for a, b in zip(ns, ns[1:] + ns[:1], strict=False) if a != b}
    for e in g["edges"]:
        a, b = e.get("from", e["source"]), e.get("to", e["target"])
        e["loops"] = []
        e["causal"] = [k for k, ps in pairs.items() if (a, b) in ps or (e["kind"] == "pipe" and (b, a) in ps)]
    for n in g["nodes"]:
        if n["kind"] == "system":
            n["charted"] = [{"part": x["part"], "label": x["label"], **{k: x[k] for k in ("value", "stale", "missing",
                            "unchecked") if k in x}} for x in n.get("measures") or []]   # its panel charts them
            n["measures"] = []                         # a module box draws no measures: SD draws structure
            n["status"] = None
            n["loops"] = {}
    return g


def _inner(n: dict) -> str:
    return (n.get("systems") or [""])[0]


def shadows(g: dict) -> dict:
    """Lines whose other end is not on the canvas, as Vensim and Stella draw a model of several views
    (modules), and only those: a line between two parts both drawn, in open systems or not, is drawn
    as itself, however far it runs (the owner, 2026-11-16: open systems keep their real connections).

    - a connector out of a closed module (a part inside it, not drawn) into a part drawn in an open
      system comes from a shadow variable ``<name>`` inside the receiving system (one per part and
      system);
    - a shadow is an input only: a connector out to a part outside a system drawn alone, or into a
      closed module, ends at a stub naming that part, inside the sending system; a pipe to or from a
      part outside ends in a cloud, the part named beneath it;

    Each line keeps the parts it joins in the model (``from``, ``to``), for the loops it is a link of."""
    nodes = {n["id"]: n for n in g["nodes"]}
    drawn = {i for i, n in nodes.items() if n["kind"] not in ("system", "terminal", "cloud")}
    extra: dict[str, dict] = {}
    edges = []
    for e in g["edges"]:
        e = {**e, "from": e.get("from", e["source"]), "to": e.get("to", e["target"])}
        s, t = e["source"], e["target"]
        if e["kind"] == "pipe":
            for end in ("source", "target"):
                x = e[end]
                if nodes.get(x, {}).get("kind") == "terminal":
                    cid = f"cloud:{e.get('flow') or x}:{'in' if end == 'source' else 'out'}"
                    term = nodes[x]
                    extra.setdefault(cid, {"id": cid, "kind": "cloud", "label": term["label"], "beyond": term["label"],
                                           "in": term.get("in"), "sd": True, "systems": []})
                    e[end] = cid
                    e["id"] = f"{e['id']}~c"
        elif nodes.get(t, {}).get("kind") == "terminal":
            term = nodes[t]
            sid = f"stub:{t.split(':', 1)[1]}"
            extra.setdefault(sid, {**term, "id": sid, "role": "stub", "systems": []})
            e["target"] = sid
            e["id"] = f"{e['id']}~s"
        elif e["kind"] == "connector" and t in drawn and nodes.get(s, {}).get("kind") == "system" and e.get("sourcePort"):
            port = next((p for p in nodes[s]["ports"] if p["id"] == e["sourcePort"]), None)
            dst = nodes[t]
            if port is not None:                            # out of a closed module, into an open system: its shadow there
                sid = f"shadow:{_inner(dst)}:{port['part']}"
                extra.setdefault(sid, {"id": sid, "kind": "terminal", "role": "shadow", "label": port["label"], "of": port.get("kind"),
                                       "in": nodes[s]["label"], "valueText": port.get("value", ""),
                                       "systems": list(dst.get("systems") or [])})
                e["source"] = sid
                e.pop("sourcePort")
                e["id"] = f"connector:{sid}->{t}"
        elif e["kind"] == "connector" and s in drawn and nodes.get(t, {}).get("kind") == "system" and e.get("targetPort"):
            port = next((p for p in nodes[t]["ports"] if p["id"] == e["targetPort"]), None)
            if port is not None:                            # out of an open system, into a closed module: a stub naming it
                sid = f"stub:{_inner(nodes[s])}:{port['part']}"
                extra.setdefault(sid, {"id": sid, "kind": "terminal", "role": "stub", "label": port["label"], "of": port.get("kind"),
                                       "in": nodes[t]["label"], "valueText": "", "systems": list(nodes[s].get("systems") or [])})
                e["target"] = sid
                e.pop("targetPort")
                e["id"] = f"connector:{s}->{sid}"
        edges.append(e)
    used = {x for e in edges for x in (e["source"], e["target"])}
    ports = {e.get(k) for e in edges for k in ("sourcePort", "targetPort")}
    for n in g["nodes"]:                                # a module's port nothing crosses now: gone
        if n["kind"] == "system":
            n["ports"] = [p for p in n.get("ports") or [] if p["id"] in ports]
    out = [n for n in g["nodes"] if n["kind"] != "terminal" or n["id"] in used]
    out += [n for i, n in extra.items() if i in used]
    seen, lines = set(), []
    for e in edges:                                     # (two lines now between the same ends: one)
        key = (e["source"], e.get("sourcePort"), e["target"], e.get("targetPort"), e["kind"], e["id"])
        if key not in seen:
            seen.add(key)
            lines.append(e)
    return {**g, "nodes": out, "edges": lines}


# the control words the attention cards use, in system dynamics' (the regulator is the flow's valve)
_WORDS = [
    (r"\ba valve too small\b", "a flow too small to close the gap"),
    (r"\bthe valve is at its limit \(saturated\)", "the flow is at its most (saturated)"),
    (r"\bits valve keeps up\b", "its flow keeps up"),
    (r"\bits valve\b", "its flow"), (r"\bthe valve\b", "the flow"), (r"\bvalves?\b", "flow"),
    (r"\bits controller\b", "its decision"), (r"\bcontrollers?\b", "decision"),
    (r"\bsetpoints?\b", "desired level"), (r"\ba rule\b", "a fixed decision"), (r"\brules?\b", "decision"),
    (r"\bgoals?\b", "desired level"), (r"<=", "≤"), (r">=", "≥"), (r"==", "="),
]


def words(text: str) -> str:
    """A card's text in system dynamics' words: no controller, setpoint, rule, goal or valve."""
    import re
    for a, b in _WORDS:
        text = re.sub(a, b, text)
    return text


def attention(att: list[dict], snap: dict) -> list[dict]:
    """The attention cards as the dynamics view says them: a loop off its goal as a gap (``backlog is
    4, desired backlog = 0: off by 4``), the rest in system dynamics' words."""
    out = []
    loops = snap.get("loops") or {}
    for a in att:
        a = dict(a)
        what = a.get("what", "")
        name = what.split(" ", 1)[1] if what.startswith(("loop ", "controller ")) else None
        lp = loops.get(name) if name else None
        if lp and lp.get("status") == "off" and what.startswith("loop "):
            sp = _sp(lp.get("setpoint") or "")
            want = sp.lstrip("≤≥=<> ")
            gap = f": {lp['off_by_words']}" if lp.get("off_by_words") else ""
            a["says"] = f"{lp['stock']} is {fmt(lp.get('value'))}, desired {lp['stock']} = {want}{gap}"
        else:
            a["says"] = words(a.get("says", ""))
        if name:
            a["what"] = f"loop {name}"
        else:
            a["what"] = words(what)
        out.append(a)
    return out
