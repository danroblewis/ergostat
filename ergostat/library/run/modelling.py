"""The modelling template's programs (SPEC §12e): the request collector and the tiers that answer the requests.

    modelling requests [--no-coherence] [--no-extremes]
        the collector: what check finds raised as requests (ergostat.modelling-request), what it no longer finds answered;
        prints how many are open (the sensor's reading)
    modelling rules [--most N]
        the rule tier: a mechanical change for each open request it can answer, recorded as made and checked here
        (``submitted``), as the engine does a propose line; the rest handed to the ai tier
    modelling ai --daily D [--model haiku] [--most N] [--tries N]
        the ai tier: the requests the rule tier could not answer, given to claude -p with the modelling guides; what it
        proposes, tried first, recorded as made and checked here; its cost recorded on the requests it was given
    modelling redesign [--when ask|off] [--model haiku] [--budget 0.5] [--rounds 3] [--daily 2]
        the redesigner: what the owner asked for, one change set for a whole system, made on a scratch copy over a few
        rounds and proposed as one change (redesign.py), within the day's cap; its cost printed as a result line
    modelling review [--model haiku] [--most N] [--daily 2]
        the reviewer: each change the judge passed of a reviewed kind, read as a senior modeller would; its verdict
        (pass, revise, reject) recorded on the change (reviewer.py), within the same daily cap

Each prints a line for the block's log on standard error, and nothing else on standard output but its readings (and
the ai tier's and the redesigner's result lines, and the redesigner's report lines)."""

from __future__ import annotations

import argparse
import sys

from .common import kept, note, now, project


def submitted(p, raws: list[dict], by: str) -> int:
    """The tier's changes recorded as made and checked here, in the tier's own process, as the engine does a propose
    line: checking one runs the model it leaves through check (seconds on a large model), which in the engine's process
    would hold up the page and the sensors. Returns how many were proposed; each one turned away is said in the log."""
    import os

    from ...numbers import improve as im
    by, run, n = os.environ.get("ERGOSTAT_BLOCK") or by, os.environ.get("ERGOSTAT_RUN") or None, 0
    for raw in raws:
        try:
            got = im.submit(p, by, raw, run=run)
        except Exception as err:                      # one that cannot even be judged: said, the rest still made
            got = {"status": "not-proposed", "why": f"{type(err).__name__}: {err}", "title": raw.get("title") or ""}
        if got["status"] == "not-proposed":
            note(f"not proposed: {got.get('title') or raw.get('title')}: {got['why']}"[:400])
        else:
            n += 1
    return n


def requests(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="modelling requests")
    ap.add_argument("--no-coherence", action="store_true")
    ap.add_argument("--no-extremes", action="store_true")
    ap.add_argument("--window", type=float, default=600.0, help="seconds the arrivals are averaged over")
    a = ap.parse_args(argv)
    from ...numbers import requests as rq
    p = project()
    got = rq.sync(p, coherence=not a.no_coherence, extremes=not a.no_extremes)
    moved = ", ".join(f"{k} {v}" for k, v in got.items() if k != "open" and v)
    note(f"requests: {got['open']} not answered" + (f" ({moved})" if moved else ""))
    t = now()
    with kept("modelling", "requests") as mem:          # the arrivals an hour, as the collect template's sensor says them
        arrivals = [x for x in mem.get("arrivals", []) if x > t - a.window]
        arrivals += [t] * int(got["raised"] + got["reopened"])
        mem["arrivals"] = arrivals
    print(round(len(arrivals) * 3600.0 / a.window, 6))
    return 0


def rules(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="modelling rules")
    ap.add_argument("--most", type=int, default=6)
    a = ap.parse_args(argv)
    sys.stdin.read()                                     # the block's input: the goal; the requests are in the record
    from ...numbers import requests as rq
    from ...numbers import rules as ru
    p = project()
    mine = [r for r in rq.waiting(p, ("open",)) if r.get("tier") == "rule"]
    if not mine:
        note("rules: no open request the rule tier answers")
        return 0
    made, none = ru.propose(p, mine, most=a.most)
    for r, why in none:
        rq.mark(p, r, "held", f"the rule tier has no certain change for it: {why}", tier="ai")
    got = submitted(p, [raw for _, raw in made], "fixer")
    note(f"rules: {got} proposed, {len(none)} handed on (of {len(mine)} open)")
    return 0


def ai(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="modelling ai")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--most", type=_between(int, 1, 16), default=8, help="requests given to one call (1 to 16)")
    ap.add_argument("--tries", type=_between(int, 1, 3), default=2,
                    help="calls on one request before it waits for the owner (1 to 3)")
    ap.add_argument("--daily", type=_between(float, 0, 20), required=True,
                    help="dollars a day (0 to 20): a call starts only if the day's spend plus its reservation stays within")
    ap.add_argument("--timeout", type=float, default=None, help="the block's timeout, in seconds: its calls fit in it")
    a = ap.parse_args(argv)
    sys.stdin.read()

    from ...numbers import modeller as md
    from ...numbers import modeller_spend as sp
    from ...numbers import requests as rq
    p = project()
    mine = [r for r in rq.waiting(p, ("open", "held")) if r.get("tier") == "ai" and not r.get("owner")
            and int((r.get("tried") or {}).get("ai") or 0) < a.tries]
    if not mine:
        note("modeller: no request waiting for the ai tier")
        return 0
    group = _near(p, mine)[:a.most]
    got = md.answer(p, group, a.model, timeout=md.per_call(a.timeout, 2), on_call=_said,
                    within=lambda text: sp.held(p, md.unsaid(text, a.model)["usd"], a.daily))
    c = got["cost"]
    said = "".join(f"; a call cost ${o:.4f} over its ${r:.4f} reservation" for o, r in c.get("over") or [])
    said += f"; {c['capped']}" if c.get("capped") else ""
    if not c.get("calls"):                       # no call made: the requests are left as they were (no try counted)
        note(f"modeller ({a.model}): no call for {len(group)} requests{said}")
        return 0
    answered = {e for raw in got["proposals"] for r in raw.get("reasons") or []
                for e in ([r.get("evidence")] if not isinstance(r.get("evidence"), list) else r.get("evidence"))}
    cannot = {x.get("cannot"): x.get("why") for x in got["cannot"]}
    share = round(c["usd"] / max(len(group), 1), 6)
    if c.get("error") and not got["tried"]:      # its first call failed: charged, the error said, no try used
        for r in group:
            rq.event(p, r["id"], r["state"], {"why": f"the ai tier's call failed: {c['error']}"[:500], "error": c["error"][:500],
                                              "cost_usd": round(float(r.get("cost_usd") or 0) + share, 6)})
        note(f"modeller ({a.model}): {c['error']}; ${c['usd']:.4f} charged, no try used for {len(group)} requests{said}")
        return 0
    for r in group:
        tried = {**(r.get("tried") or {}), "ai": int((r.get("tried") or {}).get("ai") or 0) + 1}
        if rq.evidence_of(r) in answered:
            rq.event(p, r["id"], r["state"], {"tried": tried, "error": None,
                                              "cost_usd": round(float(r.get("cost_usd") or 0) + share, 6)})
            continue
        why = cannot.get(r["id"]) or (f"its second call failed: {c['error']}"[:500] if c.get("error")
                                      else "the ai tier proposed nothing that would be proposed")
        rq.mark(p, r, "held", f"the ai tier ({a.model}): {why}", tried=tried, error=c.get("error"),
                cost_usd=round(float(r.get("cost_usd") or 0) + share, 6))
    n = submitted(p, got["proposals"], "modeller")
    note(f"modeller ({a.model}): {n} proposed for {len(group)} requests, {len(cannot)} it cannot; "
         f"${c['usd']:.4f}, {c['tokens_in']} tokens in, {c['tokens_out']} out, {c['calls']} call(s)"
         + (f"; {c['error']}" if c.get("error") else "") + said)
    return 0


def _between(kind, lo, hi):
    """An argparse type: a ``kind`` from ``lo`` to ``hi`` (a count or an amount that multiplies calls or money)."""
    def one(s: str):
        try:
            x = kind(s)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a {kind.__name__}: {s!r}") from None
        if not lo <= x <= hi:                      # (NaN fails this too)
            raise argparse.ArgumentTypeError(f"{s} is outside {lo} to {hi}")
        return x
    return one


def redesign(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="modelling redesign")
    ap.add_argument("--when", default="auto", choices=("auto", "ask", "off"))
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--budget", type=float, default=0.5)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--daily", type=float, default=2.0, help="the most dollars the redesigner's runs spend in a day")
    ap.add_argument("--timeout", type=float, default=None, help="the block's timeout, in seconds: its rounds fit in it")
    a = ap.parse_args(argv)
    sys.stdin.read()
    import json

    from ...numbers import redesign as rd
    from ...numbers import redesigner as rdr
    p = project()
    if a.when == "off":
        note("redesigner: off")
        return 0
    from ...numbers import reviewer as rv
    def room() -> float:                          # read again before each call: the reviewer may spend meanwhile
        # the reviewer's share of the cap is kept for it
        return round(min(a.daily - rd.spent(p), a.daily * (1 - rv.RESERVE) - rd.spent(p, reviewer=False)), 6)
    left = room()
    if left <= 0:                                # the daily cap, before anything is planned: nothing runs past it
        note(f"redesigner: the day's ${a.daily:.2f} is spent; nothing is reviewed until tomorrow's allowance")
        return 0
    plan = rd.plan(p, a.when)
    if plan["system"] is None:
        note(f"redesigner: nothing to do ({'; '.join(plan['why'])})")
        return 0
    from ...numbers import redesign_due as due
    sig = plan.get("unit_sig") or due.signature(p.model.spec, plan["system"])
    rd.ran(p, plan["system"], {"by": "redesigner", "result": "started", "why": plan["why"],
                               "version": rd.ver.version(p.model.spec), "unit_sig": sig})
    req = due.hold(p, plan["system"], "redesign-due", "; ".join(plan["why"]), state="open")   # its trigger, said

    def charged(got: dict) -> None:               # each call charged as it is spent, so a run cut short still counts
        _said(got)
        rd.charge(p, plan["system"], got)
    out = rdr.run(p, plan["system"], plan["why"], model=a.model, budget=min(a.budget, left), rounds=a.rounds, by="redesigner",
                  timeout=a.timeout, on_call=charged, room=room)
    rd.ran(p, plan["system"], {"by": "redesigner", "result": out.get("result"), "id": out.get("id"), "total": out["cost"],
                               "version": out["version"], "rounds": len(out["rounds"]), "why": plan["why"], "unit_sig": sig,
                               **({"why_not": out["why_not"]} if out.get("why_not") else {})})
    from ...numbers import requests as rq
    if out.get("result") == "proposed":
        rq.event(p, req, "proposed", {"change": out.get("id"), "why": None})
    elif out.get("result") == "error":           # its call failed: the request stays open, saying so
        rq.event(p, req, "open", {"why": f"the redesigner's call failed: {out['why_not']}"[:500]})
    else:
        rq.event(p, req, "answered", {"why": f"{out.get('result')}" + (f": {out['why_not']}" if out.get("why_not") else "")})
    for r in out.get("reports") or []:                        # what ergostat could not express: drafted for the owner
        print(json.dumps({"report": r}), flush=True)
    c = out["cost"]
    note(f"redesigner ({a.model}): {plan['system']}: {out.get('result')}" + (f" ({out.get('why_not')})" if out.get("why_not") else "")
         + (f", {out['scorecard']['verdict']}" if out.get("scorecard") else "")
         + f"; {len(out['rounds'])} round(s), ${c['usd']:.4f}, {c['calls']} call(s)")
    return 0


def review(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="modelling review")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--most", type=int, default=3, help="changes read in one run")
    ap.add_argument("--daily", type=float, default=2.0, help="the template's daily cap, shared with the redesigner")
    ap.add_argument("--timeout", type=float, default=None)
    a = ap.parse_args(argv)
    sys.stdin.read()
    from ...numbers import modeller as md
    from ...numbers import redesign as rd
    from ...numbers import reviewer as rv
    p = project()
    left = round(a.daily - rd.spent(p), 6)
    if left <= 0:                                 # the cap, before any call: what waits for review stays unwritten
        note(f"reviewer: the day's ${a.daily:.2f} is spent; nothing is reviewed until tomorrow's allowance")
        return 0
    out = rv.run(p, a.model, a.most, left, md.per_call(a.timeout, a.most), on_call=_said,
                 room=lambda: round(a.daily - rd.spent(p), 6))     # read again before each call: the redesigner may spend
    said = ", ".join(f"{v['id']} {v['verdict'] or 'no verdict: ' + v['why']}" for v in out["verdicts"]) or "nothing waits"
    note(f"reviewer ({a.model}): {said}; ${out['cost']['usd']:.4f}, {out['cost']['calls']} call(s)")
    return 0


def _said(got: dict) -> None:
    """One call's cost, printed as a Claude Code result line as it is spent: the engine adds each to the run's
    (``ergostat.cost.*``), so a run the block's timeout cuts short still says what it spent."""
    import json

    from ...numbers import modeller as md
    print(json.dumps(md.result_line({**got, "calls": 1})), flush=True)


def _near(p, reqs: list[dict]) -> list[dict]:
    """The requests in an order that keeps those about one part, or one file, together: one call sees one
    neighbourhood."""
    def key(r):
        about = str(r.get("about") or "")
        return (str(r.get("where") or "").split(":")[0], about.split(".")[0], about, r.get("raised") or 0.0)
    return sorted(reqs, key=key)


def main(argv: list[str]) -> int:
    subs = {"requests": requests, "rules": rules, "ai": ai, "redesign": redesign, "review": review}
    if not argv or argv[0] not in subs:
        print(f"usage: ... modelling {{{','.join(subs)}}} ...", file=sys.stderr)
        return 2
    return subs[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

