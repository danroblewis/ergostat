"""The craft and chain recovery benchmark: a good model (an example's, as
written) damaged in the ways ``check`` says as craft notes and chain findings, and the modelling subsystem's tiers run on
it, as the template runs them: the requests raised (``numbers/requests.py``), the rule tier (``numbers/rules.py``) and,
with ``--improver ai``, the AI tier (``numbers/modeller.py``), each proposal checked as a block's is, the judge with the
test policy (a description, a unit and an equation written when it passes), and the owner simulated, accepting the
rule tier's changes to the structure, the event names, the goals and its first-order equations that still wait at the
end of each round (said apart from what the judge wrote); what the AI tier makes is written by the judge or not at all.

Each defect says how it is planted (lines of a file replaced), the finding it should raise (``code@about``) and what
counts as repaired (the part as the good model has it: its unit, a target restored, an equation, an event name of the
kind's form, a goal's tolerance 0, a description). Scores per defect: **visible** (check raised its finding), **asked**
(a request held it), **proposed** (a change cited it), **fixed** (the model left says it as the good one does); and per
case **damage** (findings or errors the model left has that the good one does not), proposals by tier and the cost.

    uv run python scripts/craft_bench.py [--improver rules|ai] [--model haiku] [--out DIR] [--keep] [case ...]"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY = {"description": "auto", "unit": "auto", "equation": "auto"}
OWNER = ("structure", "rename", "control", "equation")   # the rule tier's, the owner (simulated) accepts: the guide's own
# fixes; an equation the rule tier writes is a first-order outflow, which the judge cannot test with no record here


@dataclass
class Defect:
    kind: str                  # unit-removed, equation-removed, chain-broken, event-misnamed, tolerance-added, ...
    file: str
    old: str
    new: str
    finding: str               # code@about check should raise
    repaired: object           # (spec, root) -> bool
    says: str = ""


@dataclass
class Case:
    id: str
    example: str
    defects: list[Defect] = field(default_factory=list)


def _stock_unit(name: str, unit: str):
    return lambda spec, root: (spec.stocks.get(name) is not None and spec.stocks[name].unit == unit)


def _has_equation(name: str):
    return lambda spec, root: spec.flows.get(name) is not None and spec.flows[name].equation is not None


def _target(name: str, to: str):
    return lambda spec, root: spec.flows.get(name) is not None and spec.flows[name].target == to


def _event_form(kind: str):
    from ergostat.spec import craft
    return lambda spec, root: kind in spec.items and not craft.event_forms(spec, kind)


def _tolerance(goal: str):
    return lambda spec, root: goal in spec.goals and spec.goals[goal].tolerance == 0


def _described(ref: str, sensor: str | None = None):
    def ok(spec, root):
        kind, _, name = ref.partition(".")
        x = {"stock": spec.stocks, "flow": spec.flows, "goal": spec.goals, "block": spec.blocks}[kind].get(name)
        if x is None:
            return False
        if sensor:
            s = x.sensors.get(sensor)
            return bool(s and (s.description or "").strip())
        return bool((x.description or "").strip())
    return ok


A = "model/alerts.yaml"
CASES = [
    Case("alert-triage-craft", "alert-triage", [
        Defect("unit-removed", A, "  alerts-escalated:\n    unit: alerts\n", "  alerts-escalated:\n",
               "no-unit@stock.alerts-escalated", _stock_unit("alerts-escalated", "alerts"), "a stock's unit taken away"),
        Defect("equation-removed", A, "    equation: stock.alerts-triaged / fan-out-time\n", "",
               "no-equation@flow.facets-opened-for", _has_equation("facets-opened-for"), "a flow's equation taken away"),
        Defect("chain-broken", A, "  alerts-escalated:\n    from: alerts-summarising\n    to: alerts-escalated\n",
               "  alerts-escalated:\n    from: alerts-summarising\n", "outflow-not-chained@flow.alerts-escalated",
               _target("alerts-escalated", "alerts-escalated"), "a flow between two state stocks made an outflow to a cloud"),
        Defect("event-misnamed", A, "      alert.triaged: triaged\n", "      triage.finished: triaged\n",
               "event-names-mixed@items.alert", _event_form("alert"), "an event type of another form"),
        Defect("description-removed", A, "    description: every facet done, the summary not written yet\n", "",
               "no-description@stock.alerts-summarising", _described("stock.alerts-summarising"), "a description taken away"),
        Defect("collector-undescribed", A,
               "      description: the pager collector                # (40 characters at most: the Blocks view titles "
               "the collector with it)\n",
               "", "collector-undescribed@flow.alerts-fired", _described("flow.alerts-fired", "main"),
               "a collector's description taken away"),
    ]),
    Case("ticket-factory-chain", "ticket-factory", []),       # filled in by _ticket() from the example as it is
    Case("thirteen-stocks", "thirteen-stocks", []),           # the owner's case: a workflow's stocks each to a cloud
]


def thirteen(dest: Path) -> list[Defect]:
    """A model shaped like the owner's 13 disconnected stocks: one kind through 13 states, a stock a state, every move
    written as an outflow to a cloud, a goal and a block a step; written here, with no defect planted (it is all one)."""
    states = [f"s{i:02d}" for i in range(1, 14)]
    lines = ["name: thirteen", "items:", "  request:", "    id: request/*", "    description: a request worked through 13 steps",
             f"    states: [{', '.join(states)}, done]", "    on:"]
    lines += [f"      request.{s}-reached: {s}" for s in states] + ["      request.finished: done"]
    lines += ["stocks:"]
    for s in states:
        lines += [f"  {s}-waiting:", "    unit: requests", f"    description: requests at step {s}",
                  f"    sensor: {{items: request, state: {s}, every: 5s}}"]
    lines += ["flows:", "  arrivals:", "    to: s01-waiting", "    description: requests arriving",
              "    sensor: {items: request, entering: s01, over: 10m}"]
    for i, s in enumerate(states):
        nxt = states[i + 1] if i + 1 < len(states) else "done"
        lines += [f"  {s}-worked:", f"    from: {s}-waiting", f"    description: requests leaving step {s}",
                  f"    driven-by: +stock.{s}-waiting", f"    sensor: {{items: request, entering: {nxt}, over: 10m}}"]
    lines += ["goals:"]
    for s in states:
        lines += [f"  {s}-clear:", f"    stock: {s}-waiting", '    hold: "<= 0"', f"    description: nothing waits at {s}"]
    lines += ["blocks:"]
    for i, s in enumerate(states):
        nxt = states[i + 1] if i + 1 < len(states) else "done"
        lines += [f"  step-{s}:", "    type: program", f"    description: works step {s}", f"    goal: {s}-clear",
                  "    run: python3 -c pass", f"    takes: {{kind: request, at: {s}, to: [{nxt}]}}", f"    out: flow.{s}-worked"]
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "ergostat.yaml").write_text("\n".join(lines) + "\n\nuses:\n  modelling: {use: modelling}\n", encoding="utf-8")

    def chained(spec, root):
        return all(spec.flows[f"{s}-worked"].target == (f"{states[i + 1]}-waiting" if i + 1 < len(states) else None)
                   for i, s in enumerate(states))
    return [Defect("state-stocks-disconnected", "ergostat.yaml", "", "", "state-stocks-disconnected@stock.s01-waiting",
                   chained, "13 state stocks, each move an outflow to a cloud")]


def _ticket(dest: Path) -> list[Defect]:
    t = "factory/flows.yaml" if (dest / "factory" / "flows.yaml").is_file() else None
    out = []
    for f in sorted(dest.rglob("*.yaml")):
        text = f.read_text(encoding="utf-8")
        m = re.search(r"^  (?P<flow>[a-z-]+):\n    from: (?P<a>[a-z-]+)\n    to: (?P<b>[a-z-]+)\n", text, re.M)
        if m and "flows:" in text:
            rel = str(f.relative_to(dest))
            out.append(Defect("chain-broken", rel, m.group(0), f"  {m.group('flow')}:\n    from: {m.group('a')}\n",
                              f"outflow-not-chained@flow.{m.group('flow')}", _target(m.group("flow"), m.group("b")),
                              "a move between two state stocks made an outflow to a cloud"))
            break
    _ = t
    return out


def prepare(case: Case, work: Path) -> tuple[Path, list[Defect]]:
    dest = work / case.id
    if dest.exists():
        shutil.rmtree(dest)
    if case.id == "thirteen-stocks":
        return dest, thirteen(dest)
    shutil.copytree(ROOT / "examples" / case.example, dest, ignore=shutil.ignore_patterns(".ergostat", "__pycache__", "poor"))
    defects = case.defects or (_ticket(dest) if case.example == "ticket-factory" else [])
    for d in defects:
        f = dest / d.file
        text = f.read_text(encoding="utf-8")
        if d.old not in text:
            raise ValueError(f"{case.id}: {d.kind}: the lines to replace are not in {d.file}")
        f.write_text(text.replace(d.old, d.new, 1), encoding="utf-8")
    return dest, defects


def findings_of(root: Path) -> set[str]:
    from ergostat import model as mdl
    from ergostat.spec import read
    _, ps = read(mdl.find(root))
    return {f"{x.level}:{x.code}@{x.about}" for x in ps}


def run(case: Case, work: Path, improver: str = "rules", model: str = "haiku", rounds: int = 4, approve: bool = True) -> dict:
    from ergostat import model as mdl
    from ergostat.numbers import improve as im
    from ergostat.numbers import judge as jd
    from ergostat.numbers import modeller as md
    from ergostat.numbers import observe as ob
    from ergostat.numbers import proposals as pr
    from ergostat.numbers import requests as rq
    from ergostat.numbers import rules as ru
    from ergostat.store import Project
    t0 = time.perf_counter()
    good = None
    if case.id != "thirteen-stocks":
        gdir = work / f"{case.id}-good"
        if gdir.exists():
            shutil.rmtree(gdir)
        shutil.copytree(ROOT / "examples" / case.example, gdir, ignore=shutil.ignore_patterns(".ergostat", "__pycache__", "poor"))
        good = findings_of(gdir)
    root, defects = prepare(case, work)
    planted = findings_of(root)
    state = work / f"{case.id}-state"
    if state.exists():
        shutil.rmtree(state)
    state.mkdir(parents=True)
    p = Project(mdl.load(root), directory=state)
    cost = {"usd": 0.0, "calls": 0, "tokens_in": 0, "tokens_out": 0}
    made, judged, owner = [], [], []
    for _ in range(rounds):
        p.model = mdl.load(root)
        rq.sync(p, coherence=False)
        mine = [r for r in rq.current(p, ("open",)) if r.get("tier") == "rule"]
        props, none = ru.propose(p, mine, most=20)
        for r, why in none:
            rq.mark(p, r, "held", f"the rule tier has no certain change for it: {why}", tier="ai")
        for r, raw in props:
            got = im.submit(p, "fixer", raw)
            made.append({"tier": "rule", "request": f"{r['code']}@{r['about']}", "kind": raw.get("kind"),
                         "status": got["status"], "why": got.get("why")})
        if improver == "ai":
            waiting = [r for r in rq.current(p, ("open", "held")) if r.get("tier") == "ai"
                       and int((r.get("tried") or {}).get("ai") or 0) < 2]
            for i in range(0, len(waiting), md.MOST):
                group = waiting[i:i + md.MOST]
                got = md.answer(p, group, model)
                for k in cost:
                    cost[k] = round(cost[k] + got["cost"].get(k, 0), 6)
                for r in group:
                    rq.event(p, r["id"], r["state"], {"tried": {"ai": int((r.get("tried") or {}).get("ai") or 0) + 1}})
                for raw in got["proposals"]:
                    g = im.submit(p, "modeller", raw)
                    made.append({"tier": "ai", "request": None, "kind": raw.get("kind"), "status": g["status"],
                                 "why": g.get("why"), "title": raw.get("title")})
        pol = p.model.spec.improve
        pol.accept.update(POLICY)
        j = jd.run(p)
        judged += j["verdicts"]
        p.model = mdl.load(root)
        if approve:
            tried: set[str] = set()
            while True:                                   # one at a time: each written changes what the rest stand on
                xs = [x for x in sorted(pr.pending(p), key=lambda x: x.get("created") or 0)
                      if x.get("made_by") == "fixer" and x.get("kind") in OWNER and not jd.removes(x) and x["id"] not in tried]
                if not xs:
                    break
                x = xs[0]
                tried.add(x["id"])
                try:
                    g = ob.reference(p)
                    pr.accept(p, x["id"], {"at": time.time(), "window": g.until - g.since}, by="owner")
                    owner.append({"kind": x.get("kind"), "title": x.get("title")})
                    p.model = mdl.load(root)
                except Exception as e:
                    owner.append({"kind": x.get("kind"), "title": x.get("title"), "not": str(e)[:200]})
    p.model = mdl.load(root)
    rq.sync(p, coherence=False)
    after = findings_of(root)
    spec = p.model.spec
    reqs = rq.stored(p)
    changes = pr.changes(p)
    cited = {e for _, (st, f) in changes.items() for r in f.get("reasons") or []
             for e in ([r.get("evidence")] if not isinstance(r.get("evidence"), list) else r.get("evidence")) if isinstance(e, str)}
    out = []
    for d in defects:
        code, _, about = d.finding.partition("@")
        out.append({"kind": d.kind, "says": d.says, "finding": d.finding,
                    "visible": any(x.split(":", 1)[1] == d.finding for x in planted),
                    "asked": any(r.get("code") == code and r.get("about") == about for r in reqs.values()),
                    "proposed": f"finding:{d.finding}" in cited, "fixed": bool(d.repaired(spec, root))})
    damage = sorted(x for x in after if (good is None or x not in good) and x not in planted
                    and not x.startswith("finding:template-stand-in") and x.split(":")[0] in ("error", "finding"))
    accepted = [{**f, "state": st} for _, (st, f) in changes.items() if st in ("accepted", "verified", "regressed")]
    return {"case": case.id, "defects": out, "made": made, "verdicts": [v["verdict"] for v in judged],
            "written_by_judge": sum(1 for x in accepted if (x.get("by") or "").startswith("judge")),
            "written_by_owner": len([o for o in owner if "not" not in o]), "owner": owner, "damage": damage,
            "cost": {**cost, "seconds": round(time.perf_counter() - t0, 1), "improver": improver,
                     "model": model if improver == "ai" else None}}


def markdown(results: list[dict]) -> str:
    rows = ["| Case | Defect | Visible | Asked | Proposed | Fixed |", "|---|---|---|---|---|---|"]
    for r in results:
        for d in r["defects"]:
            rows.append(f"| {r['case']} | {d['kind']} | {'yes' if d['visible'] else 'no'} | {'yes' if d['asked'] else 'no'} | "
                        f"{'yes' if d['proposed'] else 'no'} | {'yes' if d['fixed'] else 'no'} |")
    vis = [d for r in results for d in r["defects"] if d["visible"]]
    rows += ["", f"Recall: {sum(d['fixed'] for d in vis)}/{len(vis)} visible defects fixed. Damage: "
             + "; ".join(f"{r['case']} {len(r['damage'])}" for r in results) + ". Written by the judge: "
             + ", ".join(f"{r['case']} {r['written_by_judge']}" for r in results) + "; by the owner (simulated): "
             + ", ".join(f"{r['case']} {r['written_by_owner']}" for r in results) + ". Cost: "
             + ", ".join(f"{r['case']} ${r['cost']['usd']:.4f} in {r['cost']['seconds']}s" for r in results) + "."]
    return "\n".join(rows) + "\n"


def bench(work: Path, out: Path, improver: str = "rules", model: str = "haiku", cases: list[str] | None = None) -> list[dict]:
    results = []
    for c in CASES:
        if cases and c.id not in cases:
            continue
        results.append(run(c, work, improver, model))
    out.mkdir(parents=True, exist_ok=True)
    (out / "craft.json").write_text(json.dumps(results, indent=1, default=str))
    (out / "craft.md").write_text(markdown(results))
    return results


def main() -> int:
    import argparse
    import tempfile
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="*", help=f"by id (default: all): {', '.join(c.id for c in CASES)}")
    ap.add_argument("--improver", choices=["rules", "ai"], default="rules", help="the rule tier alone, or with the ai tier")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--out", default="bench-craft")
    ap.add_argument("--keep", action="store_true", help="keep each case's model and record under OUT/work")
    a = ap.parse_args()
    out = Path(a.out)
    work = out / "work" if a.keep else Path(tempfile.mkdtemp(prefix="ergostat-bench-craft-"))
    bench(work, out, a.improver, a.model, a.cases or None)
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    print((out / "craft.md").read_text())
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
