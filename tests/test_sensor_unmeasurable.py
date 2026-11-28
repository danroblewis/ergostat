"""A measure with nothing to measure yet is not a failure: ``ergostat measure`` exits 3 and says why, and the engine
records the sensor as unmeasurable (``sensor.unmeasurable``, once, when it starts), never ``sensor.failed``: no
failing sensor in the status, nothing on the attention list's faults, the log line said once, and a value read
afterwards is a normal reading."""

from __future__ import annotations

import subprocess
import sys
import time


from ergostat import model as mdl
from ergostat import state as st
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """\
name: fitless

auxiliaries:
  model-error:
    unit: "1"
    sensor:
      builtin: ergostat.model.fit
      every: 1m
"""


def project(tmp_path) -> Project:
    d = tmp_path / "m"
    d.mkdir()
    (d / "ergostat.yaml").write_text(MODEL)
    return Project(mdl.load(d))


def test_measure_exits_3_and_says_why(tmp_path):
    p = project(tmp_path)
    r = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path / "m"), "measure", "ergostat.model.fit"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 3, r.stderr
    assert "no value yet: no stock of the model's own is read by a sensor" in r.stderr


def test_a_fit_with_no_stocks_is_unmeasurable_not_failing(tmp_path):
    p = project(tmp_path)
    said: list[str] = []
    eng = Engine(p, say=said.append)
    [s] = [x for x in p.model.spec.sensors() if x.builtin]
    for _ in range(3):
        eng._read(s)
    assert p.events.query(type="sensor.failed") == []
    [u] = p.events.query(type="sensor.unmeasurable")
    assert "no stock of the model's own is read by a sensor" in u["data"]["why"]
    lines = [x for x in said if x.startswith("sensor model-error.main")]
    assert len(lines) == 1 and "not measurable yet" in lines[0], said
    assert st.sensors_failing(p, time.time()) == []
    [x] = st.sensors_unmeasurable(p, time.time())
    assert x["part"] == "auxiliary.model-error" and "nothing to replay" in x["why"]
    from ergostat.web import server
    got = server.api(server.Live(p), "status", {})
    assert got["sensors_failing"] == [] and [x["sensor"] for x in got["sensors_unmeasurable"]] == ["model-error.main"]
    assert not any(a.get("level") == "bad" and "model-error" in str(a.get("what")) for a in got["attention"])
    eng2 = Engine(p, say=said.append)                     # a new engine knows it from the record: not said again
    eng2._read(s)
    assert len(p.events.query(type="sensor.unmeasurable")) == 1
    time.sleep(0.01)
    p.measurements.add(s.series, 0.02)                    # a value read: a normal reading, no longer unmeasurable
    assert st.sensors_unmeasurable(p, time.time() + 1) == []


def test_no_modelling_request_while_nothing_is_read_yet(tmp_path):
    """A projections-first model at its start: the fit is unmeasurable for want of a stock read, and that is nothing
    for the owner or the AI tier to do yet, so no fit-unknown request is raised."""
    from ergostat.numbers import requests as rq
    p = project(tmp_path)
    assert not [r for r in rq.gather(p, p.model.spec, coherence=False) if r["code"] == "fit-unknown"]
