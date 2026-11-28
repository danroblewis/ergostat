"""The engine's own faults (faults.py, SPEC §9.1): recorded when one starts, when its why changes and when it clears,
never every pass; open ones kept in faults.json, shown among the page's faults and linked to their history."""

from __future__ import annotations

import json

from ergostat import faults as fl
from ergostat.state import attention


class _P:
    def __init__(self, tmp_path, project):
        self.dir, self.events = tmp_path, project.events


def test_a_fault_is_recorded_on_change_only_and_cleared_when_it_next_succeeds(tmp_path, project):
    p = _P(tmp_path, project)
    said = []
    f = fl.Faults(p, said.append)
    for _ in range(5):                                     # five passes failing the same way: one event
        f.failed("emit", RuntimeError("database is gone"), "emit for projection deploy")
    f.ok("joins")                                          # another part, never faulted: nothing
    evs = p.events.query(n=None, type="ergostat.fault.*")
    assert [e["type"] for e in evs] == ["ergostat.fault.started"]
    assert evs[0]["item"] == "ergostat.fault/emit" and evs[0]["data"]["why"] == "RuntimeError: database is gone"
    assert evs[0]["data"]["what"] == "emit for projection deploy" and len(said) == 1
    f.failed("emit", KeyError("deploy"), "emit for projection deploy")    # its reason changed: said again
    open_ = json.loads((tmp_path / fl.STATE).read_text())
    assert open_["emit"]["why"] == "KeyError: 'deploy'" and open_["emit"]["since"] == evs[0]["data"]["since"]
    f.ok("emit")
    f.ok("emit")
    evs = p.events.query(n=None, type="ergostat.fault.*")
    assert [e["type"] for e in evs] == ["ergostat.fault.started", "ergostat.fault.changed", "ergostat.fault.cleared"]
    assert "lasted" in evs[-1]["data"] and not (tmp_path / fl.STATE).exists()


def test_an_engine_started_again_clears_what_was_open_when_it_stopped(tmp_path, project):
    p = _P(tmp_path, project)
    fl.Faults(p).failed("triggers", ValueError("bad trigger"))
    again = fl.Faults(p)                                   # a new engine: it reads what was open
    assert again.failed("triggers", ValueError("bad trigger")) is False      # still failing the same way: nothing new
    assert again.ok("triggers") is True
    assert [e["type"] for e in p.events.query(n=None, type="ergostat.fault.*")] == \
        ["ergostat.fault.started", "ergostat.fault.cleared"]


def test_an_open_fault_shows_among_the_pages_faults_with_a_link_to_its_history(tmp_path, project):
    p = _P(tmp_path, project)
    fl.Faults(p).failed("emit", RuntimeError("no room"), "emit for projection deploy")
    snap = {"faults": fl.read_state(tmp_path), "loops": {}, "agents": {}, "residuals": {}}
    (row,) = [a for a in attention(snap) if a.get("fault")]
    assert row["level"] == "bad" and row["link"] == "/events?item=ergostat.fault%2Femit"
    assert row["says"].startswith("emit for projection deploy failing since ") and row["says"].endswith("RuntimeError: no room")


def test_the_emitter_names_the_projections_whose_outbox_failed(monkeypatch):
    from ergostat.spec import emit

    class Ix:
        pass

    class E:
        class p:
            class events:
                @staticmethod
                def last_seq():
                    return 7
        spec = type("S", (), {"items": {"deploy": type("K", (), {"name": "deploy", "emit": [1]})()}})()

        @staticmethod
        def own(what, spec):
            return True

    monkeypatch.setattr("ergostat.spec.itemindex.index_for", lambda *a: Ix())

    def broken(*a):
        raise RuntimeError("disk full")
    monkeypatch.setattr(emit, "drain", broken)
    try:
        emit.Emitter(E).look()
    except RuntimeError as e:
        assert e.projections == ["deploy"]
    else:
        raise AssertionError("it raised nothing")
