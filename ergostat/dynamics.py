"""The system dynamics view of a system: the stock-and-flow diagram as Sterman's *Business Dynamics*,
Vensim and Stella draw it (SPEC §1a, §12a). Stocks, flows (each with its valve), clouds, auxiliaries,
and the connectors between them, each with its polarity where it is known; no sensors, controllers or
agents. Drawn from the control graph (``graph.control``) and the model's causal links
(``spec/causal.py``), never written, and nothing in the model is changed:

- a block is a decision rule: it is not drawn, and what it reads is connected straight to what it
  moves or sets, the signs along the way multiplied (not known when any of them is not);
- a goal is drawn the system dynamics way, as goal-seeking structure: a desired level (an auxiliary
  holding the setpoint) and the gap (desired − actual), what the goal is about feeding the gap (−),
  the desired level feeding it (+), and the gap feeding what its decision rules move. A block that
  sets a goal's setpoint (a cascade) feeds its desired level;
- every feedback loop is given, beside its members and polarity, its members as drawn and a label as
  Sterman numbers them (R1, B2, and ?3 for one whose polarity is not known)."""

from __future__ import annotations

from .state import fmt

SP = {"<=": "≤", ">=": "≥", "==": "=", "<": "<", ">": ">"}


def _sp(text: str) -> str:
    """``<= 20`` as ``≤ 20``."""
    text = (text or "").strip()
    for a, b in SP.items():
        if text.startswith(a):
            return b + text[len(a):]
    return text


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
    """Each loop's label as Sterman numbers them, by polarity in the order given: R1, R2, B1, ?1."""
    count: dict[str, int] = {}
    out = {}
    for c in loops:
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

    def add(src: str | None, dst: str | None, sign, rules: list[str]) -> None:
        if not src or not dst or src == dst:
            return
        old = out.get((src, dst))
        if old is None:
            out[(src, dst)] = {"sign": sign, "rules": list(rules)}
            return
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
            add(_drawn_id(x.source), _drawn_id(x.target, True, x.kind), x.sign, [])
    for d in decide:
        through(d, 1, f"decision:{d.split('.', 1)[1]}", [d.split(".", 1)[1]], {d})
    for g in spec.goals:
        add(f"desired:{g}", f"gap:{g}", 1, [])
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
        if n["kind"] in ("valve", "disturbance"):
            n["valve"] = n.get("label")
            n["label"] = n.get("flow") or n["label"]
        nodes.append(n)
    loops = g.get("loops") or {}
    ctl = {n["id"].split(":", 1)[1]: n for n in g["nodes"] if n["kind"] == "controller"}
    for name, c in ctl.items():                            # each goal served here: its desired level and its gap
        goal = spec.goals.get(name) if spec else None
        if c.get("openLoop") or (spec and goal is None):
            continue
        of = goal.of.name if goal else (loops.get(name) or {}).get("stock", name)
        lp = loops.get(name) or {}
        sp = str(goal.hold) if goal else lp.get("setpoint") or ""
        where = c.get("systems", [])
        nodes.append({"id": f"desired:{name}", "kind": "auxiliary", "label": f"desired {of}", "sd": True, "role": "desired",
                      "goal": name, "of": of, "setpoint": sp, "valueText": _sp(sp), "systems": where,
                      "description": goal.description if goal else c.get("description", "")})
        err = lp.get("error", c.get("error"))
        nodes.append({"id": f"gap:{name}", "kind": "auxiliary", "label": f"{of} gap", "sd": True, "role": "gap",
                      "goal": name, "of": of, "setpoint": sp, "value": err, "valueText": fmt(err) if err is not None else "",
                      "systems": where})
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
                     "rules": c["rules"]}
                if src.startswith(("gap:", "desired:")):
                    e["goalSeeking"] = True                  # (laid out with its flow, as a controller was: layouts.js)
                edges.append(e)
    else:                                                    # an older model: its influences, and each controller's action
        for e in g["edges"]:
            if e["kind"] == "influence" and e["source"] in ids and e["target"] in ids:
                edges.append({**e, "id": "connector:" + e["id"].split(":", 1)[1], "kind": "connector", "rules": []})
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
        if n["id"] in idle and n["role"] == "gap":
            of = next((x for x in nodes if x["id"] in (f"stock:{n['of']}", f"flow:{n['of']}")), None)
            if of is not None:
                of.setdefault("goals", []).append({"name": n["goal"], "setpoint": n["setpoint"], "acted": False})
        elif n.get("role") == "gap":
            of = next((x for x in nodes if x["id"] in (f"stock:{n['of']}", f"flow:{n['of']}")), None)
            if of is not None:
                of.setdefault("goals", []).append({"name": n["goal"], "setpoint": n["setpoint"], "acted": True})
    nodes = [n for n in nodes if n["id"] not in idle]
    edges = [e for e in edges if e["source"] not in idle and e["target"] not in idle]
    causal = [{**c, "nodes": _loop_nodes(c, decide)} for c in g.get("causalLoops") or []]
    tags = labels(causal)
    for c in causal:
        c["label"] = tags[c["name"]]
    return finish({**g, "kind": "dynamics", "nodes": nodes, "edges": edges, "causalLoops": causal})


def finish(g: dict) -> dict:
    """After folding (``fold.py``): each line's loops (the causal loops it is a link of), and the
    systems' boxes left plain (a module's name and its ports, no control panel)."""
    pairs = {}
    for c in g.get("causalLoops") or []:
        ns = c["nodes"]
        pairs[c["name"]] = {(a, b) for a, b in zip(ns, ns[1:] + ns[:1], strict=False) if a != b}
    for e in g["edges"]:
        a, b = e["source"], e["target"]
        e["loops"] = []
        e["causal"] = [k for k, ps in pairs.items() if (a, b) in ps or (e["kind"] == "pipe" and (b, a) in ps)]
    for n in g["nodes"]:
        if n["kind"] == "system":
            n["measures"] = []
            n["status"] = None
            n["loops"] = {}
    return g
