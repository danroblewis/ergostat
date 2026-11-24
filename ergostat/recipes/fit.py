"""What every part shares: the run a recipe is rendered for (the project, the item, the block and its run), filling a
part's text from it (``{item}``, ``{item.title}``, ``{block}``, ``{run}``), and fitting text to a budget."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from ..decisions.kinds import STOP, words_of

PART_REF = re.compile(r"\b(stock|flow|auxiliary|goal|block|parameter)\.([a-z][a-z0-9-]*)\b")
HOLE = re.compile(r"\{(item|block|run)(?:\.([A-Za-z0-9_-]+))?\}")


@dataclass
class For:
    """What a recipe is rendered for."""
    p: object
    spec: object
    item: object = None                # the Item, folded, or None
    block: str | None = None
    run: str | None = None
    now: float = field(default_factory=time.time)

    @property
    def item_id(self) -> str | None:
        return self.item.id if self.item is not None else None

    def fill(self, text):
        """A part's text with the run's values in place of {item}, {item.FIELD}, {block} and {run} (empty when unknown)."""
        if not isinstance(text, str):
            return text

        def one(m):
            what, key = m.group(1), m.group(2)
            if what == "item":
                if self.item is None:
                    return ""
                if not key:
                    return self.item.id
                v = self.item.fields.get(key)
                return "" if v is None else (" ".join(map(str, v)) if isinstance(v, list) else str(v))
            return str({"block": self.block, "run": self.run}[what] or "")
        return HOLE.sub(one, text).strip()

    def parts_of_item(self) -> list[str]:
        """The parts of the model the item names (``stock.x``, ``flow.y``: in a ``parts`` field, its ``about``, any
        text field), and else every part of its kind's system: ``stock.x`` each."""
        if self.item is None:
            return []
        found: list[str] = []

        def walk(v):
            if isinstance(v, str):
                for m in PART_REF.finditer(v):
                    r = f"{m.group(1)}.{m.group(2)}"
                    if r not in found and known(self.spec, r):
                        found.append(r)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
            elif isinstance(v, dict):
                for x in v.values():
                    walk(x)
        from ..transcripts import FIELDS
        for k, v in self.item.fields.items():
            if k not in FIELDS:
                walk(v)
        if found:
            return found
        kind = self.spec.items.get(self.item.kind) if self.item.kind else None
        return system_parts(self.spec, kind.system) if kind and kind.system else []

    def terms(self) -> list[str]:
        """The item's own words, for relevance: its id's tail and its short text fields."""
        if self.item is None:
            return []
        from ..transcripts import FIELDS
        text = [self.item.id.split("/", 1)[-1].replace("-", " ")]
        for k, v in self.item.fields.items():
            if k not in FIELDS and isinstance(v, str) and len(v) < 400 and not v.startswith("file:"):
                text.append(v)
        return content_words(" ".join(text))


def content_words(text: str) -> list[str]:
    out: list[str] = []
    for w in words_of(text):
        if len(w) > 2 and w not in STOP and not w.isdigit() and w not in out:
            out.append(w)
    return out


def known(spec, ref: str) -> bool:
    kind, _, name = ref.partition(".")
    table = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries, "goal": spec.goals,
             "block": spec.blocks, "parameter": spec.parameters}.get(kind)
    return table is not None and name in table


def system_parts(spec, system: str) -> list[str]:
    out = []
    for kind, table in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries),
                        ("goal", spec.goals)):
        for name, x in table.items():
            if system in spec.chain(getattr(x, "system", None)):
                out.append(f"{kind}.{name}")
    return out


def cut(text: str, budget: int) -> str:
    """The text, or as much of it as fits, ended at a line, and said to be cut."""
    if len(text) <= budget:
        return text
    note = f"\n[... cut to {budget} characters]\n"
    keep = text[:max(0, budget - len(note))]
    if "\n" in keep[len(keep) // 2:]:
        keep = keep[:keep.rfind("\n")]
    from ..library.untrusted import END, close
    kept = close(keep)                         # a library's text cut short stays inside its mark (SPEC §2a)
    return (kept if len(kept) <= len(keep) else close(keep[:len(keep) - len(END)])) + note


def demote(md: str) -> str:
    """Headings one level down (a part's # title becomes ##), so parts sit under one context."""
    return re.sub(r"(?m)^(#{1,5}) ", lambda m: "#" + m.group(1) + " ", md)


def when(t: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else ""
