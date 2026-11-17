"""Convert SD Lab's ladder cases (``~/orchestra/sdlab/sdlab/ladder/cases``) into the recovery benchmark's truth
cases (``ergostat/bench/cases``): each an ergostat model with equations (``<id>.yaml``) and what it needs to be
simulated (its entry in ``cases.json``: the inputs' schedules, where each stock starts).

The ladder's format: ``stocks: {A: 0, H: 0 hidden}``, flows ``outside -> A: 20`` and ``A -> B as name: 0.5 * A``,
``delay3(expr, T)``, ``schedule: {every: N, at T label: {outside -> A: v}}``
and ``injections``. Only cases whose
rates are affine in the stocks (or a DELAY3 of one) are converted; a DELAY3 between two stocks is written as what
leaves the first at once and what arrives in the second through the delay (two flows: the material in transit is in
the delay, as SD writes a material delay), since a delayed rate taken from the first stock would drain it late;
each rate is written as its affine
form, every
number a parameter (``a-to-b-per-a``), so a defect and a fix are changes to named parameters and terms. A step is
three minutes (rates per step are multiplied by 20 to be per hour). A constant outside inflow is an input, measured;
a case with no schedule has one added (the first input doubles every 100 steps), so the record is excited, as
SD Lab's stepping variants are; injections are pulses on the stock's input.

    uv run python scripts/bench_ladder.py [CASE ...]      (default: the cases the benchmark uses)

Run it again only to refresh the converted files; the benchmark reads only ``ergostat/bench/cases``."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

LADDER = Path.home() / "orchestra/sdlab/sdlab/ladder/cases"
OUT = Path(__file__).resolve().parent.parent / "ergostat/bench/cases"
STEP_H = 3 / 60                       # a ladder step is three minutes
USED = ["002-inflow-outflow", "003-chain-2", "004-chain-3", "007-link", "008-link-loop", "011-goal-gap", "012-rework",
        "015-hidden-stock", "020-unannounced-step", "026-hidden-stock-driven", "063-delay3-supply-line"]
FLOW = re.compile(r"^\s*(?P<a>\w+)\s*->\s*(?P<b>\w+)(?:\s+as\s+(?P<name>\w+))?\s*$")
DELAY3 = re.compile(r"^\s*delay3\((?P<x>.*),\s*(?P<t>[\d.]+)\)\s*$")


def name(s: str) -> str:
    return s.lower().replace("_", "-")


def affine(expr: str, stocks: list[str]) -> tuple[float, dict[str, float]]:
    """``expr`` as c0 + Σ c_i X_i, found by evaluating it; refused when it is not affine."""
    code = compile(expr, "<rate>", "eval")

    def at(vals):
        return float(eval(code, {"__builtins__": {}}, vals))      # noqa: S307 (the ladder's own files)
    zero = dict.fromkeys(stocks, 0.0)
    c0 = at(zero)
    cs = {s: at({**zero, s: 1.0}) - c0 for s in stocks}
    probe = {s: 1.7 + i for i, s in enumerate(stocks)}
    if abs(at(probe) - (c0 + sum(cs[s] * probe[s] for s in stocks))) > 1e-9 * max(1.0, abs(at(probe))):
        raise ValueError(f"not affine: {expr}")
    return c0, {s: c for s, c in cs.items() if c}


def convert(path: Path) -> tuple[dict, dict]:
    case = yaml.safe_load(path.read_text())
    cid = path.stem
    raw_stocks = case["stocks"]
    stocks, hidden, start = [], set(), {}
    for s, v in raw_stocks.items():
        stocks.append(s)
        if isinstance(v, str) and "hidden" in v:
            hidden.add(s)
            v = v.split()[0]
        start[name(s)] = float(v)
    m = {"name": f"ladder-{cid.split('-', 1)[0]}", "description": case["title"], "parameters": {},
         "stocks": {name(s): {"unit": "units", "sensor": s not in hidden} for s in stocks}, "flows": {}, "auxiliaries": {}}
    inputs: dict[str, dict] = {}
    keys = {}
    for k, expr in case["flows"].items():
        f = FLOW.match(k)
        a, b = f.group("a"), f.group("b")
        src, dst = (None if a == "outside" else name(a)), (None if b == "outside" else name(b))
        fname = name(f.group("name")) if f.group("name") else \
            (f"{src}-to-{dst}" if src and dst else f"{dst}-in" if dst else f"{src}-out")
        keys[k.replace(" ", "")] = fname
        flow = {"from": src, "to": dst, "driven_by": [], "equation": None, "sensor": False}
        m["flows"][fname] = flow
        text = str(expr)
        dl = DELAY3.match(text)
        if dl:
            text = dl.group("x")
        c0, cs = affine(text, stocks)
        if not cs and not dl:                                  # a constant outside inflow: an input, measured
            flow["sensor"] = True
            inputs[f"flow.{fname}"] = {"base": c0 / STEP_H}
            continue
        ts = []
        if c0:
            p = f"{fname}-base"
            m["parameters"][p] = {"value": abs(c0) / STEP_H, "unit": "units/h", "estimate": True}
            ts.append(("-" if c0 < 0 else "+", p))
        for s, c in cs.items():
            p = f"{fname}-per-{name(s)}"
            m["parameters"][p] = {"value": abs(c) / STEP_H, "unit": "1/h", "estimate": True}
            ts.append(("-" if c < 0 else "+", f"{p} * stock.{name(s)}"))
            flow["driven_by"].append(f"{'-' if c < 0 else '+'}stock.{name(s)}")
        eqn = ("-" if ts[0][0] == "-" else "") + ts[0][1] + "".join(f" {sg} {t}" for sg, t in ts[1:])
        flow["equation"] = eqn
        if dl:                     # what leaves at once, arriving through the delay: two flows, the material in transit
            p = f"{fname}-delay"
            m["parameters"][p] = {"value": float(dl.group("t")) * STEP_H, "unit": "h", "estimate": True}
            leaves, arrives = f"{src or 'outside'}-leaves" if src else fname, f"{dst}-arrives"
            del m["flows"][fname]
            m["flows"][leaves] = {**flow, "to": None}
            m["flows"][arrives] = {"from": None, "to": dst, "driven_by": [f"+flow.{leaves}"],
                                   "equation": f"DELAY3(flow.{leaves}, {p})", "sensor": False}
    sched = case.get("schedule") or {}
    every = sched.get("every")
    for k, v in sched.items():
        if not str(k).startswith("at "):
            continue
        t = float(str(k).split()[1])
        for fk, val in v.items():
            ref = f"flow.{keys[fk.replace(' ', '')]}"
            inputs[ref].setdefault("steps", []).append([(t - 1) * STEP_H, float(val) / STEP_H])
    for x in inputs.values():
        if "steps" in x and every:
            x["every"] = every * STEP_H
    for inj in case.get("injections") or []:
        ref = next((r for r in inputs if m["flows"][r[5:]]["to"] == name(inj["stock"])), None)
        if ref:
            inputs[ref].setdefault("pulses", []).append([inj["t"] * STEP_H, STEP_H, inj["amount"] / STEP_H])
    if inputs and not any("steps" in x or "pulses" in x for x in inputs.values()):
        first = next(iter(inputs.values()))
        first["steps"] = [[0.0, first["base"]], [100 * STEP_H, 2 * first["base"]]]
        first["every"] = 200 * STEP_H
        first["excitation"] = "added: the input doubles every 100 steps"
    meta = {"title": case["title"], "source": f"SD Lab ladder {cid} ({case.get('tests', '')})".strip(),
            "file": f"{cid}.yaml", "inputs": inputs, "start": start, "tags": ["ladder", *case.get("tags", [])]}
    return m, meta


def main(argv: list[str]) -> int:
    from ergostat.bench import form
    want = argv or USED
    reg_path = OUT / "cases.json"
    reg = json.loads(reg_path.read_text()) if reg_path.exists() else {}
    for cid in want:
        m, meta = convert(LADDER / f"{cid}.yaml")
        text = (f"# The truth of SD Lab's ladder case {cid}, converted by scripts/bench_ladder.py: a step is three minutes,\n"
                f"# every number a parameter. {meta['title']}\n") + form.render(m)
        (OUT / meta["file"]).write_text(text)
        old = reg.get(cid, {})
        reg[cid] = {**meta, **{k: old[k] for k in ("defects", "notes") if k in old}}
        print(f"{cid}: {len(m['stocks'])} stocks, {len(m['flows'])} flows, {len(m['parameters'])} parameters")
    reg_path.write_text(json.dumps(dict(sorted(reg.items())), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
