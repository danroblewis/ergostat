"""the-job's model (examples/the-job): every rate set by another rate is written as an equation whose units agree, and
``ergostat check`` finds nothing in it but the notes listed here, which this model leaves for other work."""

from __future__ import annotations

from pathlib import Path

from ergostat.spec import read
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
