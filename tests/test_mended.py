"""The modelling loop measures what it draws (docs/roadmap/overnight/mended.md): ``model-mended`` sums what each change
written took off the error (``sum: fit_gained`` of the items entering ``accepted``), ``model-drift`` is the rest of
the error's change (``changes: rest``), and ``check`` names a flow measured as every rise or fall but drawn as caused
by another flow."""

import textwrap
import time

from ergostat.numbers import observe as ob
from ergostat.numbers import proposals as pr
from ergostat.spec import read
from ergostat.spec.engine import changed, read_sensor
from ergostat.spec.findings import find
from tests.test_modelling_template import USE, model
from tests.test_numbers import queue_project

FLOWS = """
stocks:
  err:
    unit: "1"
    sensor:
      manual: true
flows:
  mended:
    from: err
    driven-by: {cause: +flow.written, instant: true}
    sensor:
      projection: ergostat.model-change
      entering: accepted
      sum: fit_gained
      over: 1h
  drift:
    to: err
    two-way: true
    sensor:
      changes: rest
      over: 1h
  written:
    to: err
"""


def spec_of(tmp_path, text=FLOWS):
    d = tmp_path / "m"
    d.mkdir(exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    spec, problems = read(d / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], problems
    return spec, problems


def test_accepted_change_shows_in_mended(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    x = next(x for x in pr.make(p, snap) if x["kind"] == "parameter")
    got = pr.accept(p, x["id"], snap)
    gained = got["applied"]["fit_before"]["nmse"] - got["applied"]["fit_after"]["nmse"]
    assert got["fit_gained"] == round(gained, 6) and gained > 0
    spec, _ = spec_of(tmp_path)
    s = spec.flows["mended"].sensors["main"]
    v, why = read_sensor(spec, s, p.events)
    assert not why and abs(v - got["fit_gained"]) < 1e-9          # its gain, per hour over the hour
    assert read_sensor(spec, s, p.events, counts=object())[0] == v   # read from the record, not the counts kept


def test_fall_without_change_is_drift(tmp_path):
    p, _ = queue_project(tmp_path)
    spec, _ = spec_of(tmp_path)
    now = time.time()
    for dt, v in ((-3000, 0.5), (-1200, 0.3)):                   # the error fell by 0.2, and no change was written
        p.measurements.add("sensor/err.main", v, at=now + dt)
    mended = read_sensor(spec, spec.flows["mended"].sensors["main"], p.events)[0]
    p.measurements.add("sensor/mended.main", mended, at=now - 60)
    assert mended == 0.0
    assert changed(spec, spec.flows["drift"].sensors["main"], p.measurements, now)[0] == -0.2
    p.measurements.add("sensor/mended.main", 0.15, at=now - 30)    # had a change taken 0.15 off: the rest is drift's
    assert changed(spec, spec.flows["drift"].sensors["main"], p.measurements, now)[0] == -0.05


def test_replay_sum_and_rest(tmp_path):
    p, snap = queue_project(tmp_path, k_true=3.0)
    x = next(x for x in pr.make(p, snap) if x["kind"] == "parameter")
    got = pr.accept(p, x["id"], snap)
    spec, _ = spec_of(tmp_path)
    now = time.time()
    p.measurements.add("sensor/err.main", 1.0, at=now - 1700)
    p.measurements.add("sensor/err.main", 1.0 - got["fit_gained"] - 0.1, at=now - 100)
    d = ob.measured(p, ob.Grid(now - 1800, now + 1, 6), spec)
    assert abs(d.counted["flow.mended"].total[-1] - got["fit_gained"]) < 1e-9
    assert abs(d.counted["flow.drift"].total[-1] - -0.1) < 1e-9      # the fall the change does not account for


def test_check_finds_measured_not_caused(tmp_path):
    planted = FLOWS.replace("""      projection: ergostat.model-change
      entering: accepted
      sum: fit_gained
""", "      changes: falls\n")
    _, problems = spec_of(tmp_path, planted)
    got = [x for x in problems if x.code == "measured-not-caused"]
    assert len(got) == 1 and "every fall of err, but drawn as caused by written" in got[0].message
    spec, _ = spec_of(tmp_path)
    assert "measured-not-caused" not in {x.code for x in find(spec)}


def test_template_has_no_such_finding(tmp_path):

    spec, problems = model(tmp_path, USE)
    assert "measured-not-caused" not in {x.code for x in problems}
    assert spec.flows["model-drift"].two_way and spec.flows["model-drift"].sensors["main"].changes["what"] == "rest"
    assert spec.flows["model-mended"].sensors["main"].items["sum"] == "fit_gained"


def test_a_daemon_sensors_panel_line_names_its_daemon(tmp_path):
    from ergostat.spec.item_sets import counted_by
    spec, _ = spec_of(tmp_path, """
daemons:
  shared: {run: python3 d.py}
stocks:
  a:
    sensor: {daemon: shared, every: 1s}
  b:
    sensor: {daemon: {run: python3 p.py}, push: true}
""")
    assert counted_by(spec, "stock", "a") == {"says": "Read by daemon shared"}
    assert counted_by(spec, "sensor", "a.main") == {"says": "Read by daemon shared"}
    said = counted_by(spec, "stock", "b")["says"]
    assert said.startswith("Read by daemon ") and said.endswith(", which sends its readings by itself")
