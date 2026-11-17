"""A recipe rendered (SPEC §12j): its parts in order, each within its budget, as one Markdown starting context, with
what it was rendered for and a hash of the text, so a session started from it can say exactly what it was given."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from . import parts as pt
from .fit import For


class RecipeError(ValueError):
    """No such recipe, or an item that is not there."""


@dataclass
class Rendered:
    recipe: str
    version: int
    digest: str                  # of the recipe's definition
    text: str
    item: str | None = None
    block: str | None = None
    run: str | None = None
    budget: int | None = None
    parts: list[dict] = field(default_factory=list)   # {part, budget, chars}
    at: float = field(default_factory=time.time)

    @property
    def hash(self) -> str:
        return hashlib.sha1(self.text.encode()).hexdigest()[:16]

    @property
    def tag(self) -> str:
        return f"{self.recipe}@{self.version}"

    def record(self) -> dict:
        """What a session started from it records: the recipe, its version and definition, and the text's hash."""
        return {"recipe": self.recipe, "version": self.version, "tag": self.tag, "definition": self.digest,
                "hash": self.hash, "chars": len(self.text), "item": self.item, "block": self.block, "run": self.run,
                "parts": self.parts}


def item_for(p, spec, sel, command_item: str | None = None, block: str | None = None, run: str | None = None):
    """The item a run works on: the one its command names, else the block's ``context.item``: an id (``{block}``
    and ``{run}`` filled in), or the oldest (newest) item of a kind in one of the states."""
    from ..spec import items as its
    if command_item:
        return its.one(p.events, spec, str(command_item))
    if sel is None:
        return None
    if isinstance(sel, str):
        iid = For(p, spec, None, block, run).fill(sel)
        return its.one(p.events, spec, iid) if iid else None
    states = sel.get("state")
    got = [i for i in its.project(p.events, spec, sel["kind"], transcript=False) if not states or i.state in states]
    if states:                                           # the earlier state first: one left building before a new one
        got.sort(key=lambda i: (states.index(i.state), i.first if sel.get("pick", "oldest") == "oldest" else -i.first))
    else:
        got.sort(key=lambda i: i.first if sel.get("pick", "oldest") == "oldest" else -i.first)
    return got[0] if got else None


def render(p, spec, name: str, item=None, block: str | None = None, run: str | None = None,
           budget: int | None = None, now: float | None = None) -> Rendered:
    """The recipe ``name``, for ``item`` (an id, an Item, or None), within ``budget`` (else the recipe's own): each
    part's budget scaled down to fit when the whole would not."""
    r = spec.contexts.get(name)
    if r is None:
        known = ", ".join(sorted(spec.contexts)) or "none: write them under contexts: in the YAML"
        raise RecipeError(f"no recipe {name!r} (the recipes: {known})")
    if isinstance(item, str):
        from ..spec import items as its
        got = its.one(p.events, spec, item)
        if got is None:
            raise RecipeError(f"no item {item!r} in the record")
        item = got
    ctx = For(p, spec, item, block, run, now or time.time())
    total = budget or r.budget
    scale = min(1.0, total / r.total()) if total and r.total() else 1.0
    head = f"# Starting context: {r.name} (version {r.version})\n\n" + \
        (f"{r.description}\n\n" if r.description else "") + \
        (f"The work is on {item.id}.\n\n" if item is not None else "")
    out, rows = [head], []
    for part in r.parts:
        b = max(200, int(part.budget * scale))
        text = pt.render(ctx, part.kind, part.params, b)
        out.append(text)
        rows.append({"part": part.label(), "budget": b, "chars": len(text)})
    return Rendered(r.name, r.version, r.digest, "\n".join(out), item.id if item is not None else None, block, run,
                    total, rows, ctx.now)
