"""A throwaway spike for docs/proposals/control-aware-estimates.md, not part of the suites: it runs only when this
file is named on the command line, and writes what it measured to /tmp/control-spike-*.json (the proposal's tables).

    uv run python scripts/named_tests.py tests/test_control_spike.py

1. the cost of working out the factory's control structure (its own model, ergostat.yaml at the root) through
   ``closedloop.Shadow`` once per simulated event, and of its two take gates alone, against the events a run of the
   completion estimates makes on the factory-size record (scripts/factory_fixture.py);
2. the backtest of three ways to run a gate with the items, on the gated synthetic record (tests/eta_synthetic.py)."""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.numbers import eta, etamodel
from ergostat.numbers.closedloop import Shadow
from ergostat.numbers.etamodel import read
from ergostat.spec.blocks import compile_expr, eval_expr

from .eta_synthetic import GATED_BATCH, gated_record

pytestmark = pytest.mark.slow
ROOT, OUT, N = Path(__file__).resolve().parent.parent, Path("/tmp"), 5000


@pytest.fixture(autouse=True)
def _named_only(request):
    """Run only when this file is named on the command line (never in a whole-suite run)."""
    if not any(Path(__file__).name in str(a) for a in request.config.args):
        pytest.skip("a spike: run it by naming tests/test_control_spike.py")


def _said(name: str, got: dict) -> None:
    """Written to /tmp/control-spike-NAME.json, and said in the run's warnings summary."""
    (OUT / f"control-spike-{name}.json").write_text(json.dumps(got, indent=1))
    warnings.warn(f"control-spike {name}: {json.dumps(got)}", stacklevel=2)


class Counted(eta._Run):
    events = 0

    def push(self, t, *ev):
        Counted.events += 1
        super().push(t, *ev)


def test_gate_cost_per_event(factory_state, monkeypatch):
    spec = mdl.load(ROOT).spec
    sig = {f"{k}.{n}": 1.0 for k, t in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries))
           for n in t}
    sig.update({"stock.implementor-pool": 36.0, "stock.reviewer-pool": 6.0, "auxiliary.session-headroom": 4.0,
                "auxiliary.intake-open": 1.0, "stock.gaps-ready": 97.0})
    sh = Shadow(spec, sig)
    t0 = time.perf_counter()
    for k in range(N):                                   # an event: the counts the gates read move, then one pass
        sig["stock.gaps-building"] = float(k % 9)
        sig["stock.gaps-ready"] = float(97 - k % 9)
        sh.step(1_800_000_000.0 + 60 * k)
    whole = (time.perf_counter() - t0) / N
    gates = {n: (compile_expr(str(spec.blocks[n].params["expr"])), list(spec.blocks[n].inputs)) for n in
             ("implement-when", "review-when")}
    t0 = time.perf_counter()
    for k in range(N):
        for tree, ports in gates.values():
            eval_expr(tree, {**{p: 0.0 for p in ports}, "busy": float(k % 9), "pool": 36.0, "room": 4.0, "open": 1.0})
    alone = (time.perf_counter() - t0) / N
    p = factory_state.project()                          # the events of one estimate on the factory-size record
    kinds = sorted(k for k in p.model.spec.items if not k.startswith("ergostat."))
    inp = read(p, p.model.spec, kinds, factory_state.stats["end"])
    monkeypatch.setattr(eta, "_Run", Counted)
    t0 = time.perf_counter()
    got = eta.simulate(inp, runs=200, budget=120)
    took = time.perf_counter() - t0
    runs = got["runs"]
    per_run = Counted.events / (runs + 1)                # (and the levelled run drawn again)
    said = {"shadow_pass_us": round(whole * 1e6, 1), "two_gates_us": round(alone * 1e6, 2),
            "goals": len(spec.goals), "builtins": len(sh.builtins), "open_items": len(inp.items),
            "blocks": len(inp.blocks), "runs": runs, "simulate_s": round(took, 2), "events_per_run": round(per_run),
            "added_s_shadow_per_event": round(whole * per_run * runs, 2),
            "added_s_gates_per_event": round(alone * per_run * runs, 3)}
    _said("cost", said)
    assert runs and per_run > 0, said


def _coupled(gates: dict):
    """A run whose blocks also take only while their gate, worked out on the run's own count of runs going, is open."""
    trees = {b: compile_expr(x) for b, x in gates.items()}

    class Coupled(eta._Run):
        def room(self, b):
            tr = trees.get(self.blocks[b].name)
            return super().room(b) and (tr is None or bool(eval_expr(tr, {"busy": float(self.busy[b])})))
    return Coupled


def _available(share: dict, put_off: dict):
    """A run whose takes are each admitted with the block's recorded share (stationary availability); one refused is
    put off as the record's refusals were."""
    class Available(eta._Run):
        def hold(self, b, i, t, a):
            name = self.blocks[b].name
            if self.loading or name not in share or self.rnd.random() < share[name]:
                return super().hold(b, i, t, a)
            it = self.items[i]
            it[4] += 1
            self.push(t + put_off[name], "free", i, it[4])
    return Available


def _score(inp, end: float) -> dict:
    got = eta.simulate(inp, runs=60, budget=6)["items"]
    errs, cov, n, pred = [], 0, 0, 0
    day = inp.at + 86400
    for i, x in got.items():
        done = inp.finished_at.get(i)
        pred += x["p50"] is not None and x["p50"] <= day
        if done is None:
            n += x["p90"] is not None and x["p90"] < end
            continue
        n += 1
        cov += x["p90"] is not None and done <= x["p90"]
        if x["p50"] is not None:
            errs.append(abs(x["p50"] - done))
    actual = sum(1 for i in got if (inp.finished_at.get(i) or float("inf")) <= day)
    return {"mae_min": sum(errs) / len(errs) / 60 if errs else None, "coverage": cov / n if n else None,
            "next24_pred": pred, "next24_actual": actual}


def test_coupling_backtest(tmp_path, monkeypatch):
    rows: dict[str, list] = {}
    for seed in range(3):
        p = gated_record(tmp_path / str(seed), seed)
        t0 = 1_790_000_000.0 + GATED_BATCH
        end = p.events.query(n=1)[0]["time"]
        for h in (0.25, 2, 4):
            at = t0 + h * 3600
            for name, run, measured, min_run in (("pool only", eta._Run, 0.0, 0.0),
                                                 ("measured concurrency (main)", eta._Run, 0.9, 30.0),
                                                 ("two-way coupling: gate busy < 4", _coupled({"dev": "busy < 4"}), 0.0, 30.0),
                                                 ("stationary availability", None, 0.0, 30.0)):
                with monkeypatch.context() as m:
                    m.setattr(etamodel, "MEASURED", measured)
                    m.setattr(etamodel, "MIN_RUN", min_run)
                    inp = read(p, p.model.spec, ["ticket"], at, truth=True)
                    if run is None:
                        dev = next(b for b in inp.blocks if b.name == "dev")
                        share = len(dev.attempts) / (len(dev.attempts) + len(dev.refusals))
                        off = sorted(dev.refusals)[len(dev.refusals) // 2] if dev.refusals else 300.0
                        run = _available({"dev": share}, {"dev": off})
                    m.setattr(eta, "_Run", run)
                    rows.setdefault(name, []).append(_score(inp, end))
    mean = {k: {f: round(sum(r[f] for r in v) / len(v), 2) for f in v[0]} for k, v in rows.items()}
    _said("backtest", {"mean": mean, "rows": rows})
    assert all(len(v) == 9 for v in rows.values()), mean
