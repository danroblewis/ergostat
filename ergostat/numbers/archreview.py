"""The daily architecture review (SPEC §12e, *Redesign*): once a day, inside the redesigner block's run, one call on a
model larger than haiku (``review``, sonnet by default) reads the model's architecture as a whole (the notes ``check``
gives, each system's size, interface and subsystems, each unit's fit and last redesign; never the YAML) and says
where a redesign should start. Each finding is held as a modelling request (``source: redesign``): ``review-redesign``
open, which makes its unit the next redesigned (``redesign_due.triggers``); ``review-split`` and ``review-merge`` held
for the owner and never acted on (they move parts between systems: structure, written only with approval). It writes
no model change and edits no file.

Bounds, all hard: one call a review (no retry), one review a day (``DAILY``: every result but ``capped`` counts, a
call started and never ended too), 8 findings, a prompt of 40,000 characters and 60 systems. Its cost shares the
redesigner's daily cap: it is not called when its estimated most (``modeller.unsaid``) is more than is left of the
cap for the redesigner's block (``redesign.room``: a quarter kept for the reviewer), checked and charged under the lock
``redesign.held`` takes; that estimate is charged before the call and the difference after, so a run killed mid-call keeps it
charged. ``claude -p`` takes no output limit, so a call can cost more than its estimate. Read, decided and written
under ``redesign.lock`` (``lock``), taken without waiting: a run that finds it held skips the review."""

from __future__ import annotations

import fcntl
import json
import math
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from . import modeller as md
from . import proposals as pr
from . import redesign as rd
from . import redesign_due as due
from .modeller_spend import Capped

REVIEWED = "ergostat.model.architecture-reviewed"
GUIDE = Path(__file__).resolve().parent.parent / "library" / "templates" / "modelling" / "architect.md"
LOCK = "redesign.lock"       # a fixed name in the project's state directory
NOTES = ("system-splits", "systems-merge", "interface", "time-scales", "purpose")
CODES = {"redesign": "review-redesign", "split": "review-split", "merge": "review-merge"}
FINDINGS = 8                 # findings taken from one review
CHARS = 40000                # the prompt, at most
SYSTEMS = 60                 # systems described in it, at most
SAYS = 600                   # a finding's words, at most
CHARGE = "(architecture review)"   # the system its calls are charged under: no system's name (asks are not answered by it)


@contextmanager
def lock(p):
    """``redesign.lock`` held exclusively, never waited for: yields whether it was taken."""
    p.dir.mkdir(parents=True, exist_ok=True)
    with open(p.dir / LOCK, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def due_now(p, now: float) -> bool:
    """No review today: no ``architecture-reviewed`` in the last ``DAILY`` but one ``capped`` (never called)."""
    return not any((e.get("data") or {}).get("result") != "capped"
                   for e in p.events.query(n=None, type=REVIEWED, since=now - due.DAILY))


def allowed(spec) -> tuple[set[str], set[str]]:
    """What a finding may name: the units a redesign can take (``model`` when the model has no systems of its own),
    and the model's own systems (for ``split`` and ``merge``)."""
    ok, _ = due.units(spec)
    return set(ok), {s for s in spec.systems if not (spec.uses.get(s) or {}).get("once")}


def prompt(p, spec, now: float) -> str:
    from ..spec import architecture as ar
    from ..spec.ir import template_made
    from . import redesigner as rdr
    from . import scorecard as sc
    units, own = allowed(spec)
    _, big = due.units(spec)
    lines = [GUIDE.read_text(encoding="utf-8"), "", "## The architecture notes check gives", ""]
    try:
        notes = [f"- {x.code}@{x.about}: {str(x.message)[:500]}" for x in p.model.problems
                 if x.code in NOTES and not template_made(x)]
    except Exception as e:                                       # unknown, never "none"
        notes = [f"(check could not be read: {type(e).__name__}: {e}; its notes are unknown)"]
    lines += notes or ["none"]
    lines += ["", "## Each system", ""]
    for s in sorted(own)[:SYSTEMS]:
        kinds = Counter()
        for x in spec.interface(s):
            kinds[x["kind"]] += len(x["peers"])
        subs = rdr.own_systems(spec, s)
        lines += [f"- system {s} (within {spec.within.get(s) or 'the model'}): {spec.systems[s] or 'no description'}",
                  f"  size: {ar.size_said(ar.size(spec, s))}",
                  "  interface: " + (", ".join(f"{n} {k}" for k, n in sorted(kinds.items())) or "nothing crosses it"),
                  f"  subsystems: {', '.join(subs) or 'none'}"
                  + (f"; {ar.nearly_decomposable(spec, s) or 'not nearly decomposable'}" if subs else "")]
    if len(own) > SYSTEMS:
        lines.append(f"- and {len(own) - SYSTEMS} more systems, not shown")
    if not own:
        lines.append("none: the model has no systems of its own; it is one unit, model")
    lines += ["", "## Each unit's replay fit (scaled error, lower is better; over 1 is worse than its mean)", ""]
    fit = sc.fit(p, spec)
    if fit.get("why"):
        lines.append(f"(the fit could not be read: {fit['why'][:300]}; it is unknown, not good)")
    for u in sorted(units):
        mine = sorted((r, s["nmse"]) for r, s in (fit.get("stocks") or {}).items()
                      if (s or {}).get("nmse") is not None and due._in(spec, u, r))
        lines.append(f"- {u}: " + (", ".join(f"{r} {v:.3g}" for r, v in mine[:12]) or "no stock replayed"))
    lines += ["", "## Each unit's last redesign", ""]
    last = {}
    for e in p.events.query(n=2000, type=rd.RAN):
        d = e.get("data") or {}
        if d.get("result") not in (None, "started", "call", "waiting"):
            last[d.get("system") or "model"] = d
    lines += [f"- {u}: " + (f"{last[u]['result']}" + (f" ({str(last[u].get('why_not'))[:200]})" if last[u].get("why_not") else "")
                            if u in last else "never redesigned") for u in sorted(units)]
    lines += ["", "## Too large to redesign (more than 40 parts and no subsystems)", "", *(f"- {u}" for u in big or ["none"])]
    lines += ["", "## What you may name", "", f"- redesign: {', '.join(sorted(units)) or 'none'}",
              f"- split or merge: {', '.join(sorted(own)) or 'none'}"]
    return "\n".join(lines)[:CHARS]


def parse(text: str, units: set[str], own: set[str]) -> tuple[list[dict] | None, list[str]]:
    """The findings of an answer, by allowlist, and what was dropped; None when it has no JSON line at all."""
    found, dropped, seen, any_json = [], [], set(), False
    for line in str(text or "").splitlines():
        line = line.strip().strip("`").strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        any_json = any_json or isinstance(obj, dict)
        r = obj.get("review") if isinstance(obj, dict) else None
        if not isinstance(r, dict):
            continue
        s, a = r.get("system"), r.get("advice")
        if a not in CODES:
            dropped.append(f"advice {str(a)[:40]!r}: not redesign, split or merge")
        elif not isinstance(s, str) or s not in (units if a == "redesign" else own):
            dropped.append(f"{a} of {str(s)[:40]!r}: not one of the model's {'units' if a == 'redesign' else 'systems'}")
        elif (s, a) in seen:
            dropped.append(f"{a} of {s}: said again, the first kept")
        elif len(found) >= FINDINGS:
            dropped.append(f"{a} of {s}: past the {FINDINGS} findings a review takes")
        else:
            seen.add((s, a))
            found.append({"system": s, "advice": a, "says": str(r.get("says") or "")[:SAYS]})
    return (found if any_json else None), dropped


def hold(p, found: list[dict], stamp: str) -> list[str]:
    """Each finding held as a request stamped with the review that raised it; one raised before and not said again
    answered, but one ``proposed`` (waiting on its change)."""
    from . import requests as rq
    ids = []
    for f in found:
        code, mine = CODES[f["advice"]], f["advice"] == "redesign"
        ids.append(due.hold(p, f["system"], code, f["says"], owner=not mine, state="open" if mine else "held",
                            more={"review": stamp, **({"why": None} if mine else {})}, keep=("proposed",)))
    for k, x in rq.stored(p).items():
        if x.get("source") == "redesign" and x.get("code") in CODES.values() and x["state"] in ("open", "held") \
                and k not in ids:
            rq.move(p, k, "answered", {"why": "the architecture review no longer says it"}, ("open", "held"))
    return ids


def _charge(p, usd: float, now: float, model: str) -> None:
    p.events.add(rd.RAN, item=p.model.name, source="architecture-review", at=now,
                 data={"system": CHARGE, "by": "architecture-review", "result": "call", "model": model,
                       "cost": {"usd": round(usd, 6)}, "estimated": True})


def timeouts(timeout: float | None, rounds: int) -> tuple[float, float | None]:
    """The review's call limit, and the timeout the redesign after a called review is given: one share of the block's
    timeout in ``rounds + 1`` each, so the review's call and the rounds' calls together keep ``per_call``'s room."""
    r = max(1, int(rounds))
    return md.per_call(timeout, r + 1), (float(timeout) * r / (r + 1) if timeout else None)


def run(p, model: str, daily: float, timeout: float | None = None, now: float | None = None, call=None,
        on_call=None) -> dict:
    """The review, if it is due: ``{"result", "said", "findings"}`` (result None: not run). ``timeout``: the call's
    own time limit."""
    now = now or time.time()
    call = call or md.call
    with lock(p) as mine:
        if not mine:
            return {"result": None, "said": "architecture review: another run holds redesign.lock; skipped this run"}
        if not due_now(p, now):
            return {"result": None, "said": "architecture review: done today"}
        spec = p.model.spec
        text = prompt(p, spec, now)
        est = md.unsaid(text, model)["usd"]
        with pr.locked(p):                              # the lock redesign.held takes: the reviewer's checks wait on it
            left = rd.room(p, daily, now)               # the cap, less the share kept for the reviewer
            if est > left:                              # its estimated most past what is left: not called
                p.events.add(REVIEWED, item=p.model.name, source="architecture-review", at=now,
                             data={"result": "capped", "model": model, "estimate": est, "left": left, "daily": daily})
                return {"result": "capped", "said": f"architecture review ({model}): not called: ${left:.4f} left "
                        f"of the ${daily:.2f} cap (a quarter kept for the reviewer) and its estimated most is ${est:.4f}"}
            try:
                permit = md.ask(p, text, model)         # the day's budget, before the day's review is stamped
            except Capped as e:
                p.events.add(REVIEWED, item=p.model.name, source="architecture-review", at=now,
                             data={"result": "capped", "model": model, "estimate": est, "why": str(e)})
                return {"result": "capped", "said": f"architecture review ({model}): not called: {e}"}
            stamp = p.events.add(REVIEWED, item=p.model.name, source="architecture-review", at=now,
                                 data={"result": "started", "model": model, "estimate": est})["id"]   # the day's review
            _charge(p, est, now, model)                 # before the call: a run killed mid-call keeps it charged
        # (the caller's per_call: it and the rounds fit the block's)
        got = md.asked(p, text, model, timeout or 600.0, call, permit)
        usd = got.get("usd")
        usd = float(usd) if isinstance(usd, int | float) and not isinstance(usd, bool) and math.isfinite(usd) \
            and usd >= 0 else est                       # a cost unsaid or not a number: its estimate stands
        _charge(p, usd - est, now, model)
        if on_call is not None:
            on_call({**got, "usd": usd})
        found, dropped = (None, []) if got.get("error") else parse(got.get("result"), *allowed(spec))
        ids = hold(p, found, stamp) if found is not None else []
        result = "reviewed" if found is not None else "failed"
        why = got.get("error") or ("the answer had no JSON line" if found is None else None)
        p.events.add(REVIEWED, item=p.model.name, source="architecture-review", at=now,
                     data={"result": result, "model": model, "cost": {"usd": usd}, "findings": ids, "dropped": dropped,
                           "review": stamp, **({"why": str(why)[:500]} if why else {})})
    said = "; ".join(f"{f['advice']} {f['system']}" for f in found or []) or "nothing to redesign"
    return {"result": result, "findings": ids,
            "said": f"architecture review ({model}): {result}: " + (str(why)[:300] if why else said)
            + (f"; dropped: {'; '.join(dropped)}" if dropped else "") + f"; ${usd:.4f}"}


def mark(p, review: dict, out: dict) -> str:
    """The review request a redesign took up, marked after the run (``proposed`` with its change, or ``answered``
    with its result), only if, read again under both locks, it is open with the stamp the plan read."""
    from . import requests as rq
    k, stamp = review["id"], review.get("stamp")
    with lock(p) as mine:
        if not mine:
            return "the review's request left unmarked: another run holds redesign.lock"
        with rq.locked(p):
            x = rq.stored(p).get(k)
            if x is None or x["state"] != "open" or x.get("review") != stamp:
                return "the review's request left as it is: a newer review said it again, or it moved"
            if out.get("result") == "proposed":
                rq.event(p, k, "proposed", {"change": out.get("id"), "why": None})
            elif out.get("result") not in ("error", "no budget"):
                rq.event(p, k, "answered", {"why": f"its redesign: {out.get('result')}"
                                            + (f": {out['why_not']}" if out.get("why_not") else "")})
            else:
                return "the review's request left open: the redesigner's call " + (
                    "was refused" if out.get("result") == "no budget" else "failed")
    return f"the review's request {out.get('result')}"
