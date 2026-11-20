"""How the model is divided into systems, measured: the computed rung of an architecture review
(docs/proposals/architecture.md). Each is a note for ``check``, never an error, worked out from the structure
alone (no run):

- ``system-splits``: a system whose loose parts (not already its subsystems) fall into clusters with few links
  between them (Newman's modularity, greedy agglomeration: an analogue of clustering a design structure matrix);
  a system whose clusters are its own subsystems is nearly decomposable, said by ``explain``, never asked of;
- ``systems-merge``: two systems with more links between them than inside the smaller (coupling over cohesion);
- ``interface``: a boundary crossed badly: material passed through clouds on both sides, a block outside moving
  what a system's own goals hold, or many information links (what crosses is ``Spec.interface``);
- ``time-scales``: a system whose parts' time constants are more than ten times apart (singular perturbation: the
  fast ones are an inner system, given its setpoint by the slow);
- ``purpose``: a system that does not say what it is for, one whose blocks act for no goal in it, a goal traced to no
  purpose.

``size`` is each system's parts, feedback loops and depth, for ``explain`` and the system's panel."""

from __future__ import annotations

from collections import Counter

from .ir import Ref, Spec, once_made

SPLIT_Q = 0.4      # the split's modularity at or above which its clusters are well separated (Newman and Girvan 2004: 0.3 is structure)
SMALL = 20         # a system of fewer parts is read at a glance: not split
CLUSTER = 4        # a smaller cluster is folded into the one it links to most
MERGE = 1.0        # links between two systems, over the links inside the smaller: from this, they are one
MERGE_LEAST = 3
WIDE = 10          # information links across one boundary from which the interface is wide (a heuristic)
GAP = 10.0         # time constants more than this many times apart are two time scales
PARTS = (("stock", "stocks"), ("flow", "flows"), ("auxiliary", "auxiliaries"), ("goal", "goals"), ("block", "blocks"))


def _parts(spec: Spec) -> dict[str, str | None]:
    """Every part (an implied block left out: it is its goal's; a part a once template made left out: its architecture
    is the template's) → the system it is directly in."""
    return {f"{k}.{n}": x.system for k, t in PARTS for n, x in getattr(spec, t).items()
            if not (k == "block" and x.implied) and not once_made(spec, x)}


def _edges(spec: Spec) -> Counter:
    """The causal links as an undirected, weighted graph: (a, b), a < b → how many links join them (an implied
    block's links are its goal's)."""
    from .causal import links
    kept = spec.lookups().kept
    if "architecture.edges" not in kept:
        parts = _parts(spec)
        as_ = {f"block.{b.name}": f"goal.{b.goal}" for b in spec.blocks.values() if b.implied and b.goal}
        ends = [tuple(sorted((as_.get(x.source, x.source), as_.get(x.target, x.target)))) for x in links(spec)]
        kept["architecture.edges"] = Counter(e for e in ends if e[0] != e[1] and e[0] in parts and e[1] in parts)
    return kept["architecture.edges"]


def _chains(spec: Spec) -> dict[str, list[str]]:
    """Every part → the systems it is in, innermost first: worked out once per model."""
    kept = spec.lookups().kept
    if "architecture.chains" not in kept:
        kept["architecture.chains"] = {p: spec.chain(s) for p, s in _parts(spec).items()}
    return kept["architecture.chains"]


def _node(spec: Spec, system: str | None, ch: list[str]) -> str | None:
    """A part in the systems ``ch`` as drawn inside ``system``: itself, the subsystem it is in, or None when outside."""
    if system is None:
        return f"system.{ch[-1]}" if ch else ""
    if system not in ch:
        return None
    i = ch.index(system)
    return "" if i == 0 else f"system.{ch[i - 1]}"


def _graph(spec: Spec, system: str | None) -> tuple[Counter, Counter]:
    """A system's parts, each subsystem as one node: (node → parts it stands for, (a, b) → links)."""
    kept = spec.lookups().kept
    if "architecture.members" not in kept:            # each system's parts, and each part's links, once
        members: dict = {}
        for p, ch in _chains(spec).items():
            for s in [None, *ch]:
                members.setdefault(s, []).append(p)
        near: dict = {}
        for (a, b), w in _edges(spec).items():
            near.setdefault(a, []).append((b, w))
        kept["architecture.members"] = members, near
    members, near = kept["architecture.members"]
    chains = _chains(spec)
    where = {p: (_node(spec, system, chains[p]) or p) for p in members.get(system, ())}
    nodes = Counter(where.values())
    edges: Counter = Counter()
    for a, x in where.items():
        for b, w in near.get(a, ()):
            y = where.get(b)
            if y:                                    # (inside one subsystem: its own weight, as a loop on its node)
                edges[tuple(sorted((x, y)))] += w
    return nodes, edges


def modularity(groups: list[set[str]], edges: Counter) -> float:
    m = sum(edges.values())
    if not m:
        return 0.0
    of = {n: i for i, g in enumerate(groups) for n in g}
    inside, deg = Counter(), Counter()
    for (a, b), w in edges.items():
        deg[of[a]] += w
        deg[of[b]] += w
        if of[a] == of[b]:
            inside[of[a]] += w
    return sum(inside[i] / m - (deg[i] / (2 * m)) ** 2 for i in range(len(groups)))


def clusters(nodes: Counter, edges: Counter) -> list[set[str]]:
    """Greedy modularity clustering (Clauset, Newman and Moore 2004): join the two linked groups whose joining
    raises the modularity most, while one does. Then a group of fewer than ``CLUSTER`` parts joins the group it
    links to most, and two groups joined by more than a tenth of the links inside the smaller are one: what is left
    is well separated (a stage of a pipeline is not: it is tied to the next by its flow)."""
    m = sum(edges.values())
    groups = {n: {n} for n in nodes}
    size = lambda g: sum(nodes[n] for n in groups[g])   # noqa: E731  (parts: a subsystem's node stands for all of its)
    if not m:
        return list(groups.values())
    between: dict[tuple[str, str], float] = Counter()
    a, inside = Counter(), Counter()
    for (x, y), w in edges.items():
        a[x] += w / (2 * m)
        a[y] += w / (2 * m)
        if x == y:
            inside[x] += w
        else:
            between[(x, y)] += w
            between[(y, x)] += w

    def join(i: str, j: str) -> None:              # j into i
        groups[i] |= groups.pop(j)
        a[i] += a.pop(j, 0.0)
        inside[i] += inside.pop(j, 0) + between.get((i, j), 0)
        for (x, y) in [k for k in between if j in k]:
            w = between.pop((x, y))
            x, y = (i if x == j else x), (i if y == j else y)
            if x != y:
                between[(x, y)] = between.get((x, y), 0) + w
    while True:
        best = max(((2 * (w / (2 * m) - a[x] * a[y]), x, y) for (x, y), w in between.items() if x < y), default=None)
        if best is None or best[0] <= 1e-12:
            break
        join(best[1], best[2])
    while True:
        linked = {x for x, _ in between}
        small = [g for g in groups if g in linked and size(g) < CLUSTER]
        tied = [(w, x, y) for (x, y), w in between.items() if x < y and w > min(inside[x], inside[y]) / 10]
        if small:
            g = min(small, key=lambda k: (size(k), k))
            join(max((w, y) for (x, y), w in between.items() if x == g)[1], g)
        elif tied:
            _, x, y = max(tied)
            join(x, y)
        else:
            break
    return sorted(groups.values(), key=lambda g: (-len(g), sorted(g)))


def _named(spec: Spec, group: set[str], most: int = 4) -> str:
    """A cluster, by its goals and subsystems, else its stocks, else its parts."""
    order = sorted(group, key=lambda p: (not p.startswith(("goal.", "system.")), not p.startswith("stock."), p))
    return ", ".join(order[:most]) + (f" and {len(order) - most} more" if len(order) > most else "")


def decomposition(spec: Spec, system: str | None) -> dict | None:
    """A system's (or the top level's) clusters when they are well separated: {groups, across, q}; None otherwise."""
    kept = spec.lookups().kept
    key = ("architecture.decomposition", system)
    if key not in kept:
        nodes, edges = _graph(spec, system)
        got = None
        if sum(nodes.values()) >= SMALL:
            gs = [g for g in clusters(nodes, edges) if sum(nodes[n] for n in g) >= CLUSTER]
            if len(gs) >= 2:
                rest = set(nodes) - set().union(*gs)
                q = modularity(gs + ([rest] if rest else []), edges)
                of = {n: i for i, g in enumerate(gs) for n in g}
                across = sum(w for (x, y), w in edges.items() if x in of and y in of and of[x] != of[y])
                got = {"groups": gs, "across": across, "q": q} if q >= SPLIT_Q else None
        kept[key] = got
    return kept[key]


def _listed(spec: Spec, gs: list[set[str]], most: int = 6) -> str:
    return "; ".join(f"[{_named(spec, g)}]" for g in gs[:most]) + (f"; and {len(gs) - most} more" if len(gs) > most else "")


def nearly_decomposable(spec: Spec, system: str | None) -> str | None:
    """Said by ``explain``, never a request: a system whose subsystems are the well-separated clusters is nearly
    decomposable (Simon 1962), as a good hierarchy is: each subsystem can be understood and redesigned alone."""
    d = decomposition(spec, system)
    if not d or not all(n.startswith("system.") for g in d["groups"] for n in g):
        return None
    return (f"nearly decomposable: its systems fall into {len(d['groups'])} groups with {d['across']} "
            f"link{'s' * (d['across'] != 1)} between them (modularity {d['q']:.2f}); each can be understood and "
            f"redesigned alone")


def splits(spec: Spec, say) -> None:
    for system in [None, *sorted(spec.systems)]:
        d = decomposition(spec, system)
        if not d:
            continue
        loose = [g for g in d["groups"] if not any(n.startswith("system.") for n in g)]
        if not loose:
            continue                                     # its clusters are its subsystems: a good hierarchy, not a defect
        who = f"system {system}" if system else "the model"
        say("system-splits", f"{who}: its parts fall into {len(d['groups'])} clusters with {d['across']} "
            f"link{'s' * (d['across'] != 1)} between them (modularity {d['q']:.2f})"
            + (f"; {len(loose)} of them in no system of their own: " if len(loose) < len(d["groups"]) else ": ")
            + f"{_listed(spec, loose)}. Each may be a system of its own (systems:, and system: on its parts), "
            f"redesigned on its own; or a link between them is missing", f"system.{system}" if system else "model")


def merges(spec: Spec, say) -> None:
    edges, chains = _edges(spec), _chains(spec)
    inside = Counter()
    for (x, y), w in edges.items():
        for s in set(chains[x]) & set(chains[y]):
            inside[s] += w
    chatty: dict[str, list[str]] = {}
    for parent in {spec.within.get(s) for s in spec.systems}:
        sibs = set(spec.subsystems(parent))
        own = {p: next((s for s in ch if s in sibs), None) for p, ch in chains.items()}
        cross = Counter(tuple(sorted((own[x], own[y]))) for (x, y), w in edges.items() for _ in range(w)
                        if own[x] and own[y] and own[x] != own[y])
        for (x, y), n in cross.items():
            small, big = sorted((x, y), key=lambda s: (inside[s], s))
            if n >= MERGE_LEAST and n >= MERGE * inside[small]:
                chatty.setdefault(small, []).append(f"{big} ({n} links between them; {inside[small]} inside {small}, "
                                                    f"{inside[big]} inside {big})")
    for s, said in sorted(chatty.items()):
        say("systems-merge", f"system {s}: more of its links go to {'; '.join(said)} than stay inside it: the boundary "
            f"cuts through one system. Merge them (system: on its parts), or draw the boundary where few links cross",
            f"system.{s}")


def interfaces(spec: Spec, say) -> None:
    from .findings import base_unit, unit_of
    goals_in = {s: [g for g in spec.goals.values() if spec.inside(Ref("goal", g.name), s)] for s in spec.systems}
    for s in sorted(spec.systems):
        ports = spec.interface(s)
        flags = []
        for f in spec.flows.values():                    # a flow from a cloud, driven by a flow into one, across it
            for r in f.driven_by:
                g = spec.flows.get(r.name) if r.kind == "flow" else None   # (of one unit: one material)
                if g is None or f.source is not None or g.target is not None or not base_unit(unit_of(spec, r)) \
                        or base_unit(unit_of(spec, r)) != base_unit(unit_of(spec, Ref("flow", f.name))):
                    continue
                if spec.inside(Ref("flow", f.name), s) and not spec.inside(r, s) or \
                        spec.inside(r, s) and spec.owner(Ref("flow", f.name)) is None:
                    flags.append(f"material crosses through clouds on both sides: flow.{g.name} leaves for a cloud and "
                                 f"flow.{f.name} arrives from one, driven by it; one flow from {g.name}'s stock to "
                                 f"{f.name}'s keeps what is conserved")
        held = {f"flow.{x}" for g in goals_in[s] for x in spec.loop(g.name).valves} | \
            {f"block.{x}" for g in goals_in[s] for lp in [spec.loop(g.name)] for x in (*lp.actuators, *lp.controllers)}
        material = {p["part"] for p in ports if p["kind"] == "material"}
        for p in ports:
            kind, name = p["part"].split(".", 1)
            arrival = kind == "flow" and spec.flows[name].source is None            # work filed in: a hand-off
            if p["dir"] == "in" and p["kind"] in ("action", "command") and p["part"] not in material \
                    and p["part"] in held and not arrival:
                flags.append(f"{', '.join(p['peers'])} (outside) {'moves' if p['kind'] == 'action' else 'commands'} "
                             f"{p['part']}, which its own goals' loops use: it reaches into its internals; a setpoint for "
                             f"one of its goals is the interface a hierarchy uses")
        info = sum(len(p["peers"]) for p in ports if p["kind"] in ("signal", "influence"))
        if info >= WIDE:
            flags.append(f"{info} information links cross it: a wide interface; a few measures it shows (show:) would "
                         f"say the same")
        if flags:
            kinds = Counter()
            for p in ports:
                kinds[p["kind"]] += len(p["peers"])
            say("interface", f"system {s}: what crosses its boundary: "
                + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())) + ". " + "; ".join(flags), f"system.{s}")


def taus(spec: Spec) -> dict[str, float]:
    """Each part's time constant (hours) as the model stands: a stock's own drain and a delay's time at its start
    (``numbers/extremes.py``, one evaluation, no run), and a goal's loop by its identified process."""
    kept = spec.lookups().kept
    if "architecture.taus" not in kept:
        out: dict[str, float] = {}
        try:                                             # (no equation: no time constant, and nothing to import)
            if any(x.equation is not None for t in (spec.flows, spec.auxiliaries) for x in t.values()):
                from ..numbers.extremes import time_constants
                out = time_constants(spec) or {}
        except Exception:                                # equations that cannot be worked out: no time scales said
            out = {}
        for g in spec.goals.values():
            tau = (g.process or {}).get("tau")
            if isinstance(tau, int | float) and tau > 0:
                out[f"goal.{g.name}"] = tau / 3600.0
        kept["architecture.taus"] = out
    return kept["architecture.taus"]


def time_scales(spec: Spec, say) -> None:
    """A screen, not modes: each stock's own time constant (and each delay's), not the eigenvalues of the whole."""
    from ..durations import human
    ts, chains, edges = taus(spec), _chains(spec), _edges(spec)
    near: dict[str, set[str]] = {}
    for x, y in edges:
        near.setdefault(x, set()).add(y)
        near.setdefault(y, set()).add(x)
    for s in [None, *sorted(spec.systems)]:
        mine = sorted((t, p) for p, t in ts.items() if p in chains and (chains[p][:1] or [None])[0] == s)
        if len(mine) < 2:
            continue
        gap, i = max((mine[j + 1][0] / mine[j][0], j) for j in range(len(mine) - 1))
        if gap <= GAP:
            continue
        fast, slow = mine[:i + 1], mine[i + 1:]
        if not _coupled({p for _, p in fast}, {p for _, p in slow}, near, {p for p, ch in chains.items() if s in ch[:1]
                                                                              or (s is None and not ch)}):
            continue                                     # two time scales that never meet: nothing to arrange
        said = lambda xs: ", ".join(f"{p} {human(max(t * 3600, 1))}" for t, p in xs)   # noqa: E731
        say("time-scales", f"{f'system {s}' if s else 'the model'}: its parts run on time scales {gap:.0f} times apart: "
            f"fast [{said(fast)}], slow [{said(slow)}], linked within it. Each stock's own time constant is a screen, "
            f"not the system's modes; if they hold, the fast settle before the slow move (singular perturbation), so "
            f"they are a candidate inner system, given its setpoint by the slow (hierarchical control)",
            f"system.{s}" if s else "model")


def _coupled(a: set[str], b: set[str], near: dict[str, set[str]], within: set[str]) -> bool:
    """Whether a path of links inside ``within`` joins a part of ``a`` to one of ``b``."""
    seen, todo = set(a), list(a)
    while todo:
        for y in near.get(todo.pop(), ()):
            if y in b:
                return True
            if y in within and y not in seen:
                seen.add(y)
                todo.append(y)
    return False


def purpose(spec: Spec, say) -> None:
    if not [s for s in spec.systems if not (spec.uses.get(s) or {}).get("once")]:   # (a once template's system, as use:
        return                                                  # modelling's, is the template's: the model has none of its own)
    for s in sorted(spec.systems):
        if not spec.systems[s]:
            say("purpose", f"system {s}: says nothing of what it is for: a description, its purpose, is what its goals "
                f"are traced to", f"system.{s}")
        elif any(s in ch for p, ch in _chains(spec).items() if p.startswith("block.")) and \
                not any(s in ch for p, ch in _chains(spec).items() if p.startswith("goal.")):
            say("purpose", f"system {s}: is for \"{spec.systems[s]}\", and its blocks act for no goal inside it: its "
                f"purpose is not measured", f"system.{s}")
    if not spec.purpose:
        loose = sorted(g.name for g in spec.goals.values() if not any(spec.systems.get(x) for x in spec.chain(g.system)))
        if loose:
            names = ", ".join(loose[:6]) + (f" and {len(loose) - 6} more" if len(loose) > 6 else "")
            say("purpose", f"goal{'s' * (len(loose) > 1)} {names}: in no system that says what it is for, and the "
                f"model has no purpose: to trace {'them' if len(loose) > 1 else 'it'} to", "model")


def findings(spec: Spec, say) -> None:
    for f in (splits, merges, interfaces, time_scales, purpose):
        f(spec, lambda code, msg, about: say(code, msg, None, about))


def size(spec: Spec, system: str) -> dict:
    """A system's size: its parts (in it at any depth), the feedback loops inside it and through it, and how many
    levels of systems are within it."""
    from .causal import loops
    kept = spec.lookups().kept
    if ("architecture.size", system) not in kept:
        chains = _chains(spec)
        mine = {p for p, ch in chains.items() if system in ch}
        ins = [(sum(p in mine for p in lp.parts), sum(p in chains for p in lp.parts)) for lp in loops(spec)]

        def depth(s: str) -> int:
            return 1 + max((depth(k) for k in spec.subsystems(s)), default=0)
        kept[("architecture.size", system)] = {"parts": len(mine), "loops": sum(n == k for n, k in ins),
                                               "through": sum(0 < n < k for n, k in ins), "depth": depth(system) - 1}
    return dict(kept[("architecture.size", system)])


def size_said(z: dict) -> str:
    return (f"{z['parts']} parts, {z['loops']} feedback loop{'s' * (z['loops'] != 1)} inside"
            + (f" and {z['through']} through it" if z["through"] else "")
            + (f", {z['depth']} level{'s' * (z['depth'] != 1)} of systems within it" if z["depth"] else ""))
