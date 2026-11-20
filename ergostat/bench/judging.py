"""The judge alone, on changes whose worth is known (docs/MODEL-TOOLS.md, "How we know the improver works").

Synthetic worlds (``cases/judge-*.yaml``) are simulated with measurement noise; the model as written is the truth
with one number off (by a factor drawn per seed, from a half to two-thirds or from 1.4 to 2), or with its delay
missing. Each trial proposes one change, through the loop's ``propose`` path, and runs the judge on the record after
it until it has a verdict. The change is known:

- **better**: the number set within 5% of the truth (or the delay put back, its time within 10%);
- **worse**: the number moved further from the truth by half again (or the delay put back eight times too long);
- **neutral**: nothing the record can tell: the number moved by 0.2%, or the equation written another way;
- **slowed**: far worse, in a way the fit's total cannot see: a drain two hundred times too slow (the queue's k, the
  second stock's out-rate), so that stock's replay is slower than the record is long, which takes it out of the
  total.

A false accept is a worse, neutral or slowed change written; a false reject is a better change not written (refused when
it was proposed, failed by the judge, or still without a verdict). Over many seeds, the false-accept rate must be
about 0."""

from __future__ import annotations

import random
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..numbers import observe as ob
from ..numbers import yamledit as ye
from . import adapter as ad
from . import defects as df
from . import form as fm
from . import recovery as rc
from . import truth as tt

TRAIN, HOLD, TRIES = 8.0, 2.0, 3       # hours before the change, hours a judgement, judgements at most
KINDS = ("better", "worse", "neutral", "slowed")
KNOWN_BAD = ("worse", "neutral", "slowed")
SLOWED = {"judge-queue": "k", "judge-delay": "out-rate"}   # the rate a slowed change divides by 200
WORLDS = {                              # world → (the number set off, the delayed flow)
    "judge-queue": ("k", None),
    "judge-delay": ("move-delay", "move-in"),
}


@dataclass
class Trial:
    world: str
    seed: int
    family: str          # value or delay
    kind: str            # better, worse, neutral
    status: str          # proposed or refused
    verdict: str | None  # passed, failed, inconclusive (the record could not tell it), or None (no verdict)
    written: bool
    why: str | None
    hours: float | None = None   # the record held out when the verdict came


def _off(rng: random.Random) -> float:
    return rng.uniform(0.5, 0.67) if rng.random() < 0.5 else rng.uniform(1.4, 2.0)


def _value_edit(text: str, name: str, value: float) -> dict:
    ls = text.split("\n")
    i = next(j for j, x in enumerate(ls) if x == f"  {name}:")
    k = next(j for j in range(i + 1, len(ls)) if ls[j].strip().startswith("value:"))
    return {"file": "ergostat.yaml", "replace": ls[k], "with": f"    value: {ye.number(value)}"}


def _edit(text: str, after: dict) -> dict:
    return {"files": [{"file": "ergostat.yaml", "hunks": fm.hunks(text, fm.render(after))}]}


def trial(world: str, seed: int, family: str, kind: str, work: Path | None = None) -> Trial:
    case = tt.cases()[world]
    rng = random.Random(f"{world}:{seed}:{family}")
    truth = case.form()
    name, delayed = WORLDS[world]
    true = truth["parameters"][name]["value"]
    written = fm.copy_of(truth)
    written["description"] = None
    if family == "value":
        written["parameters"][name]["value"] = float(ye.number(true * _off(rng)))
    else:
        if delayed is None:
            raise ValueError(f"{world} has no delay")
        df.plant(written, truth, {"kind": "delay-missing", "flow": delayed})
    work = work or Path(tempfile.mkdtemp(prefix="ergostat-judge-"))
    s = rc.prepare(case, work, seed=seed, rounds=0, train_h=TRAIN, round_h=HOLD, forecast_h=HOLD * TRIES, damaged=written)
    text = s.p.model.path.read_text(encoding="utf-8")
    after = fm.copy_of(written)
    if family == "value":
        was = written["parameters"][name]["value"]
        slow = SLOWED[world]
        target = slow if kind == "slowed" else name
        new = {"better": true * rng.uniform(0.95, 1.05), "neutral": was * 1.002,
               "worse": was * 1.5 if was > true else was / 1.5,
               "slowed": written["parameters"][slow]["value"] / 200.0}[kind]
        edit = _value_edit(text, target, new)
        title, k = f"{target} is {ye.number(new)}", "parameter"
    else:
        tau = {"better": true * rng.uniform(0.9, 1.1), "worse": true * 8.0, "neutral": None, "slowed": true * 200.0}[kind]
        eqn = written["flows"][delayed]["equation"]
        if tau is None:
            ts = fm.terms(eqn)
            after["flows"][delayed]["equation"] = f"({fm.of_terms(ts)}) * 1"
        else:
            after["parameters"][name] = {"value": float(ye.number(tau)), "unit": "h", "estimate": True}
            after["flows"][delayed]["equation"] = f"DELAY3({eqn}, {name})"
        edit = _edit(text, after)
        title, k = f"{delayed}: {'through a delay' if tau else 'written another way'}", "structure"
    raw = {"kind": k, "parts": [f"parameter.{target if family == 'value' else name}" if family == "value" else f"flow.{delayed}"],
           "title": title,
           "edit": edit, "reasons": [{"says": "the replay drifts from the record", "evidence": "fit:total.nmse"}],
           "confidence": 0.5}
    loop = ad.Loop(s.p, ad.Policy.auto(hold_out=HOLD * 3600.0))
    at = s.t(TRAIN)
    got = loop.submit("judge-test", raw, data=ob.measured(s.p, ob.reference(s.p, at)), at=at)
    verdict, why, hours = None, got.get("why"), None
    if got["status"] == "proposed":
        for j in range(1, TRIES + 1):
            out = loop.judge(at=at + j * HOLD * 3600.0)
            v = next((v for v in out["verdicts"] if v["id"] == got["id"]), None)
            if v and v["verdict"] in ("passed", "failed", "inconclusive"):
                verdict, why, hours = v["verdict"], v["why"], j * HOLD
                break
    is_written = any(x["id"] == got["id"] for x in loop.accepted())
    return Trial(world, seed, family, kind, got["status"], verdict, is_written, why, hours)


def rates(trials: list[Trial]) -> dict:
    bad = [t for t in trials if t.kind in KNOWN_BAD]
    good = [t for t in trials if t.kind == "better"]
    fa = [t for t in bad if t.written]
    fr = [t for t in good if not t.written]
    by = {}
    for t in trials:
        k = f"{t.world}/{t.family}/{t.kind}"
        by.setdefault(k, [0, 0])
        by[k][0] += t.written
        by[k][1] += 1
    took = sorted(t.hours for t in trials if t.hours is not None and t.verdict in ("passed", "failed"))
    return {"trials": len(trials), "decided": len(took), "median_hours_to_decide": took[len(took) // 2] if took else None,
            "false_accepts": len(fa), "false_accept_rate": len(fa) / len(bad) if bad else None,
            "false_rejects": len(fr), "false_reject_rate": len(fr) / len(good) if good else None,
            "written_by_kind": {k: f"{a}/{n}" for k, (a, n) in sorted(by.items())},
            "false_accept_examples": [vars(t) for t in fa[:5]], "false_reject_examples": [vars(t) for t in fr[:5]]}


def run(seeds: int = 20) -> tuple[list[Trial], dict]:
    trials = []
    for seed in range(1, seeds + 1):
        for world, (_, delayed) in WORLDS.items():
            for family in ("value", "delay") if delayed else ("value",):
                for kind in KINDS:
                    trials.append(trial(world, seed, family, kind))
    return trials, rates(trials)
