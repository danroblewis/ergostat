"""A journal sensor (SPEC §6): a folder of JSONL journals that something ergostat did not start writes, each complete
line recorded once, as that sensor's observations."""

import json
import os
import threading
import time

from ergostat import journal_source as js
from ergostat import model as mdl
from ergostat.spec import read
from ergostat.spec.legacy import sensor_name

from .test_leases import project, start, wait_for

MODEL = """
name: s
items:
  case:
    id: case/*
    states: [open, met]
    on: {case.met: met}
stocks:
  q:
    unit: things
    sensor: {journal: logs}
"""
NAME = "q.main"


def setup(tmp_path, text=MODEL):
    (tmp_path / "logs").mkdir()
    return project(tmp_path, text)


def reader(p, state):
    spec = p.model.spec
    j = js.Journals(p, spec.root, state, say=lambda s: None)
    j.sensors = {sensor_name(s.of.name, s.name): s for s in spec.sensors() if s.journal}
    assert list(j.sensors) == [NAME]
    return j


def met(i):
    return json.dumps({"event": "case.met", "item": f"case/{i}", "data": {"i": i}}) + "\n"


def append(path, text):
    with open(path, "a") as f:
        f.write(text)


def mets(p):
    got = p.events.query(n=None, type="case.met")
    assert all(e["source"] == NAME for e in got)
    return sorted(e["item"] for e in got)


def refused(p):
    return [e["data"]["why"] for e in p.events.query(n=None, type="sensor.refused", item=NAME)]


def test_lines_recorded_once_across_restart(tmp_path):
    p = setup(tmp_path)
    a, b = tmp_path / "logs/a.jsonl", tmp_path / "logs/b.jsonl"
    append(a, met("a1") + met("a2") + met("a3")[:10])           # a partial last line
    append(b, met("b1"))
    j = reader(p, tmp_path / "state.json")
    j.look()
    assert mets(p) == ["case/a1", "case/a2", "case/b1"]
    append(a, met("a3")[10:] + met("a4")[:5])
    j.look()
    assert mets(p) == ["case/a1", "case/a2", "case/a3", "case/b1"]
    append(a, met("a4")[5:])
    append(b, met("b2"))
    j.look()
    j.look()
    fresh = reader(p, tmp_path / "other-state.json")               # a new reader, no state: everything read again
    fresh.look()
    assert mets(p) == ["case/a1", "case/a2", "case/a3", "case/a4", "case/b1", "case/b2"]
    assert refused(p) == []


def test_unreadable_state_rereads_without_loss(tmp_path):
    p = setup(tmp_path)
    a, state = tmp_path / "logs/a.jsonl", tmp_path / "state.json"
    append(a, met(1) + '{"event": "case.met"}\n' + met(2))
    reader(p, state).look()
    assert mets(p) == ["case/1", "case/2"] and len(refused(p)) == 1
    state.write_text(json.dumps({f"{NAME}/a.jsonl": {"offset": 9}})[:-2])   # corrupt: never read as "at the end"
    append(a, met(3) + '{"event": "ergostat.started", "item": "case/x"}\n' + met(4))
    reader(p, state).look()
    assert mets(p) == ["case/1", "case/2", "case/3", "case/4"]
    assert len(refused(p)) == 2                                    # each refused line once, across the re-read
    state.write_text(json.dumps({f"{NAME}/a.jsonl": {"offset": "end"}}))
    append(a, met(5))
    reader(p, state).look()
    assert mets(p) == [f"case/{i}" for i in range(1, 6)] and len(refused(p)) == 2


def test_rewritten_journal_new_lines_recorded(tmp_path):
    p = setup(tmp_path)
    a = tmp_path / "logs/a.jsonl"
    a.write_text(met("x1") + met("x2") + met("x3"))
    j = reader(p, tmp_path / "state.json")
    j.look()
    a.write_text(met("y1") + met("y2"))                            # shrunk: rewritten, same offsets
    j.look()
    assert mets(p) == ["case/x1", "case/x2", "case/x3", "case/y1", "case/y2"]
    assert len([w for w in refused(p) if "went back" in w]) == 1
    j.look()
    assert len([w for w in refused(p) if "went back" in w]) == 1   # said once
    a.write_text("".join(met(f"z{i}") for i in range(1, 6)))       # rewritten past its old size, same file
    j.look()
    j.look()
    assert mets(p)[-5:] == [f"case/z{i}" for i in range(1, 6)]
    assert len(mets(p)) == 10
    assert len([w for w in refused(p) if "went back" in w]) == 2
    assert all("not ergostat's own" not in w and "names an item" not in w for w in refused(p))   # no fragment read


def test_bad_lines_refused_with_why(tmp_path):
    p = setup(tmp_path)
    a = tmp_path / "logs/a.jsonl"
    long = json.dumps({"event": "case.met", "item": "case/long", "data": {"x": "y" * js.LINE_BYTES}}) + "\n"
    append(a, '{"event": "sensor.read", "item": "case/1"}\n' + '{"event": "case.met"}\n' + long +
           json.dumps({"event": "case.met", "item": "case/c", "id": "cite:other.log:i:1"}) + "\n" + met("ok"))
    reader(p, tmp_path / "state.json").look()
    whys = refused(p)
    assert len(whys) == 4, whys
    assert any("not ergostat's own" in w for w in whys)
    assert any("names an item" in w for w in whys)
    assert any(f"over the {js.LINE_BYTES}" in w for w in whys)
    assert any("only the sensor other.log" in w for w in whys)
    assert p.events.query(n=None, type="sensor.read") == []
    assert mets(p) == ["case/ok"]
    reader(p, tmp_path / "no-state.json").look()                   # read again: nothing said twice
    assert len(refused(p)) == 4 and mets(p) == ["case/ok"]


def test_caps_spread_over_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "LINES", 10)
    monkeypatch.setattr(js, "FILES", 3)
    p = setup(tmp_path)
    append(tmp_path / "logs/a.jsonl", "".join(met(f"a{i:02}") for i in range(25)))
    for n in "bcde":
        append(tmp_path / f"logs/{n}.jsonl", met(f"{n}0"))
    j = reader(p, tmp_path / "state.json")
    j.look()
    assert len(mets(p)) == 10
    for _ in range(5):
        j.look()
    assert mets(p) == sorted([f"case/a{i:02}" for i in range(25)] + ["case/b0", "case/c0"])
    past = [w for w in refused(p) if "past the first 3" in w]
    assert len(past) == 1 and "(from d.jsonl)" in past[0]


def test_compile_refuses_outside_root_and_two_kinds(tmp_path):
    for folder, code in [("/var/log", "bad-journal"), ("../elsewhere", "bad-journal"), ("logs/../../x", "bad-journal")]:
        f = tmp_path / folder.replace("/", "_") / "ergostat.yaml"
        f.parent.mkdir()
        f.write_text(MODEL.replace("journal: logs", f"journal: {folder}"))
        _, problems = read(f)
        assert code in {x.code for x in problems if x.level == "error"}, (folder, problems)
        assert all(x.where and x.where.line >= 1 for x in problems if x.code == code)
    f = tmp_path / "two/ergostat.yaml"
    f.parent.mkdir()
    f.write_text(MODEL.replace("journal: logs", "journal: logs, run: echo 1"))
    _, problems = read(f)
    assert "sensor-kind" in {x.code for x in problems if x.level == "error"}
    f = tmp_path / "ok/ergostat.yaml"
    f.parent.mkdir()
    f.write_text(MODEL)
    spec, problems = read(f)
    assert not [x for x in problems if x.level == "error"], problems
    assert not spec.stocks["q"].sensors["main"].measured           # never read on a schedule


def test_symlink_leaving_folder_not_read(tmp_path):
    p = setup(tmp_path)
    (tmp_path / "outside").mkdir()
    append(tmp_path / "outside/x.jsonl", met("out"))
    os.symlink(tmp_path / "outside/x.jsonl", tmp_path / "logs/x.jsonl")
    j = reader(p, tmp_path / "state.json")
    j.look()
    j.look()
    reader(p, tmp_path / "state.json").look()
    assert mets(p) == []
    assert len([w for w in refused(p) if "leaves the folder" in w]) == 1


def test_fifo_in_folder_not_read_and_never_blocks(tmp_path):
    p = setup(tmp_path)
    os.mkfifo(tmp_path / "logs/a.jsonl")                           # sorted first: a blocking open would stop the pass
    append(tmp_path / "logs/b.jsonl", met("b1"))
    j = reader(p, tmp_path / "state.json")
    t = threading.Thread(target=lambda: (j.look(), j.look()), daemon=True)
    t.start()
    t.join(5)
    assert not t.is_alive()
    assert mets(p) == ["case/b1"]
    assert len([w for w in refused(p) if "not a regular file" in w]) == 1


def test_value_line_read_again_is_no_new_reading(tmp_path):
    p = setup(tmp_path)
    series = p.model.spec.stocks["q"].sensors["main"].series
    append(tmp_path / "logs/a.jsonl", '{"value": 3}\n')
    reader(p, tmp_path / "state.json").look()
    assert p.measurements.count(series) == 1
    reader(p, tmp_path / "no-state.json").look()                   # read again from the start: no new reading
    j = reader(p, tmp_path / "state.json")
    j.state.clear()                                                # (as a file gone back is)
    j.look()
    assert p.measurements.count(series) == 1
    append(tmp_path / "logs/a.jsonl", '{"value": 4}\n')
    j.look()
    assert p.measurements.count(series) == 2 and p.measurements.latest(series)[1] == 4.0


def test_value_line_reading_and_stop_on_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "EVERY", 0.05)
    none = tmp_path / "none"
    none.mkdir()
    quiet = start(project(none, MODEL.replace("sensor: {journal: logs}", "sensor: {manual: true}")))
    try:
        assert quiet.journals is None                              # no journal sensor: no thread for them
    finally:
        quiet.close()
    p = setup(tmp_path)
    e = None
    try:
        e = p_engine = start(p)
        assert e.journals is not None and e.journals.thread.is_alive()
        series = p.model.spec.stocks["q"].sensors["main"].series
        append(tmp_path / "logs/a.jsonl", '{"value": 3}\n{"value": true}\n')
        assert wait_for(lambda: p.measurements.latest(series), 5)[1] == 3.0
        assert any("finite number" in w for w in refused(p))
        (tmp_path / "ergostat.yaml").write_text(MODEL.replace("sensor: {journal: logs}", "sensor: {manual: true}"))
        p_engine.swap(mdl.load(tmp_path))
        assert e.journals.sensors == {}
        append(tmp_path / "logs/a.jsonl", met("after-reload"))
        time.sleep(0.5)                                            # ten looks' worth: a removed sensor is not read
        assert mets(p) == []
        began = time.monotonic()
        e.close()
        assert not e.journals.thread.is_alive() and time.monotonic() - began < 5
        e = None
    finally:
        if e is not None:
            e.close()
