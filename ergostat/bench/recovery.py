"""The recovery benchmark: a true model damaged by known defects, the improvement loop run on it with the truth's
record, for a budget of rounds, and scored against the truth (docs/MODEL-TOOLS.md, "How we know the improver works").

The timeline, ending now: ``train`` hours of record before the first round; each round the improver proposes (seeing
only the record so far), and an hour later the judge judges on the hour that came after (``improve.hold-out``) and
writes what passed (``improve.accept: auto``, so the loop moves without the owner); after the last round, ``forecast``
hours of record no model was fitted or judged on.

Scores, per case:

- **recall**: the planted defects fixed. Each is judged by its **locus error**: at each measured stock it shows at,
  the model's inflow and outflow, worked out from the truth's own record (the partial-model test, every measured
  part as the truth had it), against the truth's, as a share of the truth's (RMS); a defect is fixed when that falls
  to ``FIXED`` or less. A defect whose locus error is ``FIXED`` or less as planted is **not visible** (the record
  cannot tell it from the truth) and is left out of recall;
- **precision**: the share of the improver's proposals that are real fixes (they lower the model's distance from the
  truth, the mean locus error over every measured stock, by ``REAL`` or more and raise it nowhere);
- **damage**: accepted changes that moved the model away from the truth (its distance up by ``HARM`` or more);
- **fit**: the scaled error of the replay over the record so far, the final model's beside the damaged one's and
  the truth's (the noise floor);
- **forecast**: the scaled error of the replay on the later record, damaged, final and truth;
- **cost**: rounds, seconds, and the improver's tokens and dollars."""

from __future__ import annotations

import json
import math
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..numbers import observe as ob
from ..numbers import simulate as sim
from ..numbers import trial as tr
from ..numbers import yamledit as ye
from ..spec.ir import Spec
from . import adapter as ad
from . import defects as df
from . import form as fm
from . import truth as tt

FIXED = 0.15           # a defect is fixed when the locus error falls to this
REAL = 0.02            # a proposal is a real fix when it lowers the distance from the truth by this much
HARM = 0.02            # an accepted change damages the model when it raises that distance by this much
WARM = 0.1             # the first share of a window left out of the locus error (delays settling)


@dataclass
class Setup:
    case: tt.Case
    root: Path
    p: object
    record: tt.Record
    since: float
    train_h: float
    round_h: float
    rounds: int
    forecast_h: float
    truth: dict
    damaged: dict
    planted: list[dict]
    seed: int

    def t(self, hours: float) -> float:
        return self.since + hours * 3600.0

    @property
    def rounds_end(self) -> float:
        return self.t(self.train_h + self.rounds * self.round_h)

    @property
    def end(self) -> float:
        return self.t(self.train_h + self.rounds * self.round_h + self.forecast_h)


def prepare(case: tt.Case, work: Path, seed: int = 1, rounds: int = 6, train_h: float = 8.0, round_h: float = 2.0,
            forecast_h: float = 4.0, now: float | None = None, damaged: dict | None = None) -> Setup:
    """The damaged model in ``work/model``, its project's record in ``work/state``, the truth's run behind it."""
    from .. import model as mdl
    from ..store import Project
    total = train_h + rounds * round_h + forecast_h
    from . import clock
    end = math.floor((now or clock.real()) / 60.0) * 60.0
    since = end - total * 3600.0
    record = tt.simulate(case, since, total)
    truth = case.form()
    if damaged is None:
        damaged, planted = df.damaged(truth, case.defects, record)
    else:
        planted = []
    damaged["description"] = None
    root = work / "model"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / "ergostat.yaml").write_text(fm.render(damaged), encoding="utf-8")
    state = work / "state"
    if state.exists():
        shutil.rmtree(state)
    state.mkdir(parents=True)
    p = Project(mdl.load(root), directory=state)
    p.measurements.add_many(record.rows(seed))
    return Setup(case, root, p, record, since, train_h, round_h, rounds, forecast_h, truth, damaged, planted, seed)


# ---- scores

def nmse(p, spec: Spec, since: float, until: float) -> float | None:
    grid = ob.Grid(since, until, max(2, min(120, int((until - since) // ob.MIN_BUCKET))))
    run, got = tr.fit_of(spec, ob.measured(p, grid, spec))
    return (got.get("total") or {}).get("nmse") if run.valid else None


def stock_errors(spec: Spec, s: Setup, since: float | None = None, until: float | None = None) -> dict[str, float]:
    """Each measured stock's locus error: the model's inflow and outflow, worked out on the truth's own record,
    against the truth's (RMS over the truth's RMS)."""
    since = since or s.since
    until = until or s.rounds_end
    data = s.record.data(since, until)
    tspec = s.case.spec()
    measured = [n for n, x in tspec.stocks.items() if x.sensors]
    hidden = {n for n in spec.stocks if n not in measured}
    for n in hidden:
        data.started.setdefault(f"stock.{n}", (since, spec.stocks[n].initial or 0.0))
    try:
        run = sim.replay(spec, data, sim.plan(spec, integrate=hidden))
        vals = run.values
    except Exception:                                   # a model that cannot even be run is as far as it gets
        vals = {}

    def rate(sp: Spec, name: str, source: dict, into: bool) -> list[float]:
        out = [0.0] * data.grid.n
        for f in sp.flows.values():
            if (f.target if into else f.source) != name:
                continue
            ref = f"flow.{f.name}"
            xs = (source.get(ref) if f.equation else data.values.get(ref)) or []
            for i, v in enumerate(xs[:data.grid.n]):
                out[i] += float(v or 0.0)
        return out
    k0 = int(data.grid.n * WARM)

    def rms(xs):
        xs = xs[k0:]
        return math.sqrt(sum(x * x for x in xs) / max(len(xs), 1))
    out = {}
    for n in measured:
        err, scale = 0.0, 0.0
        for into in (True, False):
            want = rate(tspec, n, data.values, into)
            got = rate(spec, n, vals, into) if n in spec.stocks else [0.0] * data.grid.n
            if any(not math.isfinite(x) for x in got):
                got = [1e12] * len(got)
            err += rms([a - b for a, b in zip(got, want, strict=True)])
            scale += rms(want)
        out[n] = min(err / scale, 10.0) if scale > 0 else (0.0 if err == 0 else 10.0)
    return out


def distance(errs: dict[str, float]) -> float:
    return sum(errs.values()) / len(errs) if errs else 0.0


def locus_error(errs: dict[str, float], d: dict) -> float:
    xs = [errs[n] for n in d["locus"] if n in errs]
    return sum(xs) / len(xs) if xs else 0.0


def spec_after(p, x: dict) -> Spec | None:
    """The model a change would leave, compiled, or None when it cannot be made or compiled."""
    try:
        edits = [ye.Edit.from_dict(d) for d in (x.get("edit") or {}).get("files") or []]
        if not edits:
            return None
        sp, errors = tr.compiled(p.model.path, ye.apply_together(edits))
        return None if errors else sp
    except Exception:
        return None


# ---- the run

@dataclass
class Result:
    case: str
    improver: str
    judge: str
    planted: list[dict]
    rounds: list[dict] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)
    accepted: list[dict] = field(default_factory=list)
    scores: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)


def run(s: Setup, improver, stop_after_quiet: int = 2) -> Result:
    """The improvement loop on ``s``'s damaged model for its rounds; the result, scored."""
    started = time.perf_counter()
    loop = ad.Loop(s.p, ad.Policy.auto(hold_out=s.round_h * 3600.0))
    res = Result(s.case.id, improver.name, f"judge warm-up {ad.jd.WARM_UP / 3600:g}h, every stock", s.planted)
    damaged_spec = s.p.model.spec
    quiet = 0
    for r in range(s.rounds):
        at = s.t(s.train_h + r * s.round_h)
        spec_now = s.p.model.spec
        errs_now = stock_errors(spec_now, s)
        data = ob.measured(s.p, ob.reference(s.p, at))
        raws = improver.propose(s.p, loop, at, data) or []
        made = []
        for raw in raws:
            got = loop.submit(improver.name, raw, data=data, at=at)
            x = loop.changes().get(got["id"]) if got["status"] == "proposed" else None
            after = spec_after(s.p, x) if x else None
            if after is None and got["status"] != "proposed":
                try:
                    from ..numbers import improve as im
                    es_ = im.edits(spec_now, (raw or {}).get("edit"))
                    sp, errors = tr.compiled(s.p.model.path, ye.apply_together(es_))
                    after = None if errors else sp
                except Exception:
                    after = None
            errs_after = stock_errors(after, s) if after is not None else None
            gain = distance(errs_now) - distance(errs_after) if errs_after else None
            worse = max((errs_after[n] - errs_now[n] for n in errs_now), default=0.0) if errs_after else None
            row = {"round": r + 1, "id": got["id"], "title": got.get("title") or (raw or {}).get("title"),
                   "status": got["status"], "why": got.get("why"), "kind": (x or {}).get("kind") or (raw or {}).get("kind"),
                   "distance_gain": gain, "real_fix": bool(gain is not None and gain >= REAL and (worse or 0.0) < HARM)}
            res.proposals.append(row)
            made.append(row)
        verdicts = loop.judge(at=at + s.round_h * 3600.0)
        for v in verdicts["verdicts"]:
            for row in res.proposals:
                if row["id"] == v["id"]:
                    row["verdict"], row["verdict_why"] = v["verdict"], v["why"]
        for pid in verdicts["accepted"]:
            x = loop.changes()[pid]
            after = s.p.model.spec
            errs_after = stock_errors(after, s)
            d0, d1 = distance(errs_now), distance(errs_after)
            res.accepted.append({"round": r + 1, "id": pid, "title": x.get("title"), "kind": x.get("kind"),
                                 "made_by": x.get("made_by"), "distance_before": d0, "distance_after": d1,
                                 "damage": d1 - d0 >= HARM, "real_fix": d0 - d1 >= REAL})
        res.rounds.append({"round": r + 1, "at": at, "proposed": len(made),
                           "checked": sum(1 for m in made if m["status"] == "proposed"),
                           "passed": sum(1 for v in verdicts["verdicts"] if v["verdict"] == "passed"),
                           "failed": sum(1 for v in verdicts["verdicts"] if v["verdict"] == "failed"),
                           "accepted": len(verdicts["accepted"])})
        quiet = quiet + 1 if not raws else 0
        if quiet >= stop_after_quiet:
            break
    res.scores = score(s, damaged_spec, s.p.model.spec, res)
    res.cost = {**improver.cost, "rounds": len(res.rounds), "seconds": round(time.perf_counter() - started, 1)}
    return res


def score(s: Setup, damaged: Spec, final: Spec, res: Result) -> dict:
    texpr = tt.spec_of(fm.render({**tt.expressible(s.truth), "description": None}))
    e_d, e_f = stock_errors(damaged, s), stock_errors(final, s)
    defects = []
    for d in s.planted:
        before, after = locus_error(e_d, d), locus_error(e_f, d)
        visible = before > FIXED                       # damage the record cannot tell from the truth is not counted
        defects.append({"kind": d["kind"], "says": d["says"], "locus": d["locus"], "locus_error_damaged": before,
                        "locus_error_final": after, "visible": visible, "fixed": visible and after <= FIXED,
                        "halved": visible and after <= before / 2})
    props = res.proposals
    acc = res.accepted
    by_kind: dict[str, dict] = {}
    for x in props:
        k = by_kind.setdefault(x.get("kind") or "?", {"proposed": 0, "checked": 0, "passed": 0, "failed": 0, "real_fixes": 0})
        k["proposed"] += 1
        k["checked"] += x["status"] == "proposed"
        k["passed"] += x.get("verdict") == "passed" or x["id"] in {a["id"] for a in acc}
        k["failed"] += x.get("verdict") == "failed"
        k["real_fixes"] += x["real_fix"]
    t0, t1, t2 = s.since, s.rounds_end, s.end
    return {
        "defects": defects, "by_kind": by_kind,
        "recall": (sum(d["fixed"] for d in defects) / sum(d["visible"] for d in defects)
                   if any(d["visible"] for d in defects) else None),
        "proposals": len(props), "checked": sum(1 for x in props if x["status"] == "proposed"),
        "real_fixes": sum(1 for x in props if x["real_fix"]),
        "precision": sum(1 for x in props if x["real_fix"]) / len(props) if props else None,
        "accepted": len(acc), "accepted_real": sum(1 for x in acc if x["real_fix"]),
        "damage": sum(1 for x in acc if x["damage"]),
        "distance": {"damaged": distance(e_d), "final": distance(e_f)},
        "fit": {"damaged": nmse(s.p, damaged, t0, t1), "final": nmse(s.p, final, t0, t1), "truth": nmse(s.p, texpr, t0, t1)},
        "forecast": {"damaged": nmse(s.p, damaged, t1, t2), "final": nmse(s.p, final, t1, t2), "truth": nmse(s.p, texpr, t1, t2)},
    }


def as_dict(r: Result) -> dict:
    return {"case": r.case, "improver": r.improver, "judge": r.judge, "planted": r.planted, "scores": r.scores,
            "cost": r.cost, "rounds": r.rounds, "proposals": r.proposals, "accepted": r.accepted}


def save(results: list[Result], out: Path) -> tuple[Path, Path]:
    from . import scorecard
    out.mkdir(parents=True, exist_ok=True)
    data = {"cases": [as_dict(r) for r in results], "overall": scorecard.overall(results)}
    j = out / "scorecard.json"
    j.write_text(json.dumps(data, indent=1, default=str))
    m = out / "scorecard.md"
    m.write_text(scorecard.markdown(data))
    return j, m

