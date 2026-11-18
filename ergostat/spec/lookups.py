"""The compiled model's reverse relations (``ir.Spec``'s lookups), worked out once per model instead of by
scanning every block on every question: who reads a part, who commands a block, which flows a stock has, which
block moves a flow, which parts drive which. A model is not changed once compiled (a change to the YAML is a new
model), so these hold for its life; ``Spec.reindex()`` drops them for code that does change one in place, and a
part added or removed is noticed by itself (the tables' sizes are the stamp). Every answer is the one the scan
gave, in the same order (docs/proposals/scale.md, #6)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ir import Block, Flow, Spec


def stamp(spec: Spec) -> tuple:
    """What the lookups were worked out from: the tables themselves and their sizes."""
    return tuple((id(t), len(t)) for t in (spec.blocks, spec.goals, spec.flows, spec.stocks, spec.auxiliaries))


class Lookups:
    def __init__(self, spec: Spec):
        self.stamp = stamp(spec)
        blocks = spec.blocks
        self.order = {n: i for i, n in enumerate(blocks)}       # a block's place: answers keep the model's order
        self.read_by: dict[tuple[str, str], set[str]] = {}       # (kind, name) a block reads → the blocks reading it
        self.reads_block: dict[str, set[str]] = {}               # a block → the blocks it reads (inputs: block.x)
        self.read_from: dict[str, set[str]] = {}                 # a block → the blocks reading it (inputs: block.x)
        self.sends_to: dict[str, set[str]] = {}                  # a block → the blocks it outputs to
        self.sent_from: dict[str, set[str]] = {}                 # a block → the blocks outputting to it
        self.first_target: dict = {}                             # an output Ref → the first block with it
        self.by_agent: dict[str, list[Block]] = {}
        for b in blocks.values():
            for r in b.reads():
                self.read_by.setdefault((r.kind, r.name), set()).add(b.name)
            for r in b.inputs.values():
                if r.kind == "block":
                    self.reads_block.setdefault(b.name, set()).add(r.name)
                    self.read_from.setdefault(r.name, set()).add(b.name)
            for t in b.targets():
                self.first_target.setdefault(t, b)
                if t.kind == "block":
                    self.sends_to.setdefault(b.name, set()).add(t.name)
                    self.sent_from.setdefault(t.name, set()).add(b.name)
            self.by_agent.setdefault(b.agent, []).append(b)   # type: ignore[arg-type]
        self.goals_on: dict[tuple, set[str]] = {}                # a goal's Ref (kind, name, port) → the goals on it
        for g, x in spec.goals.items():
            self.goals_on.setdefault((x.of.kind, x.of.name, x.of.port), set()).add(g)
        self.flows_at: dict[str | None, list[Flow]] = {}                # a stock → its flows, in the model's order
        for f in spec.flows.values():
            for s in dict.fromkeys((f.source, f.target)):            # (None: a flow's open end, as the scan had it)
                self.flows_at.setdefault(s, []).append(f)
        self.drives: dict[str, list[str]] = {}                   # a part → the flows and auxiliaries it drives
        for kind, table in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
            for f in table.values():
                for r in f.driven_by:
                    self.drives.setdefault(f"{r.kind}.{r.name}", []).append(f"{kind}.{f.name}")
        self.loops: dict = {}                                    # goal → its Loop (Spec.loop), as first worked out
        self.kept: dict = {}                                     # other answers worked out from the whole model

    def ordered(self, spec: Spec, names) -> list[Block]:
        return [spec.blocks[n] for n in sorted(names, key=self.order.__getitem__)]
