"""The redesign benchmark (SPEC §12e, *Redesign*; docs/redesign-bench.md): models of known structure, each with a piece
cut out, the record made from the whole model, and the redesigner asked to repair the cut one. Scored per case: the
missing structure found again (by its place in the model, never by the names chosen; a renamed stock followed by its
``formerly:``), the fit before and after (the scorecard's), whether its change set compiled, the verdict, and the cost.

    uv run python scripts/redesign_bench.py [--cases capacity,rework] [--model haiku] [--cap 3] [--stand-in]

The cases are ``tests/redesign_cases/cases.json``: a truth (a file there, or ``bench:ID``, a recovery-benchmark case),
the cut (a defect from ``bench/defects.py``, or ``{"set": "flows.NAME", "with": {...}}``), what the repair must have
(``expect``), the stand-in's answer, and a seed: past redesigns and interventions written to the record first, the
same for every run. ``--stand-in`` answers each case with its known repair and no AI (CI checks the harness with
it). A table is printed, and one JSON row per case appended to the results file, so runs can be compared."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ergostat.bench import defects as df
from ergostat.bench import form as fm
from ergostat.bench import recovery as rc
from ergostat.bench import truth as tt
from ergostat.numbers import changeset as cs
from ergostat.numbers import redesigner as rdr
from ergostat.numbers import scorecard as sc

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tests" / "redesign_cases"
RESULTS = ROOT / "docs" / "redesign-bench.jsonl"
HOURS = 12.0
DELAYS = ("DELAY1(", "DELAY3(", "DELAYN(", "SMOOTH(", "SMOOTH3(")


def cases(names: list[str] | None = None) -> list[tuple[tt.Case, dict]]:
    reg = json.loads((CASES / "cases.json").read_text())
    bench = tt.cases()
    out = []
    for k, v in reg.items():
        if names and k not in names:
            continue
        if v["truth"].startswith("bench:"):
            b = bench[v["truth"][6:]]
            c = tt.Case(k, v["title"], b.source, str(b.path), b.inputs, b.start, [])
        else:
            c = tt.Case(k, v["title"], "tests/redesign_cases", str(CASES / v["truth"]), v["inputs"], v["start"], [])
        out.append((c, v))
    if names and len(out) != len(names):
        raise SystemExit(f"no such case among: {', '.join(reg)}")
    return out


def cut(c: tt.Case, v: dict) -> dict:
    """The truth with its piece cut out, as plain data (``bench/form.py``)."""
    truth = c.form()
    m = fm.copy_of(truth)
    for op in v["cut"]:
        if "kind" in op:
            df.plant(m, truth, op)
        else:
            sec, name = op["set"].split(".", 1)
            m[sec][name].update(op["with"])
    fm.drop_unused(m)
    return m


# ---- what the repair must have, by structure

def found(spec, expect: dict, truth_stocks) -> bool:
    """Whether ``spec`` has the structure ``expect`` names, its stocks taken as the truth's by name or ``formerly:``."""
    def was(s):
        if s is None:
            return None
        if s in truth_stocks:
            return s
        st = spec.stocks.get(s)
        return next((f for f in (getattr(st, "formerly", None) or []) if f in truth_stocks), "new:" + s)
    flows = [(was(f.source), was(f.target), f.equation.text if f.equation else "") for f in spec.flows.values()]
    k, x = next(iter(expect.items()))
    if k == "flow":                                 # a flow between these two (null: outside)
        return any(a == x[0] and b == x[1] for a, b, _ in flows)
    if k == "limit":                                # the outflow of a stock limited (a capacity)
        return any(a == x and "MIN(" in e.upper() for a, _, e in flows)
    if k == "names":                                # a flow into x[0] whose equation reads stock x[1]
        return any(b == x[0] and x[1] in {was(r) for r in re.findall(r"stock\.([\w-]+)", e)} for _, b, e in flows)
    if k == "between":                              # a delay into x[1], or a stock between x[0] and x[1]
        if any(b == x[1] and any(d in e.upper() for d in DELAYS) for _, b, e in flows):
            return True
        mids = {b for a, b, _ in flows if a == x[0] and b not in (None, *x)}
        return any(a in mids and b == x[1] for a, b, _ in flows)
    raise ValueError(f"no expectation {k}")


# ---- the record's seed: past redesigns and interventions

def seed(p, spec, s: dict) -> None:
    from ergostat.inbox import interventions as iv
    from ergostat.numbers import proposals as pr
    for i, h in enumerate(s.get("history") or []):
        pid = f"bench-history-{i}"
        pr.event(p, pid, "made", {"kind": "redesign", "system": "model", "title": h["title"], "summary": h["summary"],
                                  "made_by": "redesigner", "redesign": {"edits": [{"said": e, "why": ""} for e in h["edits"]]}},
                 source="redesigner")
        pr.event(p, pid, "checked", {"scorecard": {"verdict": "no better" if h.get("verdict") else "better",
                                                   "why": h.get("verdict") or ""}})
        if h["state"] == "dismissed":
            pr.event(p, pid, "dismissed", {"dismissed_because": h["note"], "dismissed_by": "owner"}, source="owner")
        else:
            pr.event(p, pid, "testing", {})
            pr.event(p, pid, h["state"], {"verdict": {"verdict": h["state"], "why": h.get("verdict") or ""}})
    for x in s.get("interventions") or []:
        item = iv.request_id(x["class"])
        p.events.add(f"{iv.MODEL_REQUEST}.opened", item=item, source="ergostat",
                     data={"class": x["class"], "cause": x["cause"], "count": x["count"], "hours": x.get("hours"),
                           "remedies": iv.remedies(spec, x["class"], None), "why": "it recurs"})
        if x.get("note"):
            p.events.add(f"{iv.MODEL_REQUEST}.investing", item=item, source="owner", data={"note": x["note"]})


# ---- one case

def stand_in(v: dict):
    """The case's known repair, said once (then nothing more to do), at no cost."""
    said = []

    def call(text, model, timeout=None):
        edits = [] if said else v["stand_in"]
        said.append(1)
        return {"result": json.dumps({"redesign": {"title": "the stand-in's repair", "system": "model",
                                                   "summary": "the known repair", "edits": edits}}),
                "usd": 0.0, "tokens_in": len(text) // 3, "tokens_out": 100, "seconds": 0.0}
    return call


def run_case(c: tt.Case, v: dict, work: Path, model: str = "haiku", budget: float = 0.5, rounds: int = 3,
             call=None, hours: float = HOURS) -> dict:
    s = rc.prepare(c, work / c.id, rounds=0, train_h=hours, round_h=1.0, forecast_h=0.0, damaged=cut(c, v))
    seed(s.p, s.p.model.spec, v.get("seed") or {})
    truth = c.spec()
    t0 = time.perf_counter()
    out = rdr.run(s.p, "model", ["the owner asked"], model=model, budget=budget, rounds=rounds, by="redesign-bench",
                  submit=False, call=call)
    after = None
    if out.get("change_set"):
        scratch = cs.Scratch(s.p)
        for e in out["change_set"]["edits"]:
            scratch.apply(e)
        scratch.keep_names()
        after, _ = scratch.compiled()
    card = out.get("scorecard") or {}
    total = lambda sp: ((sc.fit(s.p, sp).get("total") or {}).get("nmse"))    # noqa: E731
    fb = (card.get("fit") or {}).get("total_before") if card else total(s.p.model.spec)
    fa = (card.get("fit") or {}).get("total_after") if card else None
    return {"case": c.id, "found": bool(after is not None and found(after, v["expect"], truth.stocks)),
            "compiles": after is not None, "verdict": card.get("verdict"), "title": (out.get("change_set") or {}).get("title"),
            "fit_before": fb, "fit_after": fa, "fit_truth": total(truth),
            "fit_improved": bool(fb is not None and fa is not None and fa < fb), "cost": out["cost"],
            "rounds": len(out["rounds"]), "prompt_chars": max((r.get("prompt_chars") or 0 for r in out["rounds"]), default=0),
            "seconds": round(time.perf_counter() - t0, 1), "result": out.get("result") or "made"}


# ---- the run

def commit() -> str:
    def git(*a):
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return git("rev-parse", "--short", "HEAD") + ("-dirty" if git("status", "--porcelain", "--untracked-files=no") else "")


def bench(names=None, model="haiku", cap=3.0, budget=0.5, rounds=3, use_stand_in=False, repeat=1, hours=HOURS,
          work: Path | None = None, label: str = "") -> list[dict]:
    work = work or Path(tempfile.mkdtemp(prefix="ergostat-redesign-bench-"))
    rows, spent = [], 0.0
    head = {"label": label, "commit": commit(), "at": round(time.time()), "model": "stand-in" if use_stand_in else model,
            "rounds_max": rounds, "budget": budget, "cap": cap, "hours": hours}
    for i in range(repeat):
        for c, v in cases(names):
            left = cap - spent
            if left <= 0.0:
                rows.append({**head, "case": c.id, "skipped": f"the cap (${cap:.2f}) is spent"})
                continue
            row = run_case(c, v, work / f"r{i}", model, min(budget, left), rounds, stand_in(v) if use_stand_in else None, hours)
            spent += float(row["cost"].get("usd") or 0.0)
            rows.append({**head, **row})
    return rows


def table(rows: list[dict]) -> str:
    def f(x):
        return "-" if x is None else f"{x:.3g}"
    out = ["| case | found | compiles | verdict | fit before → after (truth) | $ | calls | s |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("skipped"):
            out.append(f"| {r['case']} | {r['skipped']} |||||||")
            continue
        out.append(f"| {r['case']} | {'yes' if r['found'] else 'no'} | {'yes' if r['compiles'] else 'no'} | {r['verdict'] or '-'} | "
                   f"{f(r['fit_before'])} → {f(r['fit_after'])} ({f(r['fit_truth'])}) | {r['cost']['usd']:.3f} | "
                   f"{r['cost']['calls']} | {r['seconds']:.0f} |")
    done = [r for r in rows if not r.get("skipped")]
    out.append(f"\nfound {sum(r['found'] for r in done)}/{len(done)}, compiled {sum(r['compiles'] for r in done)}/{len(done)}, "
               f"fit improved {sum(r['fit_improved'] for r in done)}/{len(done)}, "
               f"${sum(r['cost']['usd'] for r in done):.3f} in {sum(r['cost']['calls'] for r in done)} calls")
    return "\n".join(out)


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--cases", help="comma-separated case names (default: all)")
    a.add_argument("--model", default="haiku")
    a.add_argument("--cap", type=float, default=3.0, help="dollars for the whole run: no case starts once spent")
    a.add_argument("--budget", type=float, default=rdr.BUDGET, help="dollars a case at most (the redesigner's budget)")
    a.add_argument("--rounds", type=int, default=rdr.ROUNDS)
    a.add_argument("--repeat", type=int, default=1, help="run every case this many times")
    a.add_argument("--hours", type=float, default=HOURS, help="hours of record made from the whole model")
    a.add_argument("--stand-in", action="store_true", help="the known repair as the answer, no AI: checks the harness")
    a.add_argument("--label", default="", help="what this run is (kept on its rows)")
    a.add_argument("--results", default=str(RESULTS), help="the JSON-lines file the rows are appended to ('-': none)")
    a.add_argument("--work", help="where the cases' models and records are made (default: a new temporary folder)")
    x = a.parse_args(argv)
    rows = bench(x.cases.split(",") if x.cases else None, x.model, x.cap, x.budget, x.rounds, x.stand_in, x.repeat,
                 x.hours, Path(x.work) if x.work else None, x.label)
    print(table(rows))
    if x.results != "-":
        with open(x.results, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, default=str) + "\n")
        print(f"{len(rows)} rows appended to {x.results}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
