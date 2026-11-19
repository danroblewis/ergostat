"""The models the layout rules (tests/layout_rules.py) are run over: every example, and generated ones of the shapes
the diagrams must draw well, small to medium: chains, fan-outs, joins, rework loops, many clouds, links across
systems, cascades, auxiliaries, and mixes of them. Shared by tests/test_diagram_rendering.py (a fast subset) and
scripts/layout_corpus.py (the whole corpus). Also the views each model is drawn in, and a record of items moving
through their states for the Process view."""
from __future__ import annotations

import random
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted(p.name for p in (ROOT / "examples").iterdir() if (p / "ergostat.yaml").exists())
SHAPES = ["chain", "fanout", "join", "rework", "clouds", "cross", "cascade", "aux", "mixed", "drains"]


# ------------------------------------------------------------------ the views

def views_of(kind: str, tree: dict, systems: int | None = None) -> list[str]:
    """A view's queries: the whole, everything open, each system open, each system alone (the first `systems` of them
    only, when given: a generated model's systems are alike)."""
    v = f"view={kind}"
    tree = dict(list(tree.items())[:systems]) if systems is not None and tree else tree
    return [v, *([f"{v}&open=*"] if tree else []), *(f"{v}&open={s}" for s in tree), *(f"{v}&system={s}" for s in tree)]


def view_tag(q: str) -> str:
    """A file name for a view's query."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", q.replace("view=", "").replace("&", "__").replace("=", "-").replace("*", "all"))


# ------------------------------------------------------------------ generated models

class Gen:
    """One model, written as ergostat.yaml: stocks, flows (a missing end is a cloud), goals and the blocks that hold
    them, auxiliaries driven by stocks, systems, and an item kind per chain (for the Process view)."""

    def __init__(self, name: str, rnd: random.Random):
        self.name, self.r = name, rnd
        self.systems: dict[str, dict] = {}
        self.stocks: dict[str, dict] = {}
        self.flows: dict[str, dict] = {}
        self.goals: dict[str, dict] = {}
        self.blocks: dict[str, dict] = {}
        self.aux: dict[str, dict] = {}
        self.items: dict[str, dict] = {}

    def stock(self, name: str, system: str | None = None) -> str:
        self.stocks[name] = {"unit": "items", "sensor": {"manual": True}, **({"system": system} if system else {})}
        return name

    def flow(self, name: str, frm: str | None, to: str | None, system: str | None = None, **kw) -> str:
        f = {**({"from": frm} if frm else {}), **({"to": to} if to else {}), **({"system": system} if system else {}), **kw}
        self.flows[name] = f
        return name

    def hold(self, stock: str, flow: str, system: str | None = None, rate_goal: bool = False) -> None:
        """A goal on the stock and a block that moves the flow to hold it."""
        g = f"{stock}-ok"
        self.goals[g] = {"stock": stock, "hold": "<= 5", **({"system": system} if system else {})}
        self.blocks[f"{stock}-keeper"] = {"type": "program", "run": "echo 1", "goal": g, "out": f"flow.{flow}",
                                          **({"system": system} if system else {})}

    def chain(self, prefix: str, n: int, system: str | None = None, inflow: bool = True, outflow: bool = True,
              drops: float = 0.0, held: float = 0.6, kind: bool = True) -> list[str]:
        """n stocks in a row, a cloud in and out; some stocks dropping work to a cloud; goals held by blocks."""
        ss = [self.stock(f"{prefix}{i}", system) for i in range(n)]
        if inflow:
            self.flow(f"{prefix}-arrive", None, ss[0], system)
        for a, b in zip(ss, ss[1:], strict=False):
            f = self.flow(f"{a}-to-{b}", a, b, system)
            if self.r.random() < held:
                self.hold(a, f, system)
        if outflow:
            f = self.flow(f"{ss[-1]}-done", ss[-1], None, system)
            if self.r.random() < held:
                self.hold(ss[-1], f, system)
        for s in ss[:-1]:
            if self.r.random() < drops:
                self.flow(f"{s}-dropped", s, None, system)
        if kind and n >= 2:
            k = f"k{prefix}".replace("-", "")
            self.items[k] = {"id": f"{k}/*", "states": ss + ["gone"],
                             "on": {**{f"{k}.to-{b}": b for b in ss[1:]}, f"{k}.gone": "gone"}}
        return ss

    def write(self, d: Path) -> Path:
        import yaml
        d.mkdir(parents=True, exist_ok=True)
        doc = {"name": self.name}
        for key, v in (("systems", self.systems), ("items", self.items), ("auxiliaries", self.aux), ("stocks", self.stocks),
                       ("flows", self.flows), ("goals", self.goals), ("blocks", self.blocks)):
            if v:
                doc[key] = v
        (d / "ergostat.yaml").write_text(yaml.safe_dump(doc, sort_keys=False, width=200))
        return d


def generate(name: str, shape: str, seed: int) -> Gen:
    r = random.Random(f"{shape}:{seed}")
    m = Gen(name, r)
    size = r.choice([2, 3, 3, 4, 4, 5, 6, 7, 8])
    if shape == "chain":
        m.chain("s", size, drops=r.choice([0, 0.2, 0.5]))
    elif shape == "drains":                    # every stock its own inflow and drain, from and to clouds
        ss = m.chain("s", max(2, size // 2), drops=1.0)
        for s in ss[1:]:
            f = m.flow(f"{s}-extra", None, s)
            if r.random() < 0.5:
                m.hold(s, f) if f"{s}-keeper" not in m.blocks else None
    elif shape == "fanout":                    # one stock feeding several
        src = m.chain("in", r.choice([1, 2]), outflow=False)[-1]
        for i in range(r.choice([2, 3, 4])):
            ss = m.chain(f"b{i}x", r.choice([1, 2, 3]), inflow=False, kind=False)
            f = m.flow(f"split-{i}", src, ss[0])
            if r.random() < 0.5:
                m.hold(ss[0], f) if f"{ss[0]}-keeper" not in m.blocks else None
    elif shape == "join":                      # several chains into one
        dst = m.stock("merged")
        m.flow("merged-done", "merged", None)
        m.hold("merged", "merged-done")
        for i in range(r.choice([2, 3, 4])):
            ss = m.chain(f"j{i}x", r.choice([1, 2, 3]), outflow=False, kind=False)
            m.flow(f"join-{i}", ss[-1], dst)
    elif shape == "rework":                    # a flow back up the chain
        ss = m.chain("s", max(3, size), drops=0.3)
        for _ in range(r.choice([1, 1, 2])):
            a = r.randrange(1, len(ss))
            b = r.randrange(0, a)
            m.flow(f"{ss[a]}-back-{ss[b]}", ss[a], ss[b])
    elif shape == "clouds":                    # many flows from and to clouds about few stocks
        ss = [m.stock(f"pool{i}") for i in range(r.choice([1, 2, 3]))]
        for s in ss:
            for j in range(r.choice([1, 2, 3])):
                m.flow(f"{s}-in{j}", None, s)
            for j in range(r.choice([1, 2, 3])):
                f = m.flow(f"{s}-out{j}", s, None)
                if j == 0:
                    m.hold(s, f)
        if len(ss) > 1:
            m.flow("pool-link", ss[0], ss[1])
    elif shape == "cross":                     # systems, a chain in each, flows and links across them
        n = r.choice([2, 3, 4])
        outer = r.random() < 0.4
        if outer:
            m.systems["whole"] = {"description": "everything"}
        last = None
        for i in range(n):
            sys = f"sys{i}"
            m.systems[sys] = {"description": f"system {i}", **({"within": "whole"} if outer else {})}
            ss = m.chain(f"c{i}x", r.choice([1, 2, 3]), system=sys, inflow=last is None, drops=0.2)
            if last:
                m.flow(f"hand-{i}", last, ss[0], sys)
            last = ss[-1] if r.random() < 0.7 else None
            if last is None and i < n - 1:
                last = ss[0]
            if i >= 1 and r.random() < 0.5:     # a flow driven from another system
                f = next(iter(k for k, v in m.flows.items() if v.get("system") == sys))
                m.flows[f]["driven-by"] = f"stock.c{i - 1}x0"
    elif shape == "cascade":                   # a goal on a flow, set by an outer controller
        m.systems.update({"plant": {"description": "the whole"}, "room": {"within": "plant"}, "heater": {"within": "plant"}})
        m.stock("temperature", "room")
        m.stock("fuel", "heater")
        m.flow("heat-in", None, "temperature", "room", **{"driven-by": "flow.burn"})
        m.flow("heat-out", "temperature", None, "room")
        m.flow("burn", "fuel", None, "heater")
        m.flow("refill", None, "fuel", "heater")
        m.goals["warm"] = {"system": "room", "stock": "temperature", "hold": ">= 20"}
        m.goals["burner-rate"] = {"system": "heater", "flow": "burn", "hold": "== 2"}
        m.blocks["thermostat"] = {"system": "room", "type": "proportional", "goal": "warm", "gain": 0.5, "out": "goal.burner-rate"}
        m.blocks["burner"] = {"system": "heater", "type": "program", "run": "echo 1", "in": "goal.burner-rate", "out": "flow.burn"}
        if r.random() < 0.5:
            m.chain("extra", r.choice([1, 2, 3]), system="room", kind=False)
        if r.random() < 0.5:
            m.goals["fuel-ok"] = {"system": "heater", "stock": "fuel", "hold": ">= 10"}
            m.blocks["refiller"] = {"system": "heater", "type": "program", "run": "echo 1", "goal": "fuel-ok", "out": "flow.refill"}
    elif shape == "aux":                       # auxiliaries read from stocks, driving flows
        ss = m.chain("s", max(2, size - 2), drops=0.3)
        for i in range(r.choice([1, 2, 3])):
            a = f"load{i}"
            src = r.sample(ss, k=min(len(ss), r.choice([1, 2])))
            m.aux[a] = {"unit": "share", "sensor": {"manual": True}, "driven-by": [f"+stock.{s}" for s in src]}
            f = r.choice(list(m.flows))
            m.flows[f].setdefault("driven-by", f"aux.{a}" if False else f"+auxiliary.{a}")
    elif shape == "mixed":                     # two systems, rework, a fan-out, drains, an auxiliary
        m.systems.update({"front": {"description": "intake"}, "back": {"description": "work"}})
        a = m.chain("f", r.choice([2, 3]), system="front", outflow=False, drops=0.5)
        b = m.chain("w", r.choice([2, 3, 4]), system="back", inflow=False, drops=0.3)
        m.flow("handoff", a[-1], b[0], "back")
        m.hold(a[-1], "handoff", "front") if f"{a[-1]}-keeper" not in m.blocks else None
        if len(b) >= 3:
            m.flow("redo", b[2], b[1], "back")
        c = m.chain("x", r.choice([1, 2]), system="back", inflow=False, kind=False)
        m.flow("side", b[0], c[0], "back")
        m.aux["pressure"] = {"unit": "share", "sensor": {"manual": True}, "driven-by": [f"+stock.{b[0]}"], "system": "back"}
        m.flows["f-arrive"]["driven-by"] = "-auxiliary.pressure"
    return m


def generated(out: Path, n: int, seed: int = 1) -> list[tuple[str, Path]]:
    """n generated models, the shapes in turn, written under out (once: kept if there)."""
    from ergostat import model as mdl
    got = []
    i = 0
    while len(got) < n and i < n * 3:
        shape = SHAPES[i % len(SHAPES)]
        name = f"gen-{shape}-{seed}-{i:03d}"
        d = out / name
        i += 1
        if not (d / "ergostat.yaml").exists():
            generate(name, shape, seed * 1000 + i).write(d)
        try:
            m = mdl.load(d)
            if [c for c in mdl.check(m, warnings=False) if c[0] == "error"]:
                raise ValueError("does not check")
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            continue
        got.append((name, d))
    return got


def all_models(out: Path, n: int, seed: int = 1, examples: list[str] | None = None) -> list[tuple[str, Path]]:
    """The examples (all of them when examples is [], none when None, else those named) and n generated models."""
    ex = [] if examples is None else (EXAMPLES if not examples else [e for e in EXAMPLES if e in examples])
    return [(e, ROOT / "examples" / e) for e in ex] + (generated(out, n, seed) if n else [])


def weight(d: Path) -> int:
    """About how long a model takes to draw: its files' size."""
    return sum(f.stat().st_size for f in Path(d).rglob("*.yaml"))


# ------------------------------------------------------------------ a record for the Process view

def item_id(glob: str, n: str) -> str:
    """An id its kind's glob matches."""
    out = re.sub(r"\[[^\]]*\]", "x", glob)
    return out.replace("**", n).replace("*", n).replace("?", "x")


def seed_workflows(d: Path, now: float, items: int = 4) -> dict:
    """A record for every kind of item the model declares, in the project at d: each item arrives, moves through
    its kind's states by the events its kind maps (one item in two goes back a state and on again: rework), and
    the first events of each kind's items are caused by an event on an item of the kind before it."""
    from ergostat import model as mdl
    from ergostat.spec.item_systems import BUILT_IN
    from ergostat.store import Project
    p = Project(mdl.load(d))
    spec = p.model.spec
    kinds = [k for k in spec.items.values() if not k.name.startswith(BUILT_IN + ".")]
    last = None
    t = now - 3000
    seen = {}
    for ki, k in enumerate(kinds):
        to = {}
        for ty, st in k.on.items():
            to.setdefault(st, ty)
        made, cause = 0, last
        for i in range(items):
            it = item_id(k.id, f"pm{ki}x{i}")
            if not k.matches(it) or any(x.matches(it) for x in kinds[:ki]):
                continue
            e = p.events.add(f"{k.name}.opened", item=it, causedby=cause["id"] if cause and i < 2 else None, at=t)
            made += 1
            t += 7
            path = [st for st in k.states[1:] if st in to]
            if i % 2 and len(path) >= 2:
                path = path[:2] + [path[0]] + path[1:]
            for st in path:
                e = p.events.add(to[st], item=it, at=t)
                t += 11
            if not k.states:
                p.events.add(f"{k.name}.noted", item=it, at=t)
                e = p.events.add(f"{k.name}.noted", item=it, at=t + 3)
            last = e
            t += 5
        seen[k.name] = made
    return {k: n for k, n in seen.items() if n}
