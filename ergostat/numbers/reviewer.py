"""The reviewer of changes to the model (SPEC §12e, *The reviewer*): an AI agent that reads a change the judge passed as a
senior modeller reads a colleague's, deliberately disagreeable, through the review checklists of MODELLING-WELL.md, before
it is written or reaches the owner. A change of a reviewed kind the judge passes waits in ``reviewing`` (``queue``). Its
verdict is ``pass``, ``revise`` or ``reject``, each with its findings, recorded on the change's item
(``ergostat.model-change.reviewed``), then the change moves:

- ``pass``: to ``passed``: the judge's policy may write it, and the inbox offers it to the owner;
- ``reject``: to ``rejected``, so the memory holds the same target back;
- ``revise``: to ``sent-back`` (its author named, saying so), whose next proposal on the same parts carries the findings
  (``revising``, ``review_asked``) and is the second round; a second revise is a reject. A change no author can revise
  (ergostat's finders, a program) goes to ``passed``, the findings beside it, for the owner; as one it could not decide.

The judge's ``reviewed:`` names the kinds that wait for it (the template sets it with ``ai: true``). Each call's cost is
recorded (``ergostat.model.review-ran``) and counted against the template's daily cap with the redesigner's."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from ..spec.ir import MODEL_CHANGE, Spec
from . import proposals as pr
from .modeller_spend import Capped

GUIDE = Path(__file__).resolve().parent.parent / "library" / "templates" / "modelling" / "reviewer.md"
VERDICTS = ("pass", "revise", "reject")
RAN = "ergostat.model.review-ran"        # each call, with its cost
MEMORY = 5                               # the reviewer's recent verdicts an author is shown
DAY = 86400.0
TRIES = 3                                # calls on one change with no usable verdict before it goes to the owner
RESERVE = 0.25                           # the share of the template's daily cap kept for the reviewer
UNDECIDED = "undecided"                  # what is recorded when it could not decide: the owner's


def kinds(spec: Spec) -> list[str]:
    return list(getattr(spec.improve, "reviewed", None) or [])


def seen(x: dict) -> str:
    """What the reviewer read, stamped: the judge's verdict and the edit as they stand. A change made again, revised, or
    carried and judged since has another stamp."""
    v = x.get("verdict") or {}
    v = v.get("judged", v)                  # its own reject (``failed``) keeps the judge's verdict it read
    got = {"verdict": v or None, "edit": x.get("edit"), "redesign": x.get("redesign"), "version": x.get("version")}
    return hashlib.sha256(json.dumps(got, sort_keys=True, default=str).encode()).hexdigest()[:16]


def review_of(x: dict) -> dict | None:
    """Its review, if it is of the change as the judge last passed it (the stamp of what it read is the change's now):
    any other is stale, as if never read."""
    r = x.get("review") or None
    return r if r and r.get("read") == seen(x) else None


def awaiting(spec: Spec, x: dict) -> bool:
    """A change of a reviewed kind the reviewer has not passed: the judge's policy does not write it."""
    return x.get("kind") in kinds(spec) and (review_of(x) or {}).get("verdict") != "pass"


def unread(spec: Spec, x: dict) -> bool:
    """A change of a reviewed kind the reviewer has not read yet: the inbox does not offer it. One it read (sent back
    with no author to take it, or it could not decide) is the owner's, its findings beside it."""
    return x.get("kind") in kinds(spec) and review_of(x) is None


def read_for_owner(spec: Spec, x: dict) -> bool:
    """Read, and left to the owner (sent back with no author to take it, or undecided): the judge never writes it."""
    return x.get("kind") in kinds(spec) and (review_of(x) or {}).get("verdict") in ("revise", UNDECIDED)


def due(p, spec: Spec) -> list[dict]:
    """The changes the judge passed that wait for a review, oldest first."""
    return [x for x in pr.pending(p, spec) if x["state"] in pr.JUDGED and unread(spec, x)]


def queue(p, spec: Spec, x: dict, kept: bool = False) -> bool:
    """A change the judge just passed, of a reviewed kind and with no review of it as it stands (``kept``: its review
    carried by a rescore), moved on to ``reviewing``: under review, not yet passed for the owner or the judge's policy.
    Whether it was moved."""
    if kept or x.get("kind") not in kinds(spec):
        return False
    pr.event(p, x["id"], "reviewing", {})
    return True


def tries(p, x: dict, failed: bool = False) -> int:
    """Calls on this change as it stands (each stamped with what it read): none made on an earlier version count. Those
    that failed (``modeller.call``'s ``error``) are no try; ``failed`` counts them instead."""
    return sum(1 for e in p.events.query(n=None, type=RAN) if (d := e.get("data") or {}).get("change") == x["id"]
               and d.get("read") == seen(x) and bool(d.get("error")) == failed)


def author(spec: Spec, x: dict) -> str | None:
    """Who a revise goes back to: the block that made it, unless it is ergostat, the owner or a program (no findings reach
    them)."""
    by = x.get("made_by")
    b = spec.blocks.get(by or "")
    return None if by in (None, "ergostat", "owner") or (b is not None and b.type not in ("ai", "person")) else by


DYNAMICS, PROJECTIONS = "<!-- dynamics", "<!-- projections"
WELL_PROJECTIONS = "**Reviewing a change to the projections**"


def projections_only(p, spec: Spec, x: dict) -> list[str]:
    """The projections a change adds or alters, when that is all it changes (no stock, flow, link, parameter, goal,
    block or sensor): reviewed by the projection checklist, not the stocks-and-flows one. Empty otherwise."""
    from . import trial as tr
    from . import unexplained as ux
    from . import version as ver
    if x.get("redesign"):
        return []
    if x.get("explains") and x.get("projections_changed"):      # the drafter's (unexplained.proposal_of): only those
        return list(x["projections_changed"])
    try:
        after = tr.spec_after(p, tr.edits_of(x))
    except Exception:
        return []
    names = ux.changed_projections(spec, after)
    if not names or ver.version(spec) != ver.version(after) or ver.control(spec) != ver.control(after) \
            or ver.changed_sensors(spec, after):
        return []
    return names


def guide(projections: bool) -> str:
    """reviewer.md's head, and the part for the change's kind: a change to the projections alone, or any other."""
    text = GUIDE.read_text(encoding="utf-8")
    a, b = text.find(DYNAMICS), text.find(PROJECTIONS)
    if a < 0 or b < 0:
        return text
    head = text[:a].rstrip()
    part = text[b:] if projections else text[a:b]
    return head + "\n\n" + part.split("\n", 1)[1].strip()


def checklists(projections: bool) -> str:
    """MODELLING-WELL's review checklists: for a change to the projections alone, its projection checklist; for any
    other, the rest of them."""
    from .. import helpdocs
    from . import redesigner as rdr
    well = rdr._sections(helpdocs.read("modelling-well") or "", ("5. Review checklists",))
    at = well.find(WELL_PROJECTIONS)
    if at < 0:
        return "" if projections else well
    end = well.find("\n**", at + len(WELL_PROJECTIONS))
    end = len(well) if end < 0 else end
    return well[at:end].strip() if projections else (well[:at] + well[end:]).strip()


def evidence(x: dict, names: list[str]) -> list[str]:
    """The judge's review of each projection the change adds or alters (its numbers, its fields' coverage, its states,
    its mechanical findings), as prompt lines."""
    ev = (x.get("verdict") or {}).get("evidence") or {}
    out = []
    if ev.get("targeted"):
        out.append("targeted: " + json.dumps(ev["targeted"]))
    for n in names:
        got = (ev.get("projections") or {}).get(n) or {}
        if got.get("after"):
            out += [f"### {n}", "", "```json", json.dumps(got["after"], ensure_ascii=False, default=str)[:6000], "```"]
            if got.get("before"):
                out.append("before the change: " + json.dumps({k: v for k, v in got["before"].items()
                                                                if not isinstance(v, (dict, list))}))
    if ev.get("findings"):
        out += ["", "The judge's findings (mechanical, from the numbers above):", ""]
        out += [f"- {g.get('projection')}: {g.get('level')} {g.get('check')}: {g.get('says')}" for g in ev["findings"]]
    return out or ["(the judge's review of it is not recorded)"]


def prompt(p, spec: Spec, x: dict) -> str:
    from . import modeller as md
    names = projections_only(p, spec, x)
    change = {k: x.get(k) for k in ("title", "kind", "made_by", "parts", "reasons", "confidence", "summary", "system",
                                    "predicted", "findings") if x.get(k)}
    change["judged"] = (x.get("verdict") or {}).get("why")
    if x.get("redesign"):
        change["edits"] = [{"edit": e.get("said") or e.get("edit"), "why": e.get("why")} for e in x["redesign"].get("edits") or []]
    lines = [guide(bool(names)), "", checklists(bool(names)), "", "## The change", "",
             json.dumps(change, ensure_ascii=False, default=str),
             "", "## Its diff", "", "```diff", str((x.get("edit") or {}).get("diff") or "")[:8000], "```", ""]
    if names:
        lines += ["## Its review (the judge's, over the record)", "", *evidence(x, names), ""]
        for n in names:
            if body := (x.get("drafted") or {}).get(n):
                lines += [f"## The projection {n} as drafted", "", "```yaml", str(body)[:8000], "```", ""]
    lines += ["## The model near it", ""]
    for ref in md.neighbourhood(spec, list(x.get("parts") or []))[:25]:
        if t := md._text_of(spec, ref):
            lines += ["```yaml", t, "```"]
    if x.get("review_asked"):
        lines += ["", "## Round 2: you sent its first version back with these findings; a second revise is a reject", ""]
        lines += [f"- {f.get('check')}: {f.get('says')}" for f in x["review_asked"]]
    return "\n".join(lines)


def parse(text: str) -> dict | None:
    """The verdict line: ``{"verdict", "findings": [{"check", "says"}], "summary"}``; None when there is none, or a revise or
    reject without a specific finding."""
    for line in str(text or "").splitlines():
        line = line.strip().strip("`").strip()
        try:
            got = json.loads(line).get("review") if line.startswith("{") else None
        except (ValueError, AttributeError):
            continue
        if not isinstance(got, dict) or got.get("verdict") not in VERDICTS:
            continue
        fs = [{"check": str(f.get("check") or "")[:40], "says": str(f["says"])[:400]}
              for f in got.get("findings") or [] if isinstance(f, dict) and str(f.get("says") or "").strip()]
        if got["verdict"] != "pass" and not fs:
            return None
        return {"verdict": got["verdict"], "findings": fs[:8], "summary": str(got.get("summary") or "")[:400]}
    return None


STALE = "stale"                          # what record returns when the change moved on while it was read: nothing recorded


def record(p, spec: Spec, x: dict, got: dict, by: str = "reviewer", cost: float = 0.0, now: float | None = None) -> str:
    """The verdict on its item, and where it sends the change, under the changes' lock and only if the change is still
    the one it read (else ``stale``, nothing recorded: it is read again). Returns the verdict as recorded."""
    with pr.locked(p):
        st, now_x = pr.changes(p).get(x["id"], (None, {}))
        if st not in pr.JUDGED or seen(now_x) != seen(x):
            return STALE
        return _record(p, spec, x, got, by, cost, now, st)


def _record(p, spec: Spec, x: dict, got: dict, by: str, cost: float, now: float | None, st: str = "reviewing") -> str:
    now = now or time.time()
    verdict, rounds, who = got["verdict"], int(x.get("review_round") or 1), author(spec, x)
    if verdict == UNDECIDED:                    # it could not decide: the owner's, said so
        pr.event(p, x["id"], "reviewed", {"review": {"verdict": verdict, "findings": [], "summary": got["summary"], "by": by,
                                                     "at": now, "round": rounds, "author": who, "read": seen(x)}}, source=by)
        if st != "passed":
            pr.event(p, x["id"], "passed", {}, source=by)
        return verdict
    said = "; ".join(f["says"] for f in got["findings"][:3]) or got["summary"]
    if verdict == "revise" and rounds >= 2:
        verdict, said = "reject", f"sent back once already and still: {said}"
    review = {"verdict": verdict, "findings": got["findings"], "summary": got["summary"], "by": by, "at": now,
              "round": rounds, "author": who, "cost_usd": round(cost, 6), "read": seen(x)}
    pr.event(p, x["id"], "reviewed", {"review": review}, source=by)
    if verdict == "reject":
        pr.event(p, x["id"], "rejected", {"verdict": {"verdict": "rejected", "why": f"the reviewer rejected it: {said}",
                                                      "at": now, "by": by, "judged": x.get("verdict")}}, source=by)
    elif verdict == "revise" and who is not None:
        pr.event(p, x["id"], "sent-back", {"why": f"sent back to {who} by the reviewer: {said}", "sent_to": who}, source=by)
        if x.get("kind") == "redesign":           # the redesigner takes it up again, the findings in its prompt
            from . import redesign as rd
            rd.ask(p, x.get("system"), by=by, why=f"the reviewer sent {x['id']} back")
    elif st != "passed":                          # passed; or sent back with no author to take it: the owner's
        pr.event(p, x["id"], "passed", {}, source=by)
    return verdict


def asked(p, by: str, parts, system: str | None = None, explains=None) -> dict:
    """What a new proposal by ``by`` on these parts (a redesign: of this system; a drafted projection: for these event
    requests, ``explains``) carries, when the reviewer sent back one of its own on them that no later proposal has
    answered: ``{"revising", "review_round", "review_asked"}``, else nothing."""
    now = time.time()
    sent = sorted(((pid, f) for pid, (st, f) in pr.changes(p).items()
                   if (f.get("review") or {}).get("verdict") == "revise" and f.get("made_by") == by
                   and now - float(f["review"].get("at") or 0) <= DAY
                   and (set(f.get("parts") or []) & set(parts or []) or (system and f.get("system") == system)
                        or set(f.get("explains") or []) & set(explains or []))),
                  key=lambda kv: -float(kv[1]["review"].get("at") or 0))
    if not sent:                                # every revise on these parts counts, whatever became of the next round
        return {}
    pid, f = sent[0]
    out = {"revising": pid, "review_round": len(sent) + 1, "review_asked": f["review"].get("findings") or []}
    if len(sent) >= 2:
        out["review_held"] = f"held back: the reviewer sent back {len(sent)} changes by {by} on these parts in the last day"
    return out


def memory(p, by: str, most: int = MEMORY) -> list[dict]:
    """The reviewer's latest verdicts on this author's own changes, newest first: what it said, so it stops repeating
    what was rejected."""
    mine = [(f, r) for _, f in pr.changes(p).values() if f.get("made_by") == by and (r := review_of(f))]
    mine.sort(key=lambda fr: -float(fr[1].get("at") or 0))   # only a review of the version as it stands
    return [{"title": f.get("title"), "parts": f.get("parts") or [], "verdict": r["verdict"],
             "findings": [g["says"] for g in r.get("findings") or []][:3]} for f, r in mine[:most]]


def lines(p, by: str) -> list[str]:
    """The memory as a prompt section (none when the reviewer has said nothing of this author's changes)."""
    got = memory(p, by)
    if not got:
        return []
    return ["", "## The reviewer on your recent proposals (do not propose again what it rejected; answer what it asked)", ""] + \
        [f"- {m['verdict']}: {m['title']} ({', '.join(m['parts'])})" + (f": {'; '.join(m['findings'])}" if m["findings"] else "")
         for m in got]


def spent(p, now: float | None = None) -> float:
    now = now or time.time()
    return round(sum(float((e.get("data") or {}).get("usd") or 0.0) for e in p.events.query(n=None, type=RAN, since=now - DAY)), 6)


def run(p, model: str = "haiku", most: int = 3, left: float = 1.0, timeout: float = 600.0, call=None, on_call=None,
        room=None) -> dict:
    """One pass: each change waiting for a review, while the day's allowance ``left`` lasts (no call starts whose estimated
    most, ``modeller.unsaid``, is more than is left). ``room()``, if given, is what is left of the day's cap, read again
    before each call and held against it while the call runs (``redesign.held``). Returns ``{"verdicts", "cost"}``."""
    from . import modeller as md
    from . import redesign as rd
    call = call or md.call
    spec: Spec = p.model.spec
    out = {"verdicts": [], "cost": {"usd": 0.0, "calls": 0}}
    for x in sorted(due(p, spec), key=lambda x: tries(p, x, failed=True))[:most]:     # one that keeps failing: behind
        text = prompt(p, spec, x)
        dearest = md.unsaid(text, model)["usd"]
        with rd.held(p, dearest, room, by="reviewer") as fits:
            if not fits or out["cost"]["usd"] + dearest > left:     # its estimated most: none past the cap
                out["verdicts"].append({"id": x["id"], "verdict": None, "why": "the day's allowance is spent"})
                break
            try:
                got = md.asked(p, text, model, timeout, call)
            except Capped as e:                         # the day's budget said no: no process, no more this run
                out["verdicts"].append({"id": x["id"], "verdict": None, "why": str(e)})
                break
            usd = float(got.get("usd") or 0.0)
            out["cost"]["usd"] = round(out["cost"]["usd"] + usd, 6)
            out["cost"]["calls"] += 1
            p.events.add(RAN, source="reviewer", data={"change": x["id"], "usd": usd, "model": model, "read": seen(x),
                                                            **({"error": got["error"]} if got.get("error") else {})})
        if on_call is not None:
            on_call(got)
        err = got.get("error")
        v = None if err else parse(got.get("result") or "")
        if v is None and tries(p, x, failed=bool(err)) >= (md.FAILS if err else TRIES):   # it cannot decide: the owner's
            v = {"verdict": UNDECIDED, "findings": [], "summary": f"the reviewer could not decide in "
                 f"{f'{md.FAILS} failed calls' if err else f'{TRIES} tries'} ({err or 'no verdict with its reasons'})"}
        if v is None:                       # no verdict with specific reasons: nothing recorded; it is read again next pass
            out["verdicts"].append({"id": x["id"], "verdict": None, "why": err or "no verdict with its reasons"})
            if err:                             # a failed call: no more this run (as the modeller's)
                break
            continue
        out["verdicts"].append({"id": x["id"], "verdict": record(p, spec, x, v, cost=usd)})
    return out


def counts(p, since: float, until: float) -> dict[str, int]:
    """The reviewer's verdicts in a span, and its misses: changes it passed that the prediction check later flagged for
    revert (regressed)."""
    out = dict.fromkeys(VERDICTS, 0) | {"missed": 0}
    for e in p.events.query(n=None, type=f"{MODEL_CHANGE}.reviewed", since=since, until=until):
        v = ((e.get("data") or {}).get("review") or {}).get("verdict")
        if v in out:
            out[v] += 1
    out["missed"] = sum(1 for st, f in pr.changes(p).values()
                        if st == "regressed" and (review_of(f) or {}).get("verdict") == "pass")   # a pass of the version written
    return out
