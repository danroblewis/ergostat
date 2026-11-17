"""The truth cases (``cases/``): each an ergostat model with equations, the true one, and in ``cases.json`` what it
needs to be run: its inputs' schedules, where each stock starts, the defects to plant in it, where it came from.

The record is made by simulating the truth: ergostat's own replay (``numbers/simulate.py``) driven only by the
inputs and each stock's start, so every stock is integrated from its flows, hidden ones too. Each measured part (a
sensor in the truth) is read every minute, with measurement noise (Gaussian, a share of the series' own RMS, seeded),
into the project's metrics store under the sensor's series."""

from __future__ import annotations

import json
import math
import random
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..numbers import observe as ob
from ..numbers import simulate as sim
from ..numbers import trial as tr
from ..spec.ir import Spec
from . import form as fm

CASES = Path(__file__).resolve().parent / "cases"
READ_EVERY = 60.0            # seconds between readings
NOISE = 0.02                 # measurement noise: this share of each series' RMS


@dataclass
class Case:
    id: str
    title: str
    source: str
    file: str
    inputs: dict[str, dict]
    start: dict[str, float]
    defects: list[dict]
    tags: list[str] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return CASES / self.file

    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def spec(self) -> Spec:
        return spec_of(self.text())

    def form(self) -> dict:
        return fm.of_spec(self.spec())


def cases() -> dict[str, Case]:
    reg = json.loads((CASES / "cases.json").read_text())
    return {k: Case(k, v["title"], v["source"], v["file"], v.get("inputs") or {}, v.get("start") or {},
                    v.get("defects") or [], v.get("tags") or []) for k, v in reg.items()}


def select(names: list[str] | None) -> list[Case]:
    """By id, a prefix of one (``011``), or a tag (``tag:world``); every case when none is named."""
    every = cases()
    if not names:
        return [c for c in every.values() if "judge" not in c.tags]
    out: list[Case] = []
    for n in names:
        got = [c for c in every.values() if n[4:] in c.tags] if n.startswith("tag:") else \
            [c for k, c in every.items() if k == n or k.startswith(n)]
        if not got:
            raise KeyError(f"no case {n}: {', '.join(every)}")
        out += [c for c in got if c not in out]
    return out


def spec_of(text: str) -> Spec:
    """A model's text compiled, as ergostat reads it from a folder of its own."""
    d = Path(tempfile.mkdtemp(prefix="ergostat-bench-"))
    try:
        (d / "ergostat.yaml").write_text(text, encoding="utf-8")
        spec, problems = tr.compiled(d / "ergostat.yaml", {})          # compiled, without check's findings
        errors = [str(x) for x in problems if x.level == "error"]
        if errors:
            raise ValueError("the model does not compile: " + "; ".join(errors[:3]))
        return spec
    finally:
        shutil.rmtree(d, ignore_errors=True)


def input_value(s: dict, t_h: float) -> float:
    """An input's value ``t_h`` hours in: its step (or base), plus its pulses and its sine; repeating every
    ``every`` hours."""
    t = t_h % s["every"] if s.get("every") else t_h
    v = float(s.get("base") or 0.0)
    for at, x in s.get("steps") or []:
        if t >= at:
            v = x
    for at, width, x in s.get("pulses") or []:
        if at <= t < at + width:
            v += x
    if s.get("sine"):
        amp, period = s["sine"]
        v += amp * math.sin(2 * math.pi * t_h / period)
    return v


@dataclass
class Record:
    """The truth's run: each part's value at every reading (``times``), noise-free; which parts are measured."""

    times: list[float]
    clean: dict[str, list[float]]
    measured: list[str]
    series: dict[str, str]         # a measured part's reference → its sensor's series

    def noisy(self, seed: int, share: float = NOISE) -> dict[str, list[float]]:
        rng = random.Random(seed)
        out = {}
        for ref in self.measured:
            xs = self.clean[ref]
            rms = math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else 0.0
            out[ref] = [x + rng.gauss(0.0, share * rms) for x in xs]
        return out

    def rows(self, seed: int, share: float = NOISE) -> list[tuple[str, float, float]]:
        got = self.noisy(seed, share)
        return [(self.series[r], t, v) for r in self.measured for t, v in zip(self.times, got[r], strict=True)]

    def data(self, since: float, until: float, most: int = 240) -> ob.Data:
        """The noise-free record on a grid of at most ``most`` buckets (a reading each), as ``observe.Data``: what the
        truth did."""
        idx = [i for i, t in enumerate(self.times) if since <= t <= until]
        idx = idx[::max(1, -(-len(idx) // most))]
        d = ob.Data(ob.Grid(since, until, len(idx)))
        for ref, xs in self.clean.items():
            vals = [xs[i] for i in idx]
            d.values[ref] = list(vals)
            if not ref.startswith("flow."):
                d.at[ref] = [self.times[i] for i in idx]
                d.started[ref] = (since, vals[0]) if vals else (since, 0.0)
            d.how[ref] = "the truth"
        return d


def simulate(case: Case, since: float, hours: float, spec: Spec | None = None) -> Record:
    """The truth run from ``since`` for ``hours``, a reading every ``READ_EVERY`` seconds."""
    spec = spec or case.spec()
    n = int(round(hours * 3600.0 / READ_EVERY))
    g = ob.Grid(since, since + hours * 3600.0, n)
    mids = g.times()
    d = ob.Data(g)
    for ref, s in case.inputs.items():
        vals = [input_value(s, (t - since) / 3600.0) for t in mids]
        d.values[ref] = vals
        if not ref.startswith("flow."):
            d.at[ref] = list(mids)
            d.started[ref] = (since, vals[0])
    for name, st in spec.stocks.items():
        v0 = case.start.get(name, st.initial if st.initial is not None else 0.0)
        d.started[f"stock.{name}"] = (since, float(v0))
    run = sim.replay(spec, d)
    if run.invalid:
        raise ValueError(f"{case.id}: the truth's run is not valid: {'; '.join(run.invalid)}")
    clean: dict[str, list[float]] = {}
    for ref, vals in run.values.items():
        clean[ref] = [float(v) if v is not None else 0.0 for v in vals]
    for ref in case.inputs:
        clean[ref] = d.values[ref]
    measured, series = [], {}
    for kind, parts in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
        for name, x in parts.items():
            for s in x.sensors.values():
                ref = f"{kind}.{name}"
                if ref in clean:
                    measured.append(ref)
                    series[ref] = s.series
    for name in spec.stocks:                         # a hidden stock: what the truth did, never read
        clean.setdefault(f"stock.{name}", [d.started[f"stock.{name}"][1]] * n)
    return Record(list(mids), clean, measured, series)


def expressible(m: dict) -> dict:
    """The truth as ergostat can fit it: a hidden stock (no sensor) with one inflow and one outflow first-order in it
    is a first-order delay (DELAY1, its time one over the drain's rate), exactly: what leaves the stock before it
    leaves at once, and arrives in the one after it through the delay. Ergostat's replay never starts a stock it has
    no reading of, so the truth with its hidden stock could not be fitted at all."""
    m = fm.copy_of(m)
    for h, st in list(m["stocks"].items()):
        if st.get("sensor"):
            continue
        ins = [n for n, f in m["flows"].items() if f["to"] == h]
        outs = [n for n, f in m["flows"].items() if f["from"] == h]
        if len(ins) != 1 or len(outs) != 1:
            continue
        fo = m["flows"][outs[0]]
        ts = fm.terms(fo["equation"] or "")
        if len(ts) != 1 or fm.refs_of(ts[0][1]) != {f"stock.{h}"}:
            continue
        k = fm.of_terms([(1, ts[0][1])]).replace(f"stock.{h}", "1")
        fi = m["flows"][ins[0]]
        fi["to"] = None                                # what leaves at once ...
        m["flows"][outs[0]] = {"from": None, "to": fo["to"], "driven_by": [f"+flow.{ins[0]}"],   # ... arrives delayed
                               "equation": f"DELAY1(flow.{ins[0]}, 1 / ({k}))", "sensor": False}
        if fi.get("from") is None:                     # from outside to the hidden stock: the delay is the inflow's
            m["flows"][outs[0]]["equation"] = f"DELAY1({fi['equation']}, 1 / ({k}))"
            m["flows"][outs[0]]["driven_by"] = fi.get("driven_by") or []
            del m["flows"][ins[0]]
        del m["stocks"][h]
    return m
