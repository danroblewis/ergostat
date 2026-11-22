"""The Viable System Model's checklist for one system, computed from the structure alone (no run): for each of Beer's
functions, the parts the model shows that may fill it, each with a short reason. Evidence for the AI rung of the
architecture review (``numbers/vsm_review.py``), never a finding: a function with no candidates is an empty list,
and nothing here is said by ``check``.

- S1, operations: the goals directly in the system on a stock of its own, and its direct subsystems;
- S2, coordination: its blocks that share a taken kind's leases (SPEC §9.5) or a workspace pool with a block outside;
- S3, control: its subsystems' inner-loop goals it sets, and its goals whose setpoint another goal's block commands;
- S3*, audit: its judge blocks and its blocks with a ``claims`` param;
- S4, intelligence: its flows in from a cloud that are measured (the outside, seen), and the model's ``use:
  modelling`` loop (model-wide);
- S5, policy: its description, the model's purpose, and its subsystems' descriptions."""

from __future__ import annotations

from .ir import Ref, Spec

FUNCTIONS = ("S1", "S2", "S3", "S3*", "S4", "S5")


def parts(spec: Spec, system: str) -> set[str]:
    """What a review may cite as the system's own: its parts at any depth (an implied block's is its goal's; a once
    template's left out) and the systems within it."""
    from .architecture import _chains
    out = {p for p, ch in _chains(spec).items() if system in ch}
    return out | {f"system.{s}" for s in spec.systems if s != system and system in spec.chain(s)}


def _in(spec: Spec, kind: str, name: str, system: str) -> bool:
    return spec.inside(Ref(kind, name), system)


def checklist(spec: Spec, system: str) -> dict[str, list[dict]]:
    """``{function: [{"part", "why"}]}`` for the six functions, each list in a stable order."""
    out: dict[str, list[dict]] = {f: [] for f in FUNCTIONS}
    add = lambda f, part, why: out[f].append({"part": part, "why": why})   # noqa: E731
    goals = sorted((g for g in spec.goals.values() if _in(spec, "goal", g.name, system)), key=lambda g: g.name)
    blocks = sorted((b for b in spec.blocks.values() if not b.implied and _in(spec, "block", b.name, system)),
                    key=lambda b: b.name)
    outside = [b for b in spec.blocks.values() if not _in(spec, "block", b.name, system)]
    subs = spec.subsystems(system)
    for g in goals:
        if g.system == system and g.of.kind == "stock" and _in(spec, "stock", g.of.name, system):   # (a subsystem's: its own)
            add("S1", f"goal.{g.name}", f"holds stock.{g.of.name}, a stock of the system's own")
    for s in subs:
        add("S1", f"system.{s}", "a subsystem: an operation within it")
    for b in blocks:
        kind = b.takes.kind if b.takes else None
        shared = sorted(o.name for o in outside if kind and o.takes and o.takes.kind == kind)
        if shared:
            add("S2", f"block.{b.name}", f"takes {kind}, as {', '.join(shared[:3])} outside does: they share its leases")
            continue
        pool = b.params.get("workspace")
        users = sorted(o.name for o in outside if pool and o.params.get("workspace") == pool)
        if users:
            add("S2", f"block.{b.name}", f"uses the workspace pool {pool}, as {', '.join(users[:3])} outside does")
    for s in subs:
        for gname in spec.inner_loops(s):
            setters = [x for p in spec.interface(s) if p["dir"] == "in" and p["kind"] == "setpoint"
                       and p["part"] == f"goal.{gname}" for x in p["peers"]]
            if any(spec.inside(Ref.parse(x), system) for x in setters if Ref.parse(x)):
                add("S3", f"goal.{gname}", f"an inner loop of {s}, its setpoint set from this system")
    said = {x["part"] for x in out["S3"]}
    ctl = {h: set(spec.loop(h).controllers) for h in spec.goals} if goals else {}
    for g in goals:
        by = sorted(b.name for b in spec.blocks.values() if any((t.kind, t.name) == ("goal", g.name) for t in b.targets())
                    and any(h != g.name and (b.goal == h or b.name in c) for h, c in ctl.items()))
        if by and f"goal.{g.name}" not in said:
            add("S3", f"goal.{g.name}", f"its setpoint is commanded by {', '.join(by[:3])}, another goal's block")
    for b in blocks:
        if b.type == "judge":
            add("S3*", f"block.{b.name}", "a judge: it tests changes against the record")
        elif "claims" in b.params:
            add("S3*", f"block.{b.name}", "it checks claims (a claims param)")
    for f in sorted(spec.flows.values(), key=lambda f: f.name):
        if f.source is None and f.sensors and _in(spec, "flow", f.name, system):
            add("S4", f"flow.{f.name}", "arrives from outside the model, and is measured")
    if any((u or {}).get("template") == "modelling" for u in spec.uses.values()):
        add("S4", "use: modelling", "the model's modelling loop: model-wide, not this system's own")
    if spec.systems.get(system):
        add("S5", "description", f"the system says what it is for: {spec.systems[system]}")
    if spec.purpose:
        add("S5", "purpose", f"the model's purpose: {spec.purpose}")
    for s in subs:
        if spec.systems.get(s):
            add("S5", f"system.{s}", f"a subsystem's purpose: {spec.systems[s]}")
    return out
