"""A verdict, recorded (SPEC §12i): an ``ergostat.verdict`` item, given by the intent judge on one piece of work at one
moment it said it was done.

Its id is ``ergostat.verdict/<short hash>`` of the work and the event that moved it into its judged state, so the same
moment is judged once. Every step is an event about it: ``ergostat.verdict.asked`` (from the judge: the work, what it
is held to, how it is judged), then one verdict, ``.met``, ``.unmet``, ``.contradicted`` or ``.unjudged``, with the
evidence; later ``.overruled`` (the owner: the verdict was wrong, with a reason) or ``.missed`` (from ergostat: work
it passed that the owner reopened, followed up or corrected after accepting it). The verdict is also put on the work
item itself, as its field ``intent`` (``ergostat.item.judged``), beside what its tests said, so the work's own page and
its own programs (a rollout that keeps only what was judged done) read it. The record is the only store."""

from __future__ import annotations

import hashlib
import time

from ..spec.ir import VERDICT, Spec
from ..spec.items import REOPENED

JUDGED = "ergostat.item.judged"          # on the work item: the latest verdict, as its field ``intent``
VERDICTS = ("met", "unmet", "contradicted", "unjudged")
HELD = ("unmet", "contradicted")          # not done as meant: held back
OWNER = "owner"


class VerdictError(ValueError):
    pass


def item_of(vid: str) -> str:
    return vid if vid.startswith(VERDICT + "/") else f"{VERDICT}/{vid}"


def vid_of(work: str, entry_event: str) -> str:
    return item_of(hashlib.sha1(f"{work}\n{entry_event}".encode()).hexdigest()[:10])


def asked(p, block: str, brief: dict, mode: str, model: str | None, rung: str, at: float | None = None) -> dict:
    """The judge takes a piece of work up: what it is, what it is held to."""
    w = brief["work"]
    data = {"work": w["id"], "kind": w["kind"], "at": w["at"], "entered": w["entered"], "entry_event": w["entry_event"],
            "judge": "intent", "block": block, "rung": rung, "mode": mode, **({"model": model} if model else {}),
            "against": [x["id"] for x in brief["against"]], "done_when": w.get("done_when"),
            "diff_chars": len(brief.get("diff") or ""), "outcome": "being judged"}
    vid = vid_of(w["id"], w["entry_event"])
    ev = p.events.add(f"{VERDICT}.asked", item=vid, source=block, causedby=w["entry_event"], data=data, at=at)
    return {**data, "id": vid, "asked_event": ev["id"]}


def given(p, v: dict, verdict: str, why: str, evidence: list[dict], spent: dict | None = None,
          seconds: float | None = None) -> dict:
    """The verdict, with its evidence; and the same, in brief, on the work item."""
    assert verdict in VERDICTS
    data = {"verdict": verdict, "why": why, "evidence": evidence, "judged": time.time(),
            "outcome": {"met": "done as meant", "unmet": "not done as meant: held back",
                        "contradicted": "contradicts what the owner decided: held back",
                        "unjudged": "not judged: counts on its tests"}[verdict],
            **({"seconds": round(seconds, 3)} if seconds is not None else {}), **(spent or {})}
    ev = p.events.add(f"{VERDICT}.{verdict}", item=v["id"], source=v["block"], causedby=v.get("asked_event"), data=data)
    p.events.add(JUDGED, item=v["work"], source=v["block"], causedby=ev["id"],
                 data={"intent": {"verdict": verdict, "why": why[:500], "id": v["id"], "by": v["block"],
                                  "against": [e.get("against") for e in evidence if e.get("against")][:10],
                                  "judged": data["judged"]}})
    return {**v, **data, "state": verdict, "verdict_event": ev["id"]}


def stored(p, since: float | None = None, until: float | None = None) -> dict[str, dict]:
    """Every verdict asked since then, folded from its events (each field replaced), with its ``state``."""
    out: dict[str, dict] = {}
    for e in p.events.query(n=None, type=f"{VERDICT}.*", since=since, until=until):
        st = e["type"].rsplit(".", 1)[1]
        x = out.get(e["item"])
        if st == "asked":
            out[e["item"]] = {**e["data"], "id": e["item"], "state": "asked", "asked_event": e["id"], "time": e["time"]}
        elif x is not None:
            x.update(e["data"])
            x["state"] = st
            x.setdefault("moves", []).append({"to": st, "time": e["time"], "by": e.get("source")})
            if st in VERDICTS:
                x["verdict_event"], x["verdict_time"] = e["id"], e["time"]
    return out


def get(p, vid: str) -> dict | None:
    evs = p.events.query(n=None, item=item_of(vid))
    if not evs:
        hit = [e for e in p.events.query(n=5000, type=f"{VERDICT}.asked") if e["item"].split("/", 1)[1].startswith(vid)]
        if len(hit) != 1:
            return None
        evs = p.events.query(n=None, item=hit[0]["item"])
    first = evs[0]["time"]
    return stored(p, since=first - 1, until=evs[-1]["time"] + 1).get(evs[0]["item"])


# ---- the owner's acts

def overrule(p, vid: str, reason: str | None, by: str = OWNER) -> dict:
    """The owner says a verdict was wrong (a false alarm, or a pass that was not), with why. Recorded about the
    verdict and on the work item; the work itself is not moved: what follows is the owner's, or its own programs'."""
    v = get(p, vid)
    if v is None:
        raise VerdictError(f"no verdict {vid!r} (ergostat intent lists them)")
    if v["state"] not in VERDICTS and v["state"] != "missed":
        raise VerdictError(f"{v['id']} is {v['state']}: only a verdict given can be overruled")
    if not (reason or "").strip():
        raise VerdictError("overruling needs a reason: what the judge got wrong (it is what the judge is measured by)")
    data = {"overruled": {"was": v.get("verdict"), "reason": reason.strip()[:2000], "by": by, "at": time.time()},
            "outcome": f"overruled by {by}: {reason.strip()[:200]}"}
    ev = p.events.add(f"{VERDICT}.overruled", item=v["id"], source=by, causedby=v.get("verdict_event"), data=data)
    p.events.add(JUDGED, item=v["work"], source=by, causedby=ev["id"],
                 data={"intent": {"verdict": v.get("verdict"), "why": v.get("why", "")[:500], "id": v["id"],
                                  "by": v.get("block"), "overruled": reason.strip()[:500]}})
    return {**v, **data, "state": "overruled"}


def missed(p, v: dict, how: str, event: dict) -> dict:
    """Work the judge passed (met, or unjudged), accepted, then reopened, followed up or corrected by the owner."""
    data = {"missed": {"how": how, "event": event["id"], "at": event["time"], "by": event.get("source")},
            "outcome": f"missed: accepted, then {how} ({event.get('source') or 'the owner'})"}
    return p.events.add(f"{VERDICT}.missed", item=v["id"], source="ergostat", causedby=event["id"], data=data)


def reopen(p, spec: Spec, item: str, reason: str | None, by: str = OWNER, to: str | None = None,
           verdict: str | None = None) -> dict:
    """Move a piece of work back, with why (``ergostat.item.reopened``): the owner's act (work accepted that was not
    done as meant), or the judge's when its policy is ``held: reopen``. Returns the event."""
    from ..spec import items as its
    it = its.one(p.events, spec, item)
    if it is None or it.kind is None:
        raise VerdictError(f"no item {item!r} of a kind the model knows")
    k = spec.items[it.kind]
    if not k.states:
        raise VerdictError(f"{item}: its kind ({k.name}) has no states to go back through")
    if not (reason or "").strip():
        raise VerdictError("reopening needs a reason: what is not done as meant (the work is given it)")
    to = to if to in k.states else (spec.messages.reopen_to.get(k.name) or k.states[0])
    data = {"reopened": {"to": to, "from": it.state, "reason": reason.strip()[:2000], "says": reason.strip()[:500],
                         "by": by, "at": time.time(), **({"verdict": verdict} if verdict else {})}}
    return p.events.add(REOPENED, item=item, source=by, data=data)
