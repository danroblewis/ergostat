"""The AI rung of the architecture review (docs/proposals/architecture.md §7, §8; SPEC §12): one system read against
Beer's Viable System Model and its goals against its purpose, by one call (haiku by default), on the owner's word.

The reviewer is given a brief (the system's words, its parts, interface, architecture notes and the computed
checklist, ``spec/vsm.py``) and answers with one JSON line. The answer is checked, not trusted: a function said
present must name one of the system's own parts (else it is *unsupported*: dropped and counted); a goal must be the
system's, and a quote the owner's words (found in the description or the model's purpose, after ``ai.norm``). What
is kept becomes modelling requests (``source: architecture``) held for the owner; an applied review answers an
earlier one only on positive evidence it kept (that function present with a real part; purpose coverage reviewed
with nothing left uncovered; that goal said to serve). A call that fails, times out, errs or gives no answer line
is recorded as unreviewed and changes nothing. Its cost is recorded: the whole cap when none was reported."""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

from ..costs import budget
from ..decisions import ai
from ..spec import vsm
from ..spec.ir import Spec

PROMPT = Path(__file__).with_name("vsm_prompt.md")
SYSTEM = "You review a control-system model against the Viable System Model. Answer with one JSON line only."
PER_CALL = 0.25            # dollars one call may spend (Claude Code's --max-budget-usd)
MAX_COST = 1.00            # a run's default cap
CEILING = 5.00             # a run's cap at most
MOST_SYSTEMS = 12          # systems one run reviews at most
BRIEF_CHARS = 30000
TIMEOUT = 300
REVIEWED, UNREVIEWED = "ergostat.architecture.reviewed", "ergostat.architecture.unreviewed"
CODES = {"S1": "vsm-s1", "S2": "vsm-s2", "S3": "vsm-s3", "S3*": "vsm-s3-audit", "S4": "vsm-s4", "S5": "vsm-s5"}
NAMES = {"S1": "operations", "S2": "coordination", "S3": "control", "S3*": "audit", "S4": "intelligence",
         "S5": "policy"}
TABLES = {"stock": "stocks", "flow": "flows", "auxiliary": "auxiliaries", "goal": "goals", "block": "blocks"}


def systems(spec: Spec) -> list[str]:
    """The systems a review may take: the model's own (a once template's, as ``use: modelling``'s, never)."""
    return sorted(s for s in spec.systems if not (spec.uses.get(s) or {}).get("once"))


def _goals(spec: Spec, system: str) -> list[str]:
    """The goals directly in the system: a subsystem's are its own review's (their requests are about the goal)."""
    mine = vsm.parts(spec, system)
    return sorted(g for g, x in spec.goals.items() if x.system == system and f"goal.{g}" in mine)


def words(spec: Spec, system: str) -> str:
    """The words a review read: the model's purpose, the system's description, its subsystems' and its goals'."""
    got = [spec.purpose, spec.systems.get(system) or "", [spec.systems.get(s) or "" for s in spec.subsystems(system)],
           [[g, spec.goals[g].description] for g in _goals(spec, system)]]
    return hashlib.sha256(json.dumps(got).encode()).hexdigest()[:16]


def signature(spec: Spec, system: str) -> str:
    from .redesign_due import signature as sig
    return sig(spec, system)


def notes(spec: Spec, system: str) -> list[tuple[str, str]]:
    from ..spec import architecture as ar
    out: list[tuple[str, str]] = []
    ar.findings(spec, lambda code, msg, _, about: out.append((code, msg)) if about == f"system.{system}" else None)
    return out


def brief(spec: Spec, system: str) -> str:
    desc = spec.systems.get(system) or ""
    out = [f"# System {system}", "", f"Description: {desc or '(none: it says nothing of what it is for)'}",
           f"The model's purpose: {spec.purpose or '(none)'}", "", "## Its parts"]
    for ref in sorted(p for p in vsm.parts(spec, system) if not p.startswith("system.")):
        kind, name = ref.split(".", 1)
        x = getattr(spec, TABLES[kind]).get(name)
        what = (f" (holds {x.of} {x.hold})" if kind == "goal" else f" ({x.type})" if kind == "block" else "")
        out.append(f"- {ref}{what}: {getattr(x, 'description', '') or '(no description)'}")
    out += ["", "## Its subsystems"]
    out += [f"- system.{s}: {spec.systems.get(s) or '(no description)'}" for s in spec.subsystems(system)] or ["- none"]
    out += ["", "## Its interface (what crosses its boundary)"]
    out += [f"- {p['dir']} {p['kind']} {p['part']}: {', '.join(p['peers'])}" for p in spec.interface(system)] or ["- nothing"]
    out += ["", "## Architecture notes check reports about it"]
    out += [f"- {c}: {m}" for c, m in notes(spec, system)] or ["- none"]
    out += ["", "## The computed checklist (evidence, not an answer)"]
    for f, xs in vsm.checklist(spec, system).items():
        out.append(f"### {f} {NAMES[f]}")
        out += [f"- {x['part']}: {x['why']}" for x in xs] or ["- no candidates"]
    text = "\n".join(out)
    if len(text) > BRIEF_CHARS:
        cut = f"\n\n[the brief is cut at {BRIEF_CHARS} characters; it had {len(text)}]"
        text = text[:BRIEF_CHARS - len(cut)] + cut
    return text


def _answer(text: str) -> dict | None:
    for raw in reversed((text or "").splitlines()):
        raw = raw.strip().strip("`").strip()
        if raw.startswith("{"):
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if isinstance(d, dict) and isinstance(d.get("functions"), list):
                return d
    return None


def _quote(x) -> str:
    return ai.norm(str(x or "")).strip().strip('"').strip()


def checked(spec: Spec, system: str, d: dict) -> dict:
    """The answer as kept: ``functions`` (s → present, parts, why), ``unsupported``, ``purpose`` (None: not reviewed)
    and ``dropped``, the entries thrown away."""
    mine, own = vsm.parts(spec, system), {"description": spec.systems.get(system), "purpose": spec.purpose}
    fns, unsupported, dropped = {}, [], 0
    for e in d.get("functions") or []:
        s = e.get("s") if isinstance(e, dict) else None
        if not isinstance(s, str) or s not in CODES or s in fns or s in unsupported or not isinstance(e.get("present"), bool):
            dropped += 1
            continue
        why = str(e.get("why") or "")[:500]
        cited = [x for x in (e.get("parts") if isinstance(e.get("parts"), list) else []) if isinstance(x, str)]
        real = [x for x in cited if x in mine or (s == "S5" and own.get(x))]
        if e["present"] and not real:
            unsupported.append(s)
            dropped += 1
            continue
        fns[s] = {"present": e["present"], "parts": real if e["present"] else [], "why": why}
    purpose = None
    if spec.systems.get(system):
        desc, goals = ai.norm(spec.systems[system]), set(_goals(spec, system))
        pu = d.get("purpose") if isinstance(d.get("purpose"), dict) else {}
        serves, off, uncovered = [], [], []
        for e in pu.get("goals") if isinstance(pu.get("goals"), list) else []:
            g = str(e.get("goal") or "").removeprefix("goal.") if isinstance(e, dict) else ""
            q = _quote(e.get("quote")) if g else ""
            if g not in goals or g in {x["goal"] for x in serves + off} or not isinstance(e.get("serves"), bool) \
                    or (e["serves"] and not (q and q in desc)):
                dropped += 1
                continue
            (serves if e["serves"] else off).append({"goal": g, "quote": q})
        given = pu.get("uncovered") if isinstance(pu.get("uncovered"), list) else []
        texts = [t for t in (desc, ai.norm(spec.purpose)) if t]
        for e in given:
            q = _quote(e.get("quote")) if isinstance(e, dict) else ""
            if len(q.split()) < 2 or not any(q in t for t in texts):
                dropped += 1
                continue
            uncovered.append({"quote": q, "why": str(e.get("why") or "")[:300]})
        purpose = {"serves": serves, "off": off, "uncovered": uncovered,
                   "complete": "uncovered" in pu and len(uncovered) == len(given)}
    return {"functions": fns, "unsupported": unsupported, "purpose": purpose, "dropped": dropped}


def _latest(p, system: str, applied: bool = False) -> dict | None:
    """The latest review of the system by seq (never by time); ``applied``: the latest that was applied."""
    evs = [e for e in p.events.query(n=None, type=REVIEWED) if (e.get("data") or {}).get("system") == system
           and (not applied or (e.get("data") or {}).get("applied"))]
    return max(evs, key=lambda e: e.get("seq") or 0, default=None)


def latest(p, system: str) -> dict | None:
    """The latest applied review's data, with its seq: what ``explain system.NAME`` says."""
    e = _latest(p, system, applied=True)
    return {**e["data"], "seq": e["seq"]} if e else None


def _call(prompt: str, model: str, cap: float, spent: ai.Spent, seen: dict, permit: dict | None = None) -> str:
    return ai.call(prompt, model, cap, spent, timeout=TIMEOUT, system=SYSTEM, group=True, seen=seen, capped=True,
                   permit=permit)


def review(p, spec: Spec, system: str, model: str = "haiku", cap: float = PER_CALL, permit: dict | None = None) -> dict:
    """One system reviewed by one call, checked, recorded, and what it found held for the owner. ``permit``: the
    day's budget's for the call (SPEC §9.9), closed at its end."""
    cap = min(float(cap), CEILING)
    before = _latest(p, system)
    stamp = {"system": system, "signature": signature(spec, system), "words": words(spec, system), "model": model}
    spent, seen = ai.Spent(), {}
    try:
        text, why = _call(PROMPT.read_text(encoding="utf-8") + "\n\n" + brief(spec, system), model, cap, spent, seen,
                          permit=permit), None
    except Exception as e:                       # (a cost or a usage that is not a number, among others)
        text, why = "", f"{type(e).__name__}: {e}"[:300]
    budget.done(permit, None)                    # (closed by its call; else, failed before it: charged its reserve)
    c = seen.get("cost")
    ok = isinstance(c, int | float) and not isinstance(c, bool) and math.isfinite(c) and c >= 0
    cost = {"cost_usd": round(float(c), 6) if ok else cap, "cost": "reported" if ok else "charged",
            "tokens": spent.tokens_in + spent.tokens_out}
    try:                                         # an answer that cannot be read is unreviewed, at its cost
        d = _answer(text) if not why else None
        got = checked(spec, system, d) if d is not None else None
    except Exception as e:
        d, why = None, why or f"unreadable answer: {type(e).__name__}: {e}"[:300]
    why = why or seen.get("error") or (f"exit {seen['rc']}" if seen.get("rc") else None) or \
        ("is_error: " + "; ".join(spent.notes)[:300] if seen.get("is_error") else None) or \
        (None if d is not None else "no readable answer line")
    if why:
        p.events.add(UNREVIEWED, item=p.model.name, source="architecture", data={**stamp, **cost, "why": why})
        return {"system": system, "reviewed": False, "why": why, **cost}
    from . import proposals as pr
    with pr.locked(p, "architecture"):          # read again inside: a review recorded since wins
        now = _latest(p, system)
        applied = (now or {}).get("seq") == (before or {}).get("seq")
        seq = p.events.add(REVIEWED, item=p.model.name, source="architecture",
                           data={**stamp, **cost, **got, "applied": applied})["seq"]
        moved = _requests(p, spec, system, got, seq, model) if applied else {"raised": 0, "answered": 0}
    fns = got["functions"]
    return {"system": system, "reviewed": True, "applied": applied, "seq": seq, **cost, **moved,
            "present": [s for s in fns if fns[s]["present"]], "missing": [s for s in fns if not fns[s]["present"]],
            "unsupported": got["unsupported"], "dropped": got["dropped"]}


def _said(spec: Spec, system: str, got: dict, model: str) -> tuple[dict, set]:
    """What the review says (request key → code, about, says) and what it shows is no longer so."""
    from . import requests as rq
    about, cl = f"system.{system}", vsm.checklist(spec, system)
    said, gone = {}, set()
    for s, f in got["functions"].items():
        k = rq.rid("architecture", CODES[s], about)
        if f["present"]:
            gone.add(k)
            continue
        had = [x["part"] for x in cl[s]]
        said[k] = (CODES[s], about, f"system {system}: the reviewer ({model}) finds no {s} ({NAMES[s]}) in it: "
                   f"{f['why'] or 'no reason given'}" + (f"; the computed checklist had candidates: {', '.join(had)}"
                                                         if had else ""))
    pu = got["purpose"]
    if pu is not None:
        k = rq.rid("architecture", "purpose-uncovered", about)
        if pu["uncovered"]:
            said[k] = ("purpose-uncovered", about, f"system {system}: no goal measures what it says it is for: "
                       + "; ".join(f"\"{u['quote']}\"" + (f" ({u['why']})" if u["why"] else "") for u in pu["uncovered"]))
        elif pu["complete"]:
            gone.add(k)
        for x in pu["off"]:
            said[rq.rid("architecture", "goal-off-purpose", f"goal.{x['goal']}")] = (
                "goal-off-purpose", f"goal.{x['goal']}", f"goal {x['goal']}: the reviewer ({model}) finds it serves "
                f"nothing system {system} says it is for")
        gone |= {rq.rid("architecture", "goal-off-purpose", f"goal.{x['goal']}") for x in pu["serves"]}
    return said, gone - set(said)


def _requests(p, spec: Spec, system: str, got: dict, seq: int, model: str) -> dict:
    """Each kept result held for the owner; each it shows is no longer so answered. Under the requests' lock."""
    from . import requests as rq
    from . import version as ver
    said, gone = _said(spec, system, got, model)
    v, now, moved = ver.version(spec), time.time(), {"raised": 0, "answered": 0}
    held = {"owner": True, "tier": "owner", "version": v, "review": seq}
    with rq.locked(p):
        have = rq.stored(p)
        for k, (code, about, says) in said.items():
            x = have.get(k)
            if x is not None and x["state"] == "dismissed" and x.get("part") == ver.part(spec, about):
                continue                         # the owner dismissed it, and its part is as it was
            data = {"source": "architecture", "code": code, "about": about, "says": says, "level": "finding", **held}
            if x is None:
                rq.event(p, k, "raised", {**data, "raised": now, "since": now})
            elif x["state"] in ("answered", "dismissed"):
                rq.event(p, k, "reopened", {**data, "since": now, "why": None, "change": None, **rq.fresh(), **held})
            elif x["state"] == "held" and x.get("says") == says:
                continue
            rq.event(p, k, "held", {**data, "why": "a judgement of the architecture: the owner's to make"})
            moved["raised"] += 1
        for k in gone:
            x = have.get(k)
            if x is not None and x.get("source") == "architecture" and x["state"] in rq.OPEN:
                rq.event(p, k, "answered", {"answered": now, "review": seq, "why": f"the architecture review "
                                            f"(seq {seq}) no longer says it"})
                moved["answered"] += 1
    return moved


def review_all(p, spec: Spec, system: str | None = None, model: str = "haiku", max_cost: float = MAX_COST) -> dict:
    """One system, or every one of the model's own: at most ``MOST_SYSTEMS``, and a call only while ``spent +
    PER_CALL`` stays within ``max_cost`` (at most ``CEILING``)."""
    if not (isinstance(max_cost, int | float) and math.isfinite(max_cost) and 0 < max_cost <= CEILING):
        raise ValueError(f"--max-cost is at most ${CEILING:.2f} (and more than 0)")
    own = systems(spec)
    if system is not None and system not in own:
        raise ValueError(f"no system {system!r} of the model's own to review (systems: {', '.join(own) or 'none'})")
    todo = [system] if system else own
    out = {"reviews": [], "not_reviewed": [{"system": s, "why": f"more than {MOST_SYSTEMS} systems in one run"}
                                           for s in todo[MOST_SYSTEMS:]], "max_cost": max_cost, "spent": 0.0}
    for i, s in enumerate(todo[:MOST_SYSTEMS]):
        if out["spent"] + PER_CALL > max_cost:
            out["not_reviewed"][:0] = [{"system": x, "why": f"the cost cap (${max_cost:.2f}) would be passed"}
                                       for x in todo[i:MOST_SYSTEMS]]
            break
        permit, no = budget.ask(p, spec, "architecture-review", PER_CALL)
        if no:                                   # (the day's budget, SPEC §9.9: this and the rest not reviewed)
            out["not_reviewed"][:0] = [{"system": x, "why": f"budget: {no}"} for x in todo[i:MOST_SYSTEMS]]
            break
        r = review(p, spec, s, model, PER_CALL, permit=permit)
        out["reviews"].append(r)
        out["spent"] = round(out["spent"] + r["cost_usd"], 6)
    return out
