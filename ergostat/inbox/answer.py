"""The answer to an entry of the inbox (SPEC §12o), whatever its kind, through the path that kind has always had: a
gated action's ``gate.approve`` / ``deny``; a person's report (``agent.ran``, and what they moved); an advised
command's ``block.approved`` or ``block.denied``; a step test's or a loop's process or gain's ``accept`` / ``dismiss``
(``control.proposals``); a change to the model's ``accept`` / ``dismiss`` (``numbers.proposals``). Each is an event
from whoever answered, as before."""

from __future__ import annotations

import time

from . import entries as en


class AnswerError(ValueError):
    pass


def person_done(p, spec, b, n: float, note: str | None = None, ask: int | None = None) -> str:
    """A person block's report: they moved ``n`` along its flow (``ergostat block NAME --done N``)."""
    from ..spec.legacy import valve_name
    flows = [t.name for t in b.targets() if t.kind == "flow"]
    run = p.events.add("agent.ran", item=b.name, source="person", data={"done": n, "note": note or "", **({"ask": ask} if ask else {})})
    if flows and n > 0:
        p.events.add("valve.opened", item=valve_name(spec, b.name, flows[0]), source=b.name, causedby=run["id"],
                     data={"amount": float(n), "flow": flows[0], **({"note": note} if note else {})})
    return f"recorded: {b.name} moved {n:g}" + (f" along flow.{flows[0]}" if flows else "")


def answer(p, spec, eid: str, verb: str, n: float | None = None, note: str | None = None, by: str = "owner") -> dict:
    """``verb``: approve, deny or done (with ``n``). Returns the entry answered and what became of it."""
    from ..actions import gate
    from ..control import proposals as cp
    from ..numbers import proposals as pr
    e = en.find(p, spec, eid)
    if e is None:
        raise AnswerError(f"nothing waiting is {eid!r} (or it is the start of several): ergostat inbox lists them")
    if verb not in e["verbs"]:
        raise AnswerError(f"{e['id']} is answered with " + " or ".join(f"--{v}" + (" N" if v == "done" else "")
                                                                      for v in e["verbs"]))
    kind, key, yes = e["kind"], e["id"].split("/", 1)[1], verb == "approve"
    try:
        if kind == "action":
            said = (gate.approve(p, spec, key, by=by, note=note) if yes else gate.deny(p, key, by=by, note=note))["state"]
        elif kind == "person":
            if n is None:
                raise AnswerError("--done N: how much they moved")
            said = person_done(p, spec, spec.blocks[e["block"]], float(n), note, ask=e["seq"])
        elif kind == "advise":                            # exactly the ask shown: a newer one is another entry
            p.events.add("block.approved" if yes else "block.denied", item=e["block"], source=by,
                         data={"note": note or "", "ask": e["seq"]})
            said = "approved: it runs with its latest command" if yes else "denied: its command is not run"
        elif kind == "breaker":                          # a block started by events, reset (SPEC §9.3)
            p.events.add("trigger.reset", item=e["block"], source=by, data={"note": note or "", "tripped": e["seq"]})
            said = "reset: its events start it again"
        elif kind == "steptest" or e.get("control"):
            x = {k: v for k, v in en.offers(p)[key].items() if k != "time"} if kind == "steptest" else None
            said = (cp.accept(p, key, by=by, offer=x) if yes else cp.dismiss(p, key, note, offer=x, by=by))["status"]
        else:
            snap = {"at": time.time(), "window": 3600.0, "starts": p.events.first_time()}
            said = (pr.accept(p, key, snap, by=by) if yes else pr.dismiss(p, key, note, by=by))["status"]
    except (gate.GateError, cp.ProposalError, pr.ProposalError, KeyError) as x:
        raise AnswerError(str(x)) from None
    return {"id": e["id"], "kind": kind, "verb": verb, "said": said, "summary": e["summary"]}
