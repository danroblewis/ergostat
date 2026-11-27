"""What a kind and an item touch (SPEC §5a, *What a kind touches*): ``spec/footprint.py``, ``/api/projections/K`` and an
item's ``path``."""

from __future__ import annotations

import shutil
import textwrap
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

from ergostat import model as mdl
from ergostat.leases import ENDED, TAKEN
from ergostat.spec import load
from ergostat.spec.footprint import item_path, kind_footprint
from ergostat.store import Project
from ergostat.web.server import Live, api

ROOT = Path(__file__).resolve().parent.parent


def _project(tmp_path, example: str | None = None, text: str | None = None) -> Project:
    if example:
        shutil.copytree(ROOT / "examples" / example, tmp_path, dirs_exist_ok=True)
    else:
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"]
    return Project(m)




def _done_ticket(p: Project, id: str = "ticket/1") -> None:
    ev = p.events
    ev.add("ticket.planned", item=id, data={"title": "x"}, at=1000.0)
    ev.add(TAKEN, item=id, data={"run": "r1", "block": "developer", "fence": 1, "ttl": 300, "max": 3, "back": "todo"},
           at=1001.0)
    ev.add("ticket.started", item=id, causedby="r1", at=1002.0)
    ev.add("ticket.submitted", item=id, causedby="r1", at=1003.0)
    ev.add(ENDED, item=id, data={"run": "r1", "fence": 1, "how": "ack"}, at=1004.0)
    ev.add(TAKEN, item=id, data={"run": "r2", "block": "reviewer", "fence": 2, "ttl": 300, "max": 3, "back": "review"},
           at=1005.0)
    ev.add("ticket.approved", item=id, causedby="r2", at=1006.0)
    ev.add(ENDED, item=id, data={"run": "r2", "fence": 2, "how": "ack"}, at=1007.0)










UNCOUNTED = """
    name: t
    projections:
      ticket:
        query: key.startswith('ticket/')
        fields:
          state:
            type: one of [todo, done]
      note:
        query: key.startswith('note/')
        fields:
          state:
            type: one of [open, closed]
    stocks:
      todo:
        sensor: {projection: ticket, state: todo, every: 3s}
    flows:
      done:
        from: todo
    blocks:
      w:
        type: program
        run: "true"
        takes: {projection: ticket, at: todo, to: [done], where: {priority: high}}
        out: flow.done
"""


def test_a_kind_nothing_counts_is_empty_and_says_why_and_a_where_takes_only_some(tmp_path):
    p = _project(tmp_path, text=UNCOUNTED)
    spec = p.model.spec
    fp = kind_footprint(spec, "note")
    assert fp["counted_in"] == [] and fp["taken_by"] == [] and fp["goals"] == [] and fp["loops"] == []
    assert "no sensor counts items of projection note" in fp["why"] and fp["uncounted"] == ["open", "closed"]
    [t] = kind_footprint(spec, "ticket")["taken_by"]
    assert t["only_some"] and t["says"] == "takes only the items whose priority is high"
    assert sorted(kind_footprint(spec, "ticket")["uncounted"]) == ["dead", "done", "leased"]
    p.events.add("note.made", item="note/1", at=1000.0)
    [step] = item_path(spec, type("It", (), {"kind": "note", "moves": [{"time": 1.0, "from": None, "to": "open",
                                                                        "type": "note.made"}], "fields": {}})())
    assert step["stock"] is None and step["says"] == "nothing in the model counts note items in open"
    assert kind_footprint(spec, "nope") is None


def test_an_undeclared_kinds_finished_states_are_the_listings_inferred_from_the_record(tmp_path):
    from ergostat.spec import items as its
    p = _project(tmp_path, text=UNCOUNTED)
    assert not any(s["finished"] for s in kind_footprint(p.model.spec, "note")["definition"]["states"])
    p.events.add("note.made", item="note/1", at=1000.0)
    fp = api(Live(p), "projections/note", {})
    f = its.finishes(p.events, p.model.spec, "note")
    assert fp["definition"]["finished_by"] == f["finished_from"] == "inferred"
    assert [s["state"] for s in fp["definition"]["states"] if s["finished"]] == f["finished"] == ["closed"]


def test_the_footprint_is_kept_per_model_and_each_caller_has_its_own(tmp_path):
    p = _project(tmp_path, text=UNCOUNTED)
    spec = p.model.spec
    a = kind_footprint(spec, "ticket")
    a["taken_by"].clear()
    assert kind_footprint(spec, "ticket")["taken_by"]
    assert ("footprint", "ticket") in spec.lookups().kept




