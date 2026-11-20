"""The reviewer of changes to the model (SPEC §12e, *The reviewer*): an AI agent that reads a change the judge passed as a
senior modeller reads a colleague's, deliberately disagreeable, through the review checklists of MODELLING-WELL.md, before
it is written or reaches the owner. Its verdict is ``pass``, ``revise`` or ``reject``, each with its findings, recorded on
the change's item (``ergostat.model-change.reviewed``, no move of state):

- ``pass``: the judge's policy may write it, and the inbox offers it to the owner;
- ``reject``: it fails (``failed``, from the reviewer), so the memory holds the same target back;
- ``revise``: back to its author (``superseded``, saying so), whose next proposal on the same parts carries the findings
  (``revising``, ``review_asked``) and is the second round; a second revise is a reject. A change no author can revise
  (ergostat's finders, a program) stays passed, the findings beside it, for the owner.

The judge's ``reviewed:`` names the kinds that wait for it (the template sets it with ``ai: true``). Each call's cost is
recorded (``ergostat.model.review-ran``) and counted against the template's daily cap with the redesigner's."""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..spec.ir import MODEL_CHANGE, Spec
from . import proposals as pr

GUIDE = Path(__file__).resolve().parent.parent / "library" / "templates" / "modelling" / "reviewer.md"
VERDICTS = ("pass", "revise", "reject")
RAN = "ergostat.model.review-ran"        # each call, with its cost
MEMORY = 5                               # the reviewer's recent verdicts an author is shown
DAY = 86400.0


def kinds(spec: Spec) -> list[str]:
    return list(getattr(spec.improve, "reviewed", None) or [])


def awaiting(spec: Spec, x: dict) -> bool:
    """A change of a reviewed kind the reviewer has not passed: the judge does not write it, the inbox does not offer it."""
    return x.get("kind") in kinds(spec) and (x.get("review") or {}).get("verdict") != "pass"


def due(p, spec: Spec) -> list[dict]:
    """The changes the judge passed that wait for a review, oldest first."""
    return [x for x in pr.pending(p, spec) if x["state"] == "passed" and x.get("kind") in kinds(spec) and not x.get("review")]


def author(spec: Spec, x: dict) -> str | None:
    """Who a revise goes back to: the block that made it, unless it is ergostat, the owner or a program (no findings reach
    them)."""
    by = x.get("made_by")
    b = spec.blocks.get(by or "")
    return None if by in (None, "ergostat", "owner") or (b is not None and b.type not in ("ai", "person")) else by


def prompt(p, spec: Spec, x: dict) -> str:
    from .. import helpdocs
    from . import modeller as md
    from . import redesigner as rdr
    well = rdr._sections(helpdocs.read("modelling-well") or "", ("5. Review checklists",))
    change = {k: x.get(k) for k in ("title", "kind", "made_by", "parts", "reasons", "confidence", "summary", "system",
                                    "predicted", "findings") if x.get(k)}
    change["judged"] = (x.get("verdict") or {}).get("why")
    if x.get("redesign"):
        change["edits"] = [{"edit": e.get("said") or e.get("edit"), "why": e.get("why")} for e in x["redesign"].get("edits") or []]
    lines = [GUIDE.read_text(encoding="utf-8"), "", well, "", "## The change", "", json.dumps(change, ensure_ascii=False, default=str),
             "", "## Its diff", "", "```diff", str((x.get("edit") or {}).get("diff") or "")[:8000], "```", "", "## The model near it", ""]
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


def record(p, spec: Spec, x: dict, got: dict, by: str = "reviewer", cost: float = 0.0, now: float | None = None) -> str:
    """The verdict on its item, and where it sends the change. Returns the verdict as recorded."""
    now = now or time.time()
    verdict, rounds, who = got["verdict"], int(x.get("review_round") or 1), author(spec, x)
    said = "; ".join(f["says"] for f in got["findings"][:3]) or got["summary"]
    if verdict == "revise" and rounds >= 2:
        verdict, said = "reject", f"sent back once already and still: {said}"
    review = {"verdict": verdict, "findings": got["findings"], "summary": got["summary"], "by": by, "at": now,
              "round": rounds, "author": who, "cost_usd": round(cost, 6)}
    pr.event(p, x["id"], "reviewed", {"review": review}, source=by)
    if verdict == "reject":
        pr.event(p, x["id"], "failed", {"verdict": {"verdict": "failed", "why": f"the reviewer rejected it: {said}", "at": now,
                                                    "by": by}}, source=by)
    elif verdict == "revise" and who is not None:
        pr.event(p, x["id"], "superseded", {"why": f"sent back to {who} by the reviewer: {said}"}, source=by)
        if x.get("kind") == "redesign":           # the redesigner takes it up again, the findings in its prompt
            from . import redesign as rd
            rd.ask(p, x.get("system"), by=by, why=f"the reviewer sent {x['id']} back")
    return verdict


def asked(p, by: str, parts, system: str | None = None) -> dict:
    """What a new proposal by ``by`` on these parts (a redesign: of this system) carries, when the reviewer sent back one
    of its own on them that no later proposal has answered: ``{"revising", "review_round", "review_asked"}``, else
    nothing."""
    every = pr.changes(p)
    answered = {f.get("revising") for _, f in every.values()}
    for pid, (st, f) in sorted(every.items(), key=lambda kv: -float(kv[1][1].get("created") or 0)):
        r = f.get("review") or {}
        if (st == "superseded" and r.get("verdict") == "revise" and f.get("made_by") == by and pid not in answered
                and (set(f.get("parts") or []) & set(parts or []) or (system and f.get("system") == system))):
            return {"revising": pid, "review_round": int(r.get("round") or 1) + 1, "review_asked": r.get("findings") or []}
    return {}


def memory(p, by: str, most: int = MEMORY) -> list[dict]:
    """The reviewer's latest verdicts on this author's own changes, newest first: what it said, so it stops repeating
    what was rejected."""
    mine = [f for _, f in pr.changes(p).values() if f.get("made_by") == by and f.get("review")]
    mine.sort(key=lambda f: -float(f["review"].get("at") or 0))
    return [{"title": f.get("title"), "parts": f.get("parts") or [], "verdict": f["review"]["verdict"],
             "findings": [g["says"] for g in f["review"].get("findings") or []][:3]} for f in mine[:most]]


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


def run(p, model: str = "haiku", most: int = 3, left: float = 1.0, timeout: float = 600.0, call=None, on_call=None) -> dict:
    """One pass: each change waiting for a review, while the day's allowance ``left`` lasts. Returns ``{"verdicts", "cost"}``."""
    from . import modeller as md
    call = call or md.call
    spec: Spec = p.model.spec
    out = {"verdicts": [], "cost": {"usd": 0.0, "calls": 0}}
    for x in due(p, spec)[:most]:
        if out["cost"]["usd"] >= left:
            out["verdicts"].append({"id": x["id"], "verdict": None, "why": "the day's allowance is spent"})
            break
        got = call(prompt(p, spec, x), model, timeout)
        usd = float(got.get("usd") or 0.0)
        out["cost"]["usd"] = round(out["cost"]["usd"] + usd, 6)
        out["cost"]["calls"] += 1
        p.events.add(RAN, source="reviewer", data={"change": x["id"], "usd": usd, "model": model})
        if on_call is not None:
            on_call(got)
        v = parse(got.get("result") or "")
        if v is None:                       # no verdict with specific reasons: nothing recorded; it is read again next pass
            out["verdicts"].append({"id": x["id"], "verdict": None, "why": got.get("error") or "no verdict with its reasons"})
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
                        if st == "regressed" and (f.get("review") or {}).get("verdict") == "pass")
    return out
