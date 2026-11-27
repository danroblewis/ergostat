"""Which system each projection is in (item_systems.py): declared where the model declares it, otherwise where it
is counted (ergostat's own kinds too: the model's changes under modelling), ergostat's own that nothing counts in
ergostat, otherwise other; and the Items list says so."""

import textwrap
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import spec as sp
from ergostat.spec import items as its
from ergostat.spec.item_systems import groups, kind_systems
from ergostat.store import Project

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
BUILT_IN = ["ergostat.model-change", "ergostat.modelling-request",
            "ergostat.claim", "ergostat.message", "ergostat.verdict", "ergostat.decision",
            "ergostat.correction", "ergostat.context", "ergostat.report"]


def systems_of(demo: str) -> tuple[dict, list]:
    spec, _ = sp.read(EXAMPLES / demo / "ergostat.yaml")
    got = kind_systems(spec)
    return {k: x["system"] for k, x in got.items()}, [(g["name"], g["projections"]) for g in groups(spec, got)]






COUNTED = """
systems:
  a: {}
  b: {}
projections:
  job:
    id: job/*
    states: [open, done]
    on: {job.done: done}
  lone:
    id: lone/*
  mine:
    id: mine/*
    system: b
stocks:
  open-a:
    system: a
    unit: jobs
    sensor: {projection: job, state: open}
  done-b:
    system: b
    unit: jobs
    sensor: {projection: job, state: done}
  later-b:
    system: b
    unit: jobs
    sensor: {projection: job, state: open}
  mine-a:
    system: a
    unit: jobs
    sensor: {projection: mine}
"""


def project(tmp_path) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(COUNTED))
    return Project(mdl.load(tmp_path))


def test_counted_in_systems_that_share_none_goes_where_it_is_counted_most(tmp_path):
    p = project(tmp_path)
    got = kind_systems(p.model.spec)
    assert got["job"] == {"system": "b", "why": "counted in a, b: most in b"}
    assert got["mine"] == {"system": "b", "why": "declared"}          # counted in a, declared in b
    assert got["lone"]["system"] == "other"


def test_the_list_says_each_kind_and_items_system(tmp_path):
    p = project(tmp_path)
    t = time.time() - 60
    p.events.add("job.opened", item="job/1", data={}, at=t)
    p.events.add("x.seen", item="stray/1", data={}, at=t)                # no kind: other
    got = its.listing(p.events, p.model.spec)
    assert {k["name"]: k["system"] for k in got["projections"]}["job"] == "b"
    assert {i["id"]: i["system"] for i in got["items"]} == {"job/1": "b", "stray/1": "other"}
    assert [(g["name"], g["projections"]) for g in got["systems"]] == [("b", ["job", "mine"]), ("ergostat", BUILT_IN),
                                                                ("other", ["lone"])]
    assert its.detail(p.events, p.model.spec, "job/1")["system"] == "b"


def test_a_collapsed_system_sends_no_items(tmp_path):
    from ergostat.web.server import Live, api
    p = project(tmp_path)
    t = time.time() - 60
    p.events.add("job.opened", item="job/1", data={}, at=t)
    p.events.add("lone.seen", item="lone/1", data={}, at=t)
    live = Live(p)
    every = api(live, "items", {"shown": ["1"], "per_projection": ["25"]})
    assert {i["id"] for i in every["items"]} == {"job/1", "lone/1"}
    got = api(live, "items", {"shown": ["1"], "per_projection": ["25"], "hide": ["b,ergostat"]})
    assert [i["id"] for i in got["items"]] == ["lone/1"]
    assert {k["name"]: k["counts"] for k in got["projections"]}["job"] == {"open": 1}       # its count still said
