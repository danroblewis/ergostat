"""the-job's model (examples/the-job): every rate set by another rate is written as an equation whose units agree, and
``ergostat check`` finds nothing in it but the notes listed here, which this model leaves for other work; the flows only I
move are marked mine and moved by nothing else; and the drafting capacity's law steps as designed, in a balancing loop."""

from __future__ import annotations

import functools
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from ergostat.spec import causal, read
from ergostat.spec.equation_checks import units
from ergostat.spec.ir import template_made

JOB = Path(__file__).resolve().parent.parent / "examples" / "the-job" / "ergostat.yaml"

# The rates another rate sets (a coflow, or a delay of it): the README's "The numbers" names each.
COUPLED = {"alerts-fired", "outages-noticed", "ramps-broke", "ramps-proved-fine", "actions-filed", "docs-needed"}

# Notes `check` gives the-job that are not about its couplings, left for other work: blocks and watchers with no
# description, the decision rules of the flows a block moves (no-equation), three event names, two schedules on blocks
# with a goal, and ci-upgrade-planned's setpoint of 1 (within one version of current, on purpose). Allowed by code,
# and only as notes: any finding, error or other code fails.
LEFT = {"no-description", "collector-undescribed", "no-equation", "event-names-mixed", "schedule-removed",
        "queue-goal-tolerance"}


def test_check_reports_nothing_on_the_job():
    spec, problems = read(JOB)                          # with the extreme-conditions run, as `ergostat check` does
    bad = [f"{p.level} {p.code} {p.about}: {p.message}" for p in problems if p.level != "note" or p.code not in LEFT]
    assert bad == [], "\n".join(bad)
    unequated = {p.about for p in problems if p.code == "no-equation"}
    assert not unequated & {f"flow.{n}" for n in COUPLED}, unequated


def test_every_coupled_rate_has_a_units_consistent_equation():
    spec, problems = read(JOB, extremes=False)
    coupled = {f.name for f in spec.flows.values() if any(r.kind == "flow" for r in f.driven_by)
               and not template_made(f)}                # the-job's own, not those of ergostat's modelling template
    assert coupled == COUPLED                           # the list the README speaks of is the model's own
    for name in sorted(coupled):
        f = spec.flows[name]
        assert f.equation is not None, name
        causes = {str(r) for r in f.driven_by if r.kind == "flow"}
        assert causes <= set(f.equation.refs), (name, causes, f.equation.refs)   # each signed cause is in the equation
        got, want, wrong = units(spec, "flow", name)
        assert not wrong and got is not None and got == want, (name, got, want, wrong)
    assert not [p for p in problems if p.code in ("equation-units", "units-mismatch")]
    ratios = {r.name for c in coupled for r in spec.flows[c].driven_by if r.kind == "auxiliary"}
    assert ratios and all(spec.auxiliaries[n].equation is not None for n in ratios), ratios   # a value, not bare


# ---- what only I move, and the capacity law

def mine_wrong(spec) -> list[str]:
    """What breaks "only I move my steps": a flow marked mine (its description ends "(mine)") that no person block on
    me moves, or that a program or AI block moves; and a flow a person block on me moves that is not marked mine."""
    mine = {f.name for f in spec.flows.values() if f.description.endswith("(mine)") and not template_made(f)}
    moved: dict[str, set[str]] = {}
    for b in spec.blocks.values():
        for r in (r for rs in b.outputs.values() for r in rs if r.kind == "flow"):
            moved.setdefault(r.name, set()).add("me" if b.type == "person" and b.agent == "me" else f"{b.type} {b.name}")
    bad = [f"{n}: mine, moved by {sorted(moved.get(n, set()) - {'me'}) or 'no person block on me'}"
           for n in sorted(mine) if moved.get(n) != {"me"}]
    return bad + [f"{n}: moved by me, not marked mine" for n, by in sorted(moved.items()) if "me" in by and n not in mine]


def _copy(tmp_path: Path, file: str, old: str, new: str) -> Path:
    root = tmp_path / "job"
    shutil.copytree(JOB.parent, root, ignore=shutil.ignore_patterns("run", "outbox", "__pycache__"))
    p = root / "job" / file
    assert old in p.read_text()
    p.write_text(p.read_text().replace(old, new, 1))
    return root / "ergostat.yaml"


def test_only_person_blocks_move_my_steps(tmp_path):
    spec = _spec()
    mine = {f.name for f in spec.flows.values() if f.description.endswith("(mine)")}
    assert {"comments-posted", "outages-declared", "outages-dismissed", "ramps-approved", "ramps-rejected",
            "docs-approved"} <= mine                       # (the verbs: post, declare, dismiss, approve, reject, present)
    assert mine_wrong(spec) == []
    # a preparer pointed at a step of mine, and a step of mine unmarked: each is found
    moved = read(_copy(tmp_path / "a", "incidents.yaml", "out: flow.comment-drafting", "out: flow.comments-posted"),
                 extremes=False)[0]
    assert any(w.startswith("comments-posted: mine, moved by ['ai alert-companion']") for w in mine_wrong(moved))
    unmarked = read(_copy(tmp_path / "b", "safety.yaml", "by me (mine)", "by me"), extremes=False)[0]
    assert "ramps-approved: moved by me, not marked mine" in mine_wrong(unmarked)


@functools.cache
def _spec():
    return read(JOB, extremes=False)[0]


def _law(spec):
    return spec.blocks["capacity-law"]


def _step(tmp_path: Path, ctx: dict, stored: float | None = None, env: dict | None = None) -> tuple[dict | None, float]:
    """Run the law's own command (the model's run:) on ``ctx`` in a copy of bin/: what it prints (None: nothing), and
    the setting after, as its sensor (the model's) reads it."""
    spec = _spec()
    (tmp_path / "bin").mkdir(parents=True)
    shutil.copy(JOB.parent / "bin" / "capacity.py", tmp_path / "bin")
    store = tmp_path / "run" / "capacity.json"
    if stored is not None:
        store.parent.mkdir(exist_ok=True)
        store.write_text(json.dumps({"setting": stored}))
    run = shlex.split(str(_law(spec).params["run"]))
    base = {k: v for k, v in os.environ.items() if k != "JOB_POLICY"}
    got = subprocess.run([sys.executable, *run[1:]], cwd=tmp_path, input=json.dumps(ctx), capture_output=True,
                         text=True, env={**base, **(env or {})}, check=True).stdout
    sensor = shlex.split(next(iter(spec.stocks["drafting-capacity"].sensors.values())).run)
    now = subprocess.run([sys.executable, *sensor[1:]], cwd=tmp_path, capture_output=True, text=True, check=True)
    return (json.loads(got) if got.strip() else None), float(now.stdout)


def _ctx(error, **params) -> dict:
    law = {k: _law(_spec()).params[k] for k in ("gain", "deadband", "resolution", "limits")}
    return {"inputs": {"goal.alert-drafting-paced.error": error}, "params": {**law, **params}}


def test_the_capacity_law_steps_by_gain_within_deadband_and_limits(tmp_path):
    spec = _spec()
    b, pool = _law(spec), spec.blocks["alert-companion"]
    gain, band, (lo, hi) = b.params["gain"], b.params["deadband"], b.params["limits"]
    assert str(pool.pool_now) == "stock.drafting-capacity" and lo >= 1 and hi <= pool.pool   # never 0, never cut
    runs = [b.params["run"], *(s.run for s in spec.stocks["drafting-capacity"].sensors.values())]
    assert [r.split()[-1] for r in runs] == ["2", "2"] and lo <= 2 <= hi   # one start value, within the limits
    assert _step(tmp_path / "start", {}) == (None, 2)    # before any step: the start value, the preparers kept going
    for e, was in ((-1, 2), (1, 2), (-2, 1)):             # outside the deadband: a step of gain x error
        assert _step(tmp_path / f"e{e}{was}", _ctx(e), was) == ({"moved": gain * e}, was + gain * e)
    for i, e in enumerate((band, -band, 0)):              # inside it: nothing printed, nothing stored
        assert _step(tmp_path / f"in{i}", _ctx(e), 2) == (None, 2)
    assert _step(tmp_path / "hi", _ctx(-5), 2) == ({"moved": hi - 2}, hi)     # clamped at the limits
    assert _step(tmp_path / "lo", _ctx(5), 2) == ({"moved": lo - 2}, lo)
    assert _step(tmp_path / "at-hi", _ctx(-5), hi) == (None, hi)              # held there: no step printed
    assert _step(tmp_path / "r0", _ctx(-1, gain=-0.4), 2) == (None, 2)        # 0.4 rounds to no step: nothing printed
    assert _step(tmp_path / "r1", _ctx(-2, gain=-0.4), 2) == ({"moved": 1}, 3)   # 0.8 rounds to a step of 1


def test_the_capacity_law_does_not_step_on_a_missing_reading(tmp_path):
    for i, ctx in enumerate([{"params": _ctx(-2)["params"]}, _ctx(None), _ctx(float("nan")), _ctx("-2"), _ctx(True),
                             {**_ctx(-2), "stale": {"goal.alert-drafting-paced": 30.0}}]):
        assert _step(tmp_path / str(i), ctx, 2) == (None, 2), ctx
    store = tmp_path / "bad" / "run" / "capacity.json"   # a setting that can't be read is the start value, not 0
    store.parent.mkdir(parents=True)
    store.write_text("{not json")
    assert _step(tmp_path / "bad", {}) == (None, 2)
    # JOB_POLICY=off: the setting held fixed, nothing printed (not a step of 0), nothing stored
    assert _step(tmp_path / "off", _ctx(-2), 2, env={"JOB_POLICY": "off"}) == (None, 2)
    assert _step(tmp_path / "on", _ctx(-2), 2, env={"JOB_POLICY": "on"}) == ({"moved": 1}, 3)


def test_the_capacity_loop_is_balancing():
    spec = _spec()
    through = {"block.capacity-law", "flow.capacity-steps", "stock.drafting-capacity", "flow.comment-drafting",
               "stock.alerts-to-draft", "goal.alert-drafting-paced"}
    found = [lp for lp in causal.loops(spec) if "block.capacity-law" in lp.parts]
    assert found and all(set(lp.parts) == through for lp in found), [lp.parts for lp in found]
    assert {lp.polarity for lp in found} == {"B"}, [(lp.parts, [x.sign for x in lp.links]) for lp in found]
    # ergostat signs a controller's reading of its error as closing the gap, whatever its law: so the loop is signed
    # again with the law's own sign there (the gain's: u_k = u_(k-1) + gain x e_k), every other link as ergostat has it
    for lp in found:
        signs = [1 if x.source == "goal.alert-drafting-paced" else x.sign for x in lp.links]
        assert math.prod(signs) * (1 if _law(spec).params["gain"] > 0 else -1) < 0, [(str(x), x.sign) for x in lp.links]
