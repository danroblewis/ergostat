"""One selection across the views: which model parts each drawn shape is, and which shapes stand for
each model part, in the view drawn (SPEC §1a: one model, two perspectives).

A model part is ``stock.x``, ``flow.x``, ``auxiliary.x``, ``goal.g`` (a goal: what it compares), its
reference ``goal.g.r`` (the value wanted: the desired level, r), ``block.b`` or ``system.s``. The
page keeps the parts chosen, not the shapes, so a selection survives a change of view and is lit in
two views at once. The rule is identity, never "everything it touches":

- dynamics: a stock or an auxiliary is itself, a flow (its valve) is the flow, a goal's desired level
  is its reference and its gap is the goal, a decision is its block; a closed module is its system
  and every part inside it (a region);
- blocks: a controller or an actuator, and the sampler, hold and junction drawn with it, is its
  block, what it moves or sets directly (its valves) and the setting it steps; a goal's summing
  junction is the goal and its reference, its reference input r the reference; a stock's integrator
  and its output y are the stock, as is a sensor H on it; a disturbance input d is its flow or
  auxiliary; G, the flows that follow other signals, is those flows; a stock's process sum is the
  stock and its flows, a multi-input multi-output process every part inside it, and a closed
  system's Q block its system and every part inside: regions;
- process: an activity of items is no model part.

A part with a shape of its own is stood for by it; one without (a turnover, a point gained inside a
process, a part inside a closed system) by the smallest region holding it, which the page says
("inside P_service"). A block drawn nowhere in the dynamics view (a decision rule, SPEC §1a) is
stood for there by what it moves or sets, through the blocks it commands; a goal nothing acts on, by
the stock it is about."""

from __future__ import annotations

from .spec.ir import Ref

KINDS = ("stock", "flow", "auxiliary", "goal", "block", "system")


def _var(spec, name: str) -> str:
    """A drawn stock node's part: a stock, or an auxiliary (drawn with the stock's id)."""
    return f"auxiliary.{name}" if name in spec.auxiliaries and name not in spec.stocks else f"stock.{name}"


def universe(spec) -> list[str]:
    """Every model part a selection can hold."""
    out = [f"stock.{x}" for x in spec.stocks] + [f"flow.{x}" for x in spec.flows] + \
        [f"auxiliary.{x}" for x in spec.auxiliaries]
    for g in spec.goals:
        out += [f"goal.{g}", f"goal.{g}.r"]
    return out + [f"block.{b}" for b in spec.blocks] + [f"system.{s}" for s in spec.systems]


def system_of(spec, part: str) -> str | None:
    """The system a part is in (a system: the one it is within)."""
    kind, _, rest = part.partition(".")
    if kind == "system":
        return spec.within.get(rest)
    if kind == "goal":
        g = spec.goals.get(rest.split(".")[0])
        return g.system if g else None
    return spec.owner(Ref(kind, rest))


def inside(spec, system: str) -> list[str]:
    """The system and every part in it, or in a system within it."""
    return [p for p in universe(spec) if p == f"system.{system}" or system in spec.chain(system_of(spec, p))]


def _moves(spec, b: str) -> list[str]:
    """What a block moves or sets directly: its flows, its auxiliaries, a goal's setpoint (a cascade)."""
    out = []
    for t in spec.blocks[b].targets():
        if t.kind in ("flow", "auxiliary"):
            out.append(f"{t.kind}.{t.name}")
        elif t.kind == "goal":
            out.append(f"goal.{t.name}.r")
    return out


def _reaches(spec, b: str) -> list[str]:
    """What a block moves or sets, itself or through the blocks it commands."""
    seen, todo, out = set(), [b], []
    while todo:
        x = todo.pop(0)
        if x in seen or x not in spec.blocks:
            continue
        seen.add(x)
        out += [m for m in _moves(spec, x) if m not in out]
        todo += [d.name for d in spec.downstream(x)]
    return out


def _key_parts(spec, key: str) -> list[str]:
    """The parts a block diagram's signal is: a variable, a goal's error or reference, a block's output."""
    if key.startswith("meas."):
        return [".".join(key.split(".")[1:3])]
    head, _, rest = key.partition(".")
    if head in ("stock", "flow", "auxiliary"):
        return [key]
    if head == "goal":
        g, _, what = rest.partition(".")
        return [f"goal.{g}.r"] if what == "r" else [f"goal.{g}"]
    if head == "cmd":
        return [f"block.{rest.split('.')[0]}"]
    for pre in ("held:", "ctl:", "jsum:", "samp:"):
        if key.startswith(pre):
            return [f"block.{key[len(pre):].split(':')[0]}"]
    return []


def blocks_shapes(g: dict, spec) -> dict[str, dict]:
    """Each shape of the block diagram (``blockdiagram.diagram``): the parts it is, and whether it
    holds them (a region) rather than being each of them."""
    from .blockdiagram import _Diagram
    d = _Diagram(spec, {})
    nodes = {n["id"]: n for n in g["nodes"]}

    def of(nid: str) -> tuple[list[str], bool]:
        kind, _, rest = nid.partition(":")
        n = nodes.get(nid, {})
        if kind in ("blk", "smp", "zoh", "jsum"):
            b = rest.split(":")[0]
            if b not in spec.blocks:
                return [], False
            own = [f"block.{b}", *_moves(spec, b)]
            return own + ([d.setting_of[b]] if d.setting_of.get(b) else []), False   # the setting it steps: its memory
        if kind == "sum":
            return [f"goal.{rest}", f"goal.{rest}.r"], False
        if kind == "ref":
            return [f"goal.{rest}.r"], False
        if kind in ("out", "dist", "sen"):
            return [rest], False
        if kind == "col":                             # a collector: the sensor on the flow that brings its items in
            return [n.get("part") or f"flow.{rest.rsplit('.', 1)[0]}"], False
        if kind == "proc" and "." not in rest:        # a multi-input multi-output process: what is inside it
            return list(n.get("inside") or []), True
        if kind == "proc":
            return [rest], False
        if kind == "psum":
            return [rest, *(f"flow.{f.name}" for f in spec.flows_of(rest.split(".", 1)[1]))], True
        if kind == "gen":
            return [f"flow.{f.name}" for f in spec.flows_of(rest.split(".", 1)[1]) if not d.disturbance(f"flow.{f.name}")], False
        if kind == "sys":                             # a closed system: what the model puts in it, and what is drawn in it
            return _union(inside(spec, rest), *(of(x)[0] for x in n.get("holds") or [])), True
        if kind == "term":
            return _key_parts(spec, n.get("label") or rest.split(":", 1)[-1]), False
        return [], False
    out: dict[str, dict] = {}
    for nid, n in nodes.items():
        kind, _, rest = nid.partition(":")
        if kind in ("mux", "demux"):                  # (its process's: chosen with it, never standing for a part)
            out[nid] = {"is": list((nodes.get(f"proc:{rest}") or {}).get("inside") or []), "region": True,
                        "name": n.get("label", nid), "aside": True}
            continue
        is_, region = of(nid)
        out[nid] = {"is": is_, "region": region, "name": _bd_name(n), **({"box": rest} if kind == "sys" else {})}
    frames = {f["id"]: f for f in g.get("frames") or []}

    def within(nid: str, fid: str) -> bool:
        x = (nodes.get(nid) or frames.get(nid) or {}).get("parent")
        while x:
            if x == fid:
                return True
            x = (frames.get(x) or {}).get("parent")
        return False
    for fid, f in frames.items():                     # an open system's frame: the system, holding what is in it
        if f.get("frame") == "system":
            drawn = [x for nid in nodes if within(nid, fid) for x in out[nid]["is"]]
            out[fid] = {"is": _union(inside(spec, f["label"]), drawn), "region": True, "name": f["label"], "system": f["label"]}
    return out


def _union(*lists) -> list[str]:
    return list(dict.fromkeys(x for xs in lists for x in xs))


def _bd_name(n: dict) -> str:
    """How the page names a shape of the block diagram: its function's symbol (P_service, Σ ideas)."""
    fn = n.get("fn") or {}
    if n.get("kind") in ("sum", "mux", "demux"):
        return n.get("label", n["id"])
    if fn.get("sym"):
        return fn["sym"] + (f"_{fn['sub']}" if fn.get("sub") else "")
    return fn.get("name") or n.get("label", n["id"])


def dynamics_shapes(g: dict, spec, model=None) -> dict[str, dict]:
    """Each shape of the system dynamics view (``dynamics.dynamics``, folded)."""
    out: dict[str, dict] = {}

    def of(nid: str) -> list[str]:
        kind, _, rest = nid.partition(":")
        if kind == "stock":
            return [_var(spec, rest)] if spec is not None else _old_var(model, rest)
        if kind == "flow":
            return [f"flow.{rest}"]
        if kind == "desired":
            return [f"goal.{rest}.r"]
        if kind == "gap":
            return [f"goal.{rest}"]
        if kind == "decision":
            return [f"block.{rest}"]
        if kind in ("term", "shadow", "stub"):        # a part drawn elsewhere, or outside: that part
            for cand in (rest, rest.split(":", 1)[-1]):
                if cand.split(":", 1)[0] in ("stock", "flow", "desired", "gap", "decision"):
                    return of(cand)
        return []
    for n in g["nodes"]:
        nid = n["id"]
        if n["kind"] == "system":                     # a closed module: what the model puts in it, and what is drawn in it
            out[nid] = {"is": _union(inside(spec, n["label"]) if spec is not None else [f"system.{n['label']}"],
                                     *(of(x) for x in n.get("holds") or [])), "region": True, "name": n["label"], "box": n["label"]}
        elif n["kind"] != "cloud":
            out[nid] = {"is": of(nid), "region": False, "name": n.get("label") or nid}
    for name in g.get("open") or []:                  # an open system's outline: the system, holding what is in it
        drawn = [x for n in g["nodes"] if name in (n.get("systems") or []) and n.get("role") not in ("shadow", "stub")
                 for x in out.get(n["id"], {}).get("is", [])]                    # (a shadow is a part drawn elsewhere)
        if spec is not None and drawn:
            out[f"hull:{name}"] = {"is": _union(inside(spec, name), drawn), "region": True, "name": name, "system": name}
    return out


def _old_var(model, name: str) -> list[str]:
    s = getattr(model, "stocks", {}).get(name)
    return [f"auxiliary.{name}" if s is not None and s.auxiliary else f"stock.{name}"]


def table(g: dict, model) -> dict:
    """The correspondence for one drawn view: ``shapes`` (each shape: the parts it is, and whether it
    is a region holding them), ``parts`` (each part: the shapes standing for it here) and ``inside``
    (the parts stood for only by a region holding them: that region's name, for the page to say)."""
    from .blockdiagram import spec_of
    spec = getattr(model, "spec", None)
    kind = g.get("kind")
    if kind == "blocks":
        spec = spec_of(model)
        shapes = blocks_shapes(g, spec) if spec is not None else {}
    elif kind == "process":                        # activities of items: no model part is drawn
        shapes = {}
    else:
        shapes = dynamics_shapes(g, spec, model)
    own: dict[str, list[str]] = {}
    held: dict[str, list[tuple[int, str]]] = {}
    for sid, x in shapes.items():
        if x.get("aside"):
            continue
        if x.get("system"):                           # an open system's outline is the system itself
            own.setdefault(f"system.{x['system']}", []).append(sid)
        for p in x["is"]:
            if x.get("system") and p == f"system.{x['system']}":
                continue
            if x["region"]:
                held.setdefault(p, []).append((len(x["is"]), sid))
            else:
                own.setdefault(p, []).append(sid)
    parts = {p: list(dict.fromkeys(ids)) for p, ids in own.items()}
    within: dict[str, list[str]] = {}
    for p, rs in held.items():
        if p in parts:
            continue
        least = min(n for n, _ in rs)                 # the smallest region holding it
        parts[p] = [sid for n, sid in rs if n == least]
        within[p] = parts[p]
    if spec is not None and kind in ("dynamics", "blocks"):
        _stand_ins(spec, g, parts, within)
    loops = _loops(spec, g, shapes) if spec is not None else {}
    return {"view": {"blocks": "blocks", "process": "process"}.get(kind, "dynamics"),
            "shapes": {k: {"is": v["is"], **({"region": True} if v["region"] else {}),
                           **({"system": v.get("system") or v.get("box")} if v.get("system") or v.get("box") else {}),
                           **({"aside": True} if v.get("aside") else {})} for k, v in shapes.items()},
            "parts": parts, "inside": {p: [shapes[s]["name"] for s in ids] for p, ids in within.items()}, "loops": loops,
            **({"colours": colours(spec)} if spec is not None else {})}


HUES, STEPS = 10, 3                                   # the page's palette: ten hues, each in three lightnesses (colours.js)


def colours(spec) -> dict[str, int]:
    """Each model part's colour (a slot of the page's palette: hue ``i % HUES``, lightness ``i // HUES``), the
    same in every view, as the parts are: parts that touch (a stock and its flows, a block and what it moves
    or reads, a goal, its reference and what it holds) get different hues while there are hues to spare, and
    the slots are used evenly, so each group's colour is its own as far as the palette goes."""
    near: dict[str, set[str]] = {}

    def touch(a: str, b: str) -> None:
        if a != b:
            near.setdefault(a, set()).add(b)
            near.setdefault(b, set()).add(a)
    for f in spec.flows.values():
        for x in (f.source, f.target):
            if x:
                touch(f"flow.{f.name}", _var(spec, x))
    for name, goal in spec.goals.items():
        touch(f"goal.{name}", f"goal.{name}.r")
        touch(f"goal.{name}", f"{goal.of.kind}.{goal.of.name}")
    from .blockdiagram import _Diagram
    setting = _Diagram(spec, {}).setting_of
    for b, blk in spec.blocks.items():
        together = [f"block.{b}", *_moves(spec, b), *([setting[b]] if setting.get(b) else [])]   # one shape: told apart
        for i, x in enumerate(together):
            for y in together[i + 1:]:
                touch(x, y)
        for r in blk.reads():
            if r.kind in ("stock", "flow", "auxiliary", "block"):
                touch(f"block.{b}", f"{r.kind}.{r.name}")
            elif r.kind == "goal":
                touch(f"block.{b}", f"goal.{r.name}")
    slots, used, out = HUES * STEPS, [0] * (HUES * STEPS), {}
    for p in universe(spec):
        ns = [out[x] for x in near.get(p, ()) if x in out]
        hues = {n % HUES for n in ns}
        i = min(range(slots), key=lambda s: (s % HUES in hues, s in ns, used[s], s))
        out[p] = i
        used[i] += 1
    return out


def _stand_ins(spec, g: dict, parts: dict, within: dict) -> None:
    """A block drawn nowhere (the dynamics view draws a decision rule as what it decides; the block
    diagram draws a block of the world as the disturbance it is) is stood for by what it moves or
    sets, through the blocks it commands. A goal nothing acts on, in the dynamics view, by the stock
    it is about (whose panel says it); a goal compared inside a controller (it reads the measurement
    itself, its reference beside it), in the block diagram, by that controller."""
    for b in spec.blocks:
        p = f"block.{b}"
        if p in parts and p not in within:
            continue
        reach = _reaches(spec, b)
        got = [sid for m in reach for sid in parts.get(m, []) if m not in within]
        held = [sid for m in reach for sid in within.get(m, [])]
        if got:
            parts[p] = list(dict.fromkeys(got))
            within.pop(p, None)
        elif held:                                    # what it moves is inside a region: so is it
            parts[p] = within[p] = list(dict.fromkeys(held))
    for name in spec.goals:
        p = f"goal.{name}"
        if g.get("kind") == "blocks" and (p not in parts or p in within):
            got = [sid for b in spec.loop(name).controllers for sid in parts.get(f"block.{b}", [])]
            if got:
                parts[p] = list(dict.fromkeys(got))
                within.pop(p, None)
    for n in g["nodes"]:
        for x in n.get("goals") or []:
            for p in (f"goal.{x['name']}", f"goal.{x['name']}.r"):
                if p not in parts or p in within:
                    parts[p] = [n["id"]]
                    within.pop(p, None)


def _loops(spec, g: dict, shapes: dict) -> dict[str, list[str]]:
    """Each loop's members as parts: a feedback loop's (dynamics), by its name; a goal's control loop
    (blocks), by its goal: the goal and its reference, what it holds, the blocks serving it, its
    valves and the way it closes."""
    out: dict[str, list[str]] = {}
    for c in g.get("causalLoops") or []:
        ps = list(c.get("parts") or [])
        for nid in c.get("nodes") or []:
            ps += shapes.get(nid, {}).get("is", []) if not shapes.get(nid, {}).get("region") else []
        out[c["name"]] = list(dict.fromkeys(p for p in ps if p.split(".", 1)[0] in KINDS))
    for name in g.get("loops") or {}:
        if name not in spec.goals or name in out:
            continue
        lp, goal = spec.loop(name), spec.goals[name]
        ps = [f"goal.{name}", f"goal.{name}.r", f"{goal.of.kind}.{goal.of.name}",
              *(f"block.{b}" for b in [*lp.controllers, *lp.actuators]), *(f"flow.{v}" for v in lp.valves),
              *(p for p in lp.through if p.split(".", 1)[0] in KINDS)]
        out[name] = list(dict.fromkeys(ps))
    return out
