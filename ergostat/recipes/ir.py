"""What a context recipe is (SPEC §12j): a name, a version, and a list of parts, each with a budget, rendered in
order into one Markdown starting context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from ..spec.ir import CONTEXT  # noqa: F401  (the built-in projection: one use of a recipe, and its outcome)
from ..spec.load import Where

CONTEXT_STATES = ["started", "succeeded", "failed"]

# each kind of part, the keys it takes (besides budget), and what it gives
PARTS: dict[str, tuple[set[str], str]] = {
    "decisions": ({"scope", "proposed"}, "the owner's confirmed decisions, most relevant to scope first"),
    "corrections": ({"kind", "proposed"}, "what the owner corrected before, for this kind of work"),
    "owner-words": ({"topic", "item", "from", "rest"},
                    "the owner's messages, verbatim, most relevant to the topic, the item or its parts first"),
    "item-history": ({"events", "sessions", "turns"},
                     "the item's fields and history, and the key turns of the sessions that worked on it"),
    "state": ({"repo", "branch", "since", "commits", "running", "findings"},
              "what moved on the main branch, what is running, and the open findings on the item's parts"),
    "session": ({"of", "last", "match"}, "a session's turns: all of it, the last N, or those matching a pattern"),
    "docs": ({"files"}, "named files, whole, in order"),
    "model": ({"parts", "goals"}, "the item's parts in the model, and their goals"),
}
DEFAULT_BUDGET = {"decisions": 8000, "corrections": 6000, "owner-words": 8000, "item-history": 6000, "state": 3000,
                  "session": 12000, "docs": 12000, "model": 3000}
RESERVED = ("decisions", "corrections")   # ergostat context decisions | corrections: the one-part built-ins


@dataclass
class Part:
    kind: str
    budget: int
    params: dict = field(default_factory=dict)
    where: Where | None = None

    def label(self) -> str:
        bits = [f"{k}: {v}" for k, v in self.params.items() if not isinstance(v, (dict, list))]
        return self.kind + (f" ({', '.join(bits)})" if bits else "")


@dataclass
class Recipe:
    name: str
    version: int = 1
    parts: list[Part] = field(default_factory=list)
    description: str = ""
    budget: int | None = None                         # the whole context's most, when it says one
    outcome: dict = field(default_factory=dict)       # success: [states], failure: [states] of the item it works on
    where: Where | None = None

    @property
    def tag(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def digest(self) -> str:
        """A hash of what the recipe says: a change made without a new version is still told apart."""
        body = {"parts": [[p.kind, p.budget, p.params] for p in self.parts], "budget": self.budget,
                "outcome": self.outcome}
        return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:12]

    def total(self) -> int:
        return sum(p.budget for p in self.parts)
