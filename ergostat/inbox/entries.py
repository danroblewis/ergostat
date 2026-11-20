"""Everything waiting on a person now, in one list (SPEC §12o): gated actions held for the owner, a person block's
request not yet reported, an advised command not yet approved or denied, a step test offered and not decided, the
model changes awaiting the owner, and what check finds that modelling holds (no tier has a change for it). Each entry:
``id`` (``KIND/KEY``), ``kind``, ``summary``, ``time`` (asked) and ``age``, ``link`` (its item's or block's page),
``verbs`` (how it is answered), ``class`` (what it is counted with toward graduation) and ``why`` (an action about an
item: the item's impact sentence and tests, when it has them)."""

from __future__ import annotations

import time

from ..spec.ir import MODELLING_REQUEST

KINDS = ("action", "person", "advise", "steptest", "change", "request", "breaker")
_CACHE: dict = {}


MERGES = "Approving merges this code into your repository; it then runs with your rights, outside the sandbox."


def _cut(s: str, n: int = 80) -> str:
    return s if len(s) <= n else s[:n - 3] + "..."


def _why(p, spec, item: str | None) -> str:
    """The work item's impact sentence and its tests' result (the repair loop's failure, SPEC §12n), when it has them."""
    from ..spec import items as its
    try:
        it = its.one(p.events, spec, item) if item else None
    except Exception:
        return ""
    f = it.fields if it else {}
    imp = f.get("impact")
    imp = imp.get("said") if isinstance(imp, dict) else imp
    if str(item).startswith("ergostat.failure/"):              # the repair loop's fix (SPEC §12r): said plainly
        return (f"{MERGES} Diff: /item/{item}. The fixed program {(f.get('test') or {}).get('how') or 'was not tested'}. {imp or ''}")
    return "; ".join(x for x in (str(imp or ""), f"tests {f['tests']}" if f.get("tests") else "") if x)


def _actions(p, spec, now: float) -> list[dict]:
    from ..actions import record
    if not spec.actions:
        return []
    return [{"id": f"action/{record.short(a['id'])}", "kind": "action", "time": a["time"], "link": f"/item/{a['id']}",
             "verbs": ["approve", "deny"], "class": a.get("class") or a.get("action"), "action": a.get("action"),
             **({"warn": MERGES} if str(a.get("item")).startswith("ergostat.failure/") else {}),
             "summary": f"{a.get('action')}" + (f" for {a['item']}" if a.get("item") else "") + f": "
                        f"{_cut(a.get('command') or '', 70)}", "why": _why(p, spec, a.get("item"))}
            for a in record.stored(p, until=now).values() if a["state"] == "requested"]


def asks(p, b, since: float | None = None, until: float | None = None) -> list[dict]:
    """Each time a person block was asked (``person.asked``) or an advised block advised (``block.advised``): its
    ``seq``, time and data, and when and how it was answered (a person's report; an approval or a denial), by whom. An
    ask a newer one replaced before any answer is ``superseded``: one waits at a time, the newest."""
    person = b.type == "person"
    out: list[dict] = []
    for e in p.events.query(n=None, item=b.name, since=since, until=until,
                            type="person.asked,agent.ran" if person else "block.advised,block.approved,block.denied"):
        if e["type"] in ("person.asked", "block.advised"):
            if out and out[-1]["answered"] is None:
                out[-1].update(answered=e["time"], verdict="superseded", by=None)
            out.append({"seq": e["seq"], "time": e["time"], "data": e["data"], "answered": None, "verdict": None})
        elif out and out[-1]["answered"] is None:
            out[-1].update(answered=e["time"], by=e.get("source"),
                           verdict="denied" if e["type"] == "block.denied" else "approved")
    return out


def _blocks(p, spec, now: float) -> list[dict]:
    out = []
    for b in spec.blocks.values():
        if b.type != "person" and b.mode != "advise":
            continue
        last = asks(p, b, now - 30 * 86400.0, now)[-1:]
        if not last or last[0]["answered"] is not None:
            continue
        x, person, ask = last[0], b.type == "person", str(b.params.get("ask") or "")
        kind, cmd = ("person" if person else "advise"), f"command {x['data'].get('command') or 0:g}"
        if x["data"].get("event_type"):                   # started by an event: asked about it (SPEC §9.3)
            cmd = f"run on {x['data']['event_type']} {str(x['data'].get('event'))[:8]}"
        out.append({"id": f"{kind}/{b.name}@{x['seq']}", "kind": kind, "block": b.name, "seq": x["seq"],
                    "time": x["time"], "link": f"/diagram?view=blocks&around=block/{b.name}",
                    "verbs": ["done"] if person else ["approve", "deny"], "class": f"{kind}:{b.name}", "why": "",
                    "summary": f"{b.name} is asked: {_cut(ask) or cmd}" if person else f"{b.name} advises its {cmd}"})
    return out


def _breakers(p, spec, now: float) -> list[dict]:
    """Blocks started by events whose breaker tripped (SPEC §9.3), each waiting for the owner to reset it."""
    out = []
    for b in spec.blocks.values():
        last = p.events.query(n=1, item=b.name, type="trigger.tripped,trigger.reset") if b.on is not None else []
        if last and last[0]["type"] == "trigger.tripped":
            x = last[0]
            out.append({"id": f"breaker/{b.name}@{x['seq']}", "kind": "breaker", "block": b.name, "seq": x["seq"],
                        "time": x["time"], "link": f"/diagram?view=blocks&around=block/{b.name}", "verbs": ["approve"],
                        "class": f"breaker:{b.name}", "why": "",
                        "summary": f"{b.name}'s runs from events stopped: {x['data'].get('runs')} in a minute (the most "
                                   f"{x['data'].get('most')}); approve to reset its breaker"})
    return out


def offers(p, now: float | None = None) -> dict[str, dict]:
    """Step tests offered (``steptest.offered``), by id: the proposal as the loop's analysis made it."""
    return {e["data"]["id"]: {**e["data"], "time": e["time"]} for e in p.events.query(n=50, type="steptest.offered",
                                                                                         until=now) if e["data"].get("id")}


def _steptests(p, spec, now: float) -> list[dict]:
    from ..control import loop as lp
    from ..control import proposals as cp
    done, out = cp.decisions(p), []
    for pid, x in offers(p, now).items():
        try:
            if pid in done or x.get("goal") not in spec.goals or lp.key(spec, x["goal"]) != x.get("key"):
                continue
        except Exception:
            continue
        out.append({"id": f"steptest/{pid}", "kind": "steptest", "time": x["time"], "verbs": ["approve", "deny"],
                    "link": f"/diagram?around=loop/{x['goal']}", "class": "steptest", "summary": x.get("title") or pid,
                    "why": _cut(x.get("reason") or "", 200)})
    return out


def _changes(p, spec, now: float) -> list[dict]:
    from ..numbers import proposals as pr
    from ..numbers.review import control_pending
    judged = any(b.type == "judge" for b in spec.blocks.values())      # with a judge, what it passed waits for the owner
    from ..numbers import reviewer as rv
    xs = [x for x in pr.pending(p, spec) if (not judged or x.get("state") == "passed") and not rv.unread(spec, x)]
    return [{"id": f"change/{x['id']}", "kind": "change", "time": x.get("created") or now, "verbs": ["approve", "deny"],
             "link": f"/item/ergostat.model-change/{x['id']}", "class": f"change:{x.get('kind')}",
             "summary": f"model change: {_cut(x.get('title') or x['id'])}", "why": _cut(x.get("reason") or "", 200),
             **({"control": True} if x.get("kind") in ("process", "tuning") else {})}
            for x in xs + control_pending(p, spec)]


def _requests(p, spec, now: float) -> list[dict]:
    """What check finds that modelling holds (``ergostat.modelling-request``, held: no tier has a change for it): read
    on its item's page; answered when check no longer finds it, so it has no verb here."""
    from ..numbers import requests as rq
    if MODELLING_REQUEST not in spec.items:
        return []
    return [{"id": f"request/{r['id']}", "kind": "request", "time": r.get("raised") or now, "verbs": [],
             "link": f"/item/{MODELLING_REQUEST}/{r['id']}", "class": f"request:{r.get('code')}",
             "summary": f"modelling holds {r.get('code')} on {r.get('about')}", "why": _cut(r.get("why") or "", 200)}
            for r in rq.stored(p).values() if r["state"] == "held"]


def entries(p, spec=None, now: float | None = None) -> list[dict]:
    """Everything waiting on a person, oldest first, each with its age. Worked out again when the record changes."""
    spec = spec if spec is not None else getattr(p.model, "spec", None)
    if spec is None:
        return []
    live = now is None
    now = time.time() if live else now
    key = (str(p.dir), id(spec), p.events.last_seq(), None if live else now)
    got = _CACHE.get(key)
    if got is None:
        got = []
        for part in (_actions, _blocks, _steptests, _changes, _requests, _breakers):
            try:
                got += part(p, spec, now)
            except Exception:                               # one kind that cannot be read leaves the others
                continue
        got.sort(key=lambda e: e["time"])
        _CACHE.clear()
        _CACHE[key] = got
    return [{**e, "age": max(0.0, now - e["time"])} for e in got]


def find(p, spec, eid: str) -> dict | None:
    """An entry by its id, or a unique start of its key (``1a2b`` for ``action/1a2b3c...``)."""
    eid = eid.replace("ergostat.action/", "action/").replace("ergostat.model-change/", "change/")
    kind, key = (eid.split("/", 1) if "/" in eid and eid.split("/", 1)[0] in KINDS else ("", eid))
    es = entries(p, spec)
    hit = [e for e in es if e["id"] == eid] or [e for e in es if (not kind or e["kind"] == kind)
                                                 and e["id"].split("/", 1)[1].startswith(key)]
    return hit[0] if len(hit) == 1 else None
