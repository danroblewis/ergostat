"""A kind whose waiting cannot be explained (SPEC §5a, *What the model must say for why*; ``check``'s
``wait-unexplained``): a state its items rest in, unfinished, where ``ergostat why`` has nothing in the model to name
as what holds them, because the kind has no precedence relation they wait through, no block takes them from it, and
no one is named to move them on (the state is where they arrive, or no event of its kind moves them out of it).

Read from the model alone, so only of a kind whose finished states ``messages: done:`` declares (one whose finished
states are inferred from the record is finished as the record shows, which the model cannot say); a state no event of
its kind moves an item into is not one it rests in."""

from __future__ import annotations

from .finished import finish_of
from .ir import DEAD, LEASED, template_made


def unexplained(spec) -> list[tuple[object, list[str]]]:
    """(the kind, its states whose waiting cannot be explained), for each of the model's own kinds with any."""
    out = []
    for name, k in sorted((getattr(spec, "items", None) or {}).items()):
        if name.startswith("ergostat.") or k.sealed or template_made(k) or len(k.states) < 2:
            continue
        if any(r.precedence for r in k.relations.values()):
            continue
        fin = finish_of(spec, name, set())
        if fin["from"] != "declared":       # finished as the record shows it: not the model's to say here
            continue
        taken = {s for b in spec.blocks.values() if b.takes and b.takes.kind == name for s in b.takes.at}
        entered = set(k.on.values())
        bad = [s for i, s in enumerate(k.states)
               if s in entered and s not in taken and s not in fin["finished"] and s not in fin["paused"]
               and s not in (LEASED, DEAD) and (i == 0 or not any(t != s for t in k.on.values()))]
        if bad:
            out.append((k, bad))
    return out


def findings(spec, say) -> None:
    for k, bad in unexplained(spec):
        first = k.states[0] in bad
        said = ", ".join(bad)
        say("wait-unexplained", f"items {k.name}: an item waiting in {said} has nothing in the model that says why: no "
            f"block takes it from there, the kind has no relation it waits through, and no one is named to move it on ("
            + ("its first state is where items wait to be taken" if first else "no event of its kind moves it out")
            + "), so `ergostat why` cannot name who or what must act. Give the state a block that takes it, a "
            "relation its items wait through (precedence: true), or, for work done outside ergostat, let items arrive "
            "in a later state that the event recording that work moves on (docs/AGENT-GUIDE.md, section 3m)",
            k.where, f"items.{k.name}")
