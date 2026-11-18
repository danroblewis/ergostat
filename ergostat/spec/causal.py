"""The model's feedback loops as system dynamics names them (SPEC §12a): every cycle of cause and
effect through stocks, flows, auxiliaries, goals and blocks, each with its polarity, R
(reinforcing: the product of its signs is +) or B (balancing: −), or unknown when any link's sign
is not known. Worked out from the model, never written.

The links, each with a sign (+1, -1, or None: not known):

- a flow into its stock is +, out of its stock − (the structure of a stock: it changes only by
  its flows);
- a ``driven-by`` is the sign written on it (``+stock.x``, ``-auxiliary.y``), unknown unsigned;
- what a goal is about drives the goal's error, e = r − y: −;
- a block reading a goal: its error, + (a controller acts on its error: that is what serving a
  goal means); while the goal is off (``.off``, an ``onoff`` or ``proportional`` on it, or the goal
  itself), + for a goal held up (">= 5": off when the error is above 0), − for one held down,
  unknown for "==";
- a built-in block passes its input on with its own sign (``compare`` ``below`` and a falling
  ``lookup`` −; ``expr`` unknown); a machine block does as it is commanded (+); any other reading
  is as written on it (``in: +stock.x``), else, when it reads what a goal it serves is about, as
  the goal's gap says (it acts as that quantity rises above a ceiling, +, or falls below a floor,
  −; not known for "=="), else not known;
- a block's output is + on what it moves, sets or commands (a setpoint it sets raises the error).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ir import Block, Ref, Spec


@dataclass(frozen=True)
class Link:
    source: str                # a part: stock.x, flow.x, auxiliary.x, goal.x, block.x
    target: str
    sign: int | None           # +1, -1, or None (not known)
    kind: str                  # material, influence, goal, reads, acts


@dataclass
class CausalLoop:
    name: str                  # stable: the goal it seeks, else the stocks (or parts) it runs through
    polarity: str | None       # "R", "B", or None (a sign along it is not known)
    parts: list[str]           # in the loop's order, from what its goal is about (or its first stock)
    links: list[Link] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)

    @property
    def unknown(self) -> list[Link]:
        return [x for x in self.links if x.sign is None]


def _part(r: Ref) -> str:
    return f"{r.kind}.{r.name}"


def _held(spec: Spec, goal: str) -> int | None:
    """How a goal's being off follows its error: off past a floor (">=") rises with the error, off
    past a ceiling ("<=") falls with it; for "==" it is off either way, so not known."""
    op = spec.goals[goal].hold.op
    return 1 if op in (">=", ">") else -1 if op in ("<=", "<") else None


def _passes(b: Block) -> int | None:
    """The sign a built-in block gives what it reads."""
    if b.type in ("limit", "delay", "select", "timer", "counter"):
        return 1
    if b.type == "compare":
        return 1 if b.params.get("above") is not None else -1
    if b.type == "lookup":
        ys = [y for _, y in b.params.get("table") or []]
        if len(ys) > 1 and all(a <= c for a, c in zip(ys, ys[1:], strict=False)) and ys[0] != ys[-1]:
            return 1
        if len(ys) > 1 and all(a >= c for a, c in zip(ys, ys[1:], strict=False)) and ys[0] != ys[-1]:
            return -1
    return None


def served(spec: Spec) -> dict[str, list[str]]:
    """The goals each block serves: those it names (``goal:``, or reading ``goal.x``); a block that
    names none, those whose loop closes with it as a controller or an actuator. Worked out once per model."""
    kept = spec.lookups().kept
    if "causal.served" not in kept:
        kept["causal.served"] = _served(spec)
    return {b: list(gs) for b, gs in kept["causal.served"].items()}


def _served(spec: Spec) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for b in spec.blocks.values():
        named = [r.name for r in b.reads() if r.kind == "goal" and r.name in spec.goals]
        if named:
            out[b.name] = list(dict.fromkeys(named))
    for g in spec.goals:
        lp = spec.loop(g)
        if not lp.closes:
            continue
        for b in dict.fromkeys(lp.controllers + lp.actuators):
            if b not in out or g in out[b] or not any(r.kind == "goal" for r in spec.blocks[b].reads()):
                out.setdefault(b, [])
                if g not in out[b]:
                    out[b].append(g)
    return out


def inferred(spec: Spec, b: Block, r: Ref, serves: dict[str, list[str]] | None = None) -> int | None:
    """The sign of a machine block's unsigned reading of a stock, flow or auxiliary, from the goals
    it serves that are about that very quantity: as their gap says (the block acts the more, the
    further the quantity is past the goal: + above a ceiling, − below a floor; not known for "==",
    nor when two goals disagree)."""
    serves = served(spec) if serves is None else serves
    signs = {-_held(spec, g) if _held(spec, g) is not None else None for g in serves.get(b.name, [])
             if spec.goals[g].of.kind == r.kind and spec.goals[g].of.name == r.name}
    return signs.pop() if len(signs) == 1 else None


def input_sign(spec: Spec, b: Block, r: Ref, port: str | None = None, serves: dict[str, list[str]] | None = None) -> int | None:
    """The sign of the link from what ``b`` reads (``r``, at its input ``port``) to ``b``'s output."""
    if r.kind == "goal":
        base = 1 if r.port == "error" else _held(spec, r.name) if r.name in spec.goals else None
    elif r.kind == "block":
        base = 1
    elif b.builtin:
        base = 1
    elif port is not None and port in b.signs:          # as written on it: in: +stock.x
        base = b.signs[port]
    else:                                               # what it does with it is its own, unless a goal it serves says
        base = inferred(spec, b, r, serves)
    if base is None:
        return None
    if b.builtin and b.type not in ("onoff", "proportional"):
        f = _passes(b)
        return None if f is None else base * f
    return base


def links(spec: Spec) -> list[Link]:
    """Every causal link in the model, each once. Worked out once per model (a link is never changed)."""
    kept = spec.lookups().kept
    if "causal.links" not in kept:
        kept["causal.links"] = tuple(_links(spec))
    return list(kept["causal.links"])


def _links(spec: Spec) -> list[Link]:
    out: dict[tuple[str, str], Link] = {}

    def add(src: str, dst: str, sign: int | None, kind: str) -> None:
        if src == dst:
            return
        old = out.get((src, dst))
        if old is not None and old.sign != sign:
            sign = None                                  # two ways of saying it disagree: not known
        out[(src, dst)] = Link(src, dst, sign, old.kind if old else kind)
    for f in spec.flows.values():
        if f.target:
            add(f"flow.{f.name}", f"stock.{f.target}", 1, "material")
        if f.source:
            add(f"flow.{f.name}", f"stock.{f.source}", -1, "material")
    for kind, table in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
        for x in table.values():
            for r in x.driven_by:
                add(_part(r), f"{kind}.{x.name}", x.polarity.get(str(r)), "influence")
    for g in spec.goals.values():
        add(_part(g.of), f"goal.{g.name}", -1, "goal")
    implied = {(t.name, b.goal) for b in spec.blocks.values() if b.implied for t in b.targets() if t.kind == "block"}
    serves = served(spec)
    for b in spec.blocks.values():
        me = f"block.{b.name}"
        reads: list[tuple[str | None, Ref]] = list(b.inputs.items())
        if b.goal and (b.name, b.goal) not in implied:  # a machine block's goal: is its implied onoff's link
            reads.append((None, Ref("goal", b.goal, None if b.type in ("onoff", "proportional") else "off")))
        for port, r in reads:
            sign = input_sign(spec, b, r, port, serves)
            if b.type == "proportional" and r.kind == "goal" and r.port is None:
                gain = b.params.get("gain")
                sign = None if sign is None or not isinstance(gain, int | float) or not gain else sign * (1 if gain > 0 else -1)
            add(_part(r), me, sign, "reads")
        for t in b.targets():
            if t.kind == "block" and t.name in spec.blocks:
                add(me, _part(t), input_sign(spec, spec.blocks[t.name], Ref("block", b.name)), "acts")
            else:
                add(me, _part(t), 1, "acts")
    known = {f"{k}.{n}" for k, t in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries),
                                       ("goal", spec.goals), ("block", spec.blocks)) for n in t}
    return [x for x in out.values() if x.source in known and x.target in known]


def loops(spec: Spec, longest: int = 30, most: int = 300) -> list[CausalLoop]:
    """The simple cycles among the links (each found once), named and signed; at most ``most``,
    none longer than ``longest`` parts. Worked out once per model; each caller is given its own."""
    kept = spec.lookups().kept
    key = ("causal.loops", longest, most)
    if key not in kept:
        kept[key] = _loops(spec, longest, most)
    return [CausalLoop(c.name, c.polarity, list(c.parts), list(c.links), list(c.goals)) for c in kept[key]]


def _loops(spec: Spec, longest: int, most: int) -> list[CausalLoop]:
    ls = links(spec)
    nxt: dict[str, list[Link]] = {}
    for x in ls:
        nxt.setdefault(x.source, []).append(x)
    for v in nxt.values():
        v.sort(key=lambda x: x.target)
    nodes = sorted({x.source for x in ls} | {x.target for x in ls})
    found: list[list[Link]] = []
    for start in nodes:
        if len(found) >= most:
            break
        _from(start, ls, nxt, longest, most, found)
    return _named(spec, found)


def _from(start: str, ls: list[Link], nxt: dict[str, list[Link]], longest: int, most: int, found: list) -> None:
    """The cycles whose first part (by name) is ``start``: through parts after it, and only those
    that can still come back to it."""
    prev: dict[str, list[str]] = {}
    for x in ls:
        if x.source >= start and x.target >= start:
            prev.setdefault(x.target, []).append(x.source)
    back, todo = {start}, [start]
    while todo:
        for p in prev.get(todo.pop(), []):
            if p not in back:
                back.add(p)
                todo.append(p)
    stack: list[Link] = []
    on = {start}

    def walk(n: str) -> None:
        for x in nxt.get(n, []):
            if len(found) >= most:
                return
            if x.target == start:
                found.append([*stack, x])
            elif x.target > start and x.target not in on and x.target in back and len(stack) + 1 < longest:
                on.add(x.target)
                stack.append(x)
                walk(x.target)
                stack.pop()
                on.discard(x.target)
    walk(start)


def _named(spec: Spec, cycles: list[list[Link]]) -> list[CausalLoop]:
    out = []
    for cyc in cycles:
        parts = [x.source for x in cyc]
        goals = sorted(p.split(".", 1)[1] for p in parts if p.startswith("goal."))
        if goals:                                        # read it from what its goal is about
            first = next(i for i, p in enumerate(parts) if p == f"goal.{goals[0]}")
            first = (first - 1) % len(parts)
        else:
            stocks = sorted(p for p in parts if p.startswith("stock."))
            first = parts.index(stocks[0]) if stocks else parts.index(min(parts))
        cyc = cyc[first:] + cyc[:first]
        signs = [x.sign for x in cyc]
        if any(s is None for s in signs):
            pol = None
        else:
            prod = 1
            for s in signs:
                prod *= s
            pol = "R" if prod > 0 else "B"
        out.append(CausalLoop("", pol, [x.source for x in cyc], cyc, goals))
    out.sort(key=lambda lp: (len(lp.parts), lp.parts))
    for lp, name in zip(out, names(spec, out), strict=True):
        lp.name = name
    out.sort(key=lambda lp: (lp.name, len(lp.parts), lp.parts))
    return out


# which members name a loop best when its siblings share its head: a flow (the mechanism, "via
# rejected"), then a stock, an auxiliary, a goal, a block
_ORDER = ("flow", "stock", "auxiliary", "goal", "block")


def names(spec: Spec, ls: list[CausalLoop]) -> list[str]:
    """Each loop's name (SPEC §12a), in the order of ``ls`` (shortest first): the name the model
    gives it (``loops:``: the shortest loop through every part named, or seeking the goal named);
    else its head (the goal it seeks, else the stock it runs through first, else its first part),
    the shortest loop with that head taking it bare, and every other loop with that head the head
    "via" the members no sibling has (as few as tell it apart). Never numbered, never a list of
    everything in it."""
    out: dict = {}
    taken: set[str] = set()
    for nl in spec.named_loops.values():                # the model's own names first
        want = {f"{r.kind}.{r.name}" for r in nl.through}
        for lp in ls:
            if id(lp) in out:
                continue
            if (nl.goal and f"goal.{nl.goal}" in lp.parts) or (want and want <= set(lp.parts)):
                out[id(lp)] = nl.name
                taken.add(nl.name)
                break
    heads: dict[str, list[CausalLoop]] = {}
    for lp in ls:
        if id(lp) in out:
            continue
        stocks = [p for p in lp.parts if p.startswith("stock.")]
        head = lp.goals[0] if lp.goals else (stocks[0] if stocks else lp.parts[0]).split(".", 1)[1]
        heads.setdefault(head, []).append(lp)
    for head, group in heads.items():
        for i, lp in enumerate(group):
            if i == 0 and head not in taken:
                name = head
            else:
                others = [set(o.parts) for o in group if o is not lp]
                cand = sorted((p for p in dict.fromkeys(lp.parts) if p.split(".", 1)[1] != head),
                              key=lambda p: (_ORDER.index(p.split(".", 1)[0]) if p.split(".", 1)[0] in _ORDER else 9,
                                             lp.parts.index(p)))
                pick: list[str] = []
                left = others
                for p in sorted(cand, key=lambda p: (-sum(p not in o for o in left), cand.index(p))):
                    if not left:
                        break
                    if all(p in o for o in left):
                        continue
                    pick.append(p)
                    left = [o for o in left if p in o]
                pick.sort(key=cand.index)
                words = [p.split(".", 1)[1] for p in pick]
                name = f"{head} via {' and '.join(words)}" if words else f"{head}, the other way round"
            base, k = name, 1
            while name in taken:                          # (two loops through the very same parts)
                k += 1
                name = f"{base}, {['', '', 'again', 'once more', 'a fourth way'][k] if k < 5 else 'yet again'}"
            taken.add(name)
            out[id(lp)] = name
    return [out[id(lp)] for lp in ls]
