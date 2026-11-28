"""The drafter (SPEC §12e, *Unexplained events*): an AI agent of the modelling subsystem, on with ``ai: true``, given
the open event requests (``unexplained.py``: events no projection takes, grouped) and a prompt built from
AGENT-GUIDE §3o's recipe (``library/templates/modelling/drafter.md``). It looks at the events with ergostat's own
commands (``events shape``, ``events query``, ``events kinds``), drafts, tries and reviews (``projection try``,
``projection review``) until the review leaves nothing it targets unexplained, and answers with ``draft`` lines: a new
projection, or an existing one with new kinds of event. Each becomes an ordinary change to the model
(``unexplained.proposal_of``), checked and judged like any (``judge.py``: by what it takes); a change to the
projections is structure, written by the owner (the review queue, the inbox) unless the policy says otherwise.

Its session may run only those commands, and read and write only its own scratch folder; it changes no file of the
model. Its cost is counted with the AI tier's (``modeller_spend``, the template's ``ai-daily``): a session starts only
when the day's spend plus its whole budget stays within it."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

GUIDE = Path(__file__).resolve().parent.parent / "library" / "templates" / "modelling" / "drafter.md"
MOST = 4                    # requests given to one session
TRIES = 2                   # sessions on one request before it waits for the owner


def command_prefix() -> str:
    return f"{sys.executable} -m ergostat"


def tools(scratch: Path) -> list[str]:
    erg = command_prefix()
    return [f"Bash({erg} events:*)", f"Bash({erg} projection:*)", f"Write({scratch}/**)", f"Read({scratch}/**)",
            f"Edit({scratch}/**)"]


def prompt(p, spec, reqs: list[dict], scratch: Path) -> str:
    erg = command_prefix()
    lines = [GUIDE.read_text(encoding="utf-8"), "", "## How you run ergostat here", "",
             f"Every command is `{erg} ...`, run in the model's folder: `{erg} events shape`, "
             f"`{erg} events query \"QUERY\"`, `{erg} events kinds \"QUERY\"`, `{erg} projection try FILE --name NAME`, "
             f"`{erg} projection review FILE --name NAME` (each with `--json` for the whole answer). Write your drafts "
             f"in {scratch} (nowhere else).", "", "## The model's projections", ""]
    own = {n: k for n, k in (spec.items or {}).items() if not n.startswith("ergostat.")}
    for n, k in own.items():
        try:
            d = k.definition()
        except Exception:
            d = {}
        lines.append(json.dumps({"name": n, "query": d.get("query"), "key": d.get("key"),
                                 "kinds": [x.get("name") if isinstance(x, dict) else x for x in (d.get("kinds") or [])][:30]},
                                default=str, ensure_ascii=False))
    if not own:
        lines.append("(none yet)")
    lines += ["", "## The requests (each a group of events no projection takes)", ""]
    for r in reqs:
        u = r.get("unexplained") or {}
        lines.append(json.dumps({"id": r["id"], "group": r.get("group"), "count": u.get("count"),
                                 "first": u.get("first"), "last": u.get("last"), "examples": u.get("examples"),
                                 "why": u.get("by"), **({"why held": r["why"]} if r.get("why") else {})},
                                default=str, ensure_ascii=False))
    return "\n".join(lines)


def parse(text: str) -> tuple[list[dict], list[dict]]:
    """The draft lines and the cannot lines of an answer."""
    drafts, cannot = [], []
    for line in str(text or "").splitlines():
        line = line.strip().strip("`").strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("draft"), dict):
            drafts.append(obj["draft"])
        elif isinstance(obj, dict) and obj.get("cannot"):
            cannot.append(obj)
    return drafts, cannot


def run(p, model: str = "haiku", budget: float = 0.5, daily: float = 1.0, most: int = MOST,
        timeout: float = 900.0, on_call=None, by: str = "drafter") -> dict:
    """One run: the open event requests (``most`` at most, the largest first) given to one session within the day's
    cap; its drafts proposed. Returns ``{"proposed", "not_proposed", "cannot", "cost", "requests", "said"}``."""
    from . import improve as im
    from . import modeller as md
    from . import modeller_spend as sp
    from . import requests as rq
    from . import unexplained as ux
    spec = p.model.spec
    reqs = [r for r in ux.open_requests(p) if int((r.get("tried") or {}).get("ai") or 0) < TRIES]
    reqs = sorted(reqs, key=lambda r: -int((r.get("unexplained") or {}).get("count") or 0))[:most]
    out = {"proposed": [], "not_proposed": [], "cannot": [], "cost": {"usd": 0.0, "calls": 0}, "requests": len(reqs)}
    if not reqs:
        from . import unexplained as ux_
        mine = [r for r in rq.waiting(p, ("open", "proposed", "held")) if r.get("source") == ux_.SOURCE]
        waiting = [r for r in mine if r["state"] == "proposed"]
        owners = [r for r in mine if r["state"] != "proposed"]
        out["said"] = ("drafter: nothing to draft: " + "; ".join(x for x in (
            f"{len(waiting)} groups have a draft waiting for the owner (ergostat inbox, or the Fit page's review queue)"
            if waiting else "",
            f"{len(owners)} wait for the owner (tried {TRIES} times, or held)" if owners else "") if x)
            if mine else "drafter: no events wait for a projection")
        return out
    scratch = Path(p.dir) / "modelling" / "drafts" / time.strftime("%Y%m%dT%H%M%S")
    scratch.mkdir(parents=True, exist_ok=True)
    text = prompt(p, spec, reqs, scratch)
    try:
        with sp.held(p, budget, daily) as box:
            got = md.call(text, model, timeout, tools=tools(scratch), budget=budget, cwd=str(spec.root))
            if got.get("error"):                        # a session that failed may have spent its whole budget
                got["usd"] = max(float(got.get("usd") or 0), budget)
            box.append(got)
    except sp.Capped as e:
        out["said"] = f"drafter ({model}): {e}"
        out["capped"] = str(e)
        return out
    out["cost"] = {"usd": float(got.get("usd") or 0), "calls": 1, "tokens_in": got.get("tokens_in") or 0,
                   "tokens_out": got.get("tokens_out") or 0}
    if on_call is not None:
        on_call(got)
    share = round(out["cost"]["usd"] / max(1, len(reqs)), 6)
    if got.get("error"):
        for r in reqs:
            rq.mark(p, r, r["state"], error=got["error"][:500], cost_usd=round(float(r.get("cost_usd") or 0) + share, 6))
        out["said"] = f"drafter ({model}): {got['error']}"[:400]
        return out
    drafts, cannot = parse(got["result"])
    answered: set[str] = set()
    env_by = os.environ.get("ERGOSTAT_BLOCK") or by
    run_id = os.environ.get("ERGOSTAT_RUN") or None
    for d in drafts:
        try:
            raw = ux.proposal_of(p, spec, d)
            r = im.submit(p, env_by, raw, run=run_id)
        except Exception as e:                          # a draft that cannot even be placed: said, the rest proposed
            r = {"status": "not-proposed", "why": f"{type(e).__name__}: {e}", "title": d.get("title") or d.get("name")}
        if r["status"] == "proposed":
            out["proposed"].append(r["id"])
            answered |= {str(i).removeprefix("ergostat.modelling-request/") for i in d.get("requests") or []}
        else:
            out["not_proposed"].append({"title": r.get("title"), "why": r.get("why")})
    gone = {str(c.get("cannot")): str(c.get("why") or "") for c in cannot}
    out["cannot"] = list(gone)
    for r in reqs:
        tried = {**(r.get("tried") or {}), "ai": int((r.get("tried") or {}).get("ai") or 0) + 1}
        cost = round(float(r.get("cost_usd") or 0) + share, 6)
        if r["id"] in answered:
            rq.mark(p, r, r["state"], tried=tried, error=None, cost_usd=cost)
            continue
        why = gone.get(r["id"]) or ("its drafts were not proposed: " + "; ".join(
            f"{x['title']}: {x['why']}" for x in out["not_proposed"])[:400] if out["not_proposed"]
            else "the drafter drafted nothing for it")
        rq.mark(p, r, "held", f"the drafter ({model}): {why}", tried=tried, cost_usd=cost)
    out["said"] = (f"drafter ({model}): {len(out['proposed'])} proposed for {len(reqs)} requests, "
                   f"{len(out['not_proposed'])} not proposed, {len(gone)} it cannot; ${out['cost']['usd']:.4f}")
    return out
