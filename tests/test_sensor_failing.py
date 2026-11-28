"""A sensor whose newest read failed is said where the owner looks: in /api/status (``sensors_failing``), on the
attention list (a fault, never "for you": not a decision), and gone once it reads again. A command that
prints nothing says so, and says that ``run:`` is /bin/sh's."""

from __future__ import annotations

import time

from ergostat import model as mdl
from ergostat import state as st
from ergostat.spec.engine import number_in
from ergostat.store import Project

MODEL = """\
name: chirp

stocks:
  mission:
    unit: thing
    sensor:
      run: echo $RANDOM
      every: 5s
"""


def project(tmp_path) -> Project:
    d = tmp_path / "m"
    d.mkdir()
    (d / "ergostat.yaml").write_text(MODEL)
    return Project(mdl.load(d))


def fail(p: Project, why: str = "it printed nothing") -> None:
    p.events.add("sensor.failed", item="mission.main", source="ergostat", data={"why": why})


def test_nothing_printed_is_said_with_the_shell_it_ran_in():
    v, why = number_in("\n\n", None)
    assert v is None and why.startswith("it printed nothing") and "/bin/sh" in why and "bash -c" in why
    v, why = number_in("hello\n", None)
    assert v is None and why.endswith("'hello'")


def test_a_failing_sensor_is_listed_and_never_waits_for_the_owner(tmp_path):
    p = project(tmp_path)
    assert st.sensors_failing(p, time.time()) == []
    fail(p)
    [x] = st.sensors_failing(p, time.time())
    assert (x["sensor"], x["part"], x["why"], x["last_read"], x["in_a_row"]) == \
        ("mission.main", "stock.mission", "it printed nothing", None, 1)
    snap = st.snapshot(p)
    [a] = [a for a in st.attention(snap, True, p.model) if a["what"] == "sensor mission.main"]
    assert a["level"] == "bad" and a["part"] == "stock.mission" and not a.get("waiting")
    assert "never read" in a["says"] and "stock mission is unmeasured" in a["says"]
    fail(p)
    fail(p)
    snap = st.snapshot(p)
    [a] = [a for a in st.attention(snap, True, p.model) if a["what"] == "sensor mission.main"]
    assert not a.get("waiting") and not a.get("answer") and "its last 3 reads failed" in a["says"]


def test_a_sensor_that_reads_again_is_no_longer_failing(tmp_path):
    p = project(tmp_path)
    fail(p)
    time.sleep(0.01)
    p.measurements.add("sensor/mission.main", 7.0)
    assert st.sensors_failing(p, time.time() + 1) == []
    time.sleep(0.01)
    fail(p)
    [x] = st.sensors_failing(p, time.time() + 1)
    assert x["last_read"] is not None and x["in_a_row"] == 1


def test_the_status_answer_carries_them(tmp_path):
    from ergostat.web import server
    p = project(tmp_path)
    fail(p)
    got = server.api(server.Live(p), "status", {})
    assert [x["sensor"] for x in got["sensors_failing"]] == ["mission.main"]
    assert any(a["what"] == "sensor mission.main" for a in got["attention"])
