"""Acceptance (items-one-section-per-kind-closed): ``/api/items-overview`` answers the Items page's overview in one
request, from the item index, with no event-log scan; each state is in a state group, summed on the server so the page's
toggle needs no request; and the overview's script asks for nothing else and draws no item row."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ergostat.web.items_overview import GROUPS, grouped, state_groups
from tests import factory_shape

ROOT = Path(__file__).resolve().parent.parent
KINDS_JS = ROOT / "ergostat" / "web" / "static" / "kinds.js"


def test_state_groups_follow_the_finished_waiting_and_paused_states():
    f = {"finished": ["merged", "closed"], "paused": ["parked"], "queue": ["open", "ready"]}
    got = state_groups(["open", "ready", "leased", "building", "merged", "parked", "dead", "closed"], f)
    assert got == {"open": "waiting", "ready": "waiting", "leased": "working", "building": "working",
                   "merged": "done", "closed": "done", "parked": "stopped", "dead": "stopped"}
    assert state_groups(["held"], {"finished": [], "paused": [], "queue": ["held"]}) == {"held": "waiting"}   # lives on


def test_grouped_sums_each_groups_states_and_keeps_only_its_groups():
    g = {"open": "waiting", "doing": "working", "review": "working", "done": "done"}
    got = grouped({"open": [1, 2], "doing": [3, 0], "review": [1, 1], "done": [0, 5]}, g, 2)
    assert got == {"waiting": [1, 2], "working": [4, 1], "done": [0, 5]}
    assert list(got) == [x for x in GROUPS if x in got]                    # stacked in the groups' order


@pytest.fixture(scope="module")
def factory(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    d = tmp_path_factory.mktemp("factory")
    mp.setenv("ERGOSTAT_HOME", str(d / "home"))
    factory_shape.write(d / "f")
    from ergostat import model as mdl
    from ergostat.store import Project
    yield Project(mdl.load(d / "f"))
    mp.undo()


def segment_reads(monkeypatch) -> list:
    """Each read of the event log's sealed segments, the head's events and the item-by-item reads, counted."""
    from ergostat import segments
    seen: list = []
    for name in ("_rows", "_scan", "counted", "items", "times"):
        was = getattr(segments.Segments, name)

        def spy(self, *a, _was=was, _name=name, **kw):
            seen.append(_name)
            return _was(self, *a, **kw)
        monkeypatch.setattr(segments.Segments, name, spy)
    return seen


@pytest.mark.slow
@pytest.mark.serial
def test_the_overview_answers_the_factorys_record_in_under_200ms_with_no_event_log_scan(factory, monkeypatch):
    from ergostat.web.items_overview import overview
    p = factory
    week = 7 * 86400
    overview(p, time.time(), week)                                  # the index made (once per record), as any answer's
    seen = segment_reads(monkeypatch)
    took = []
    for _ in range(3):
        t0 = time.perf_counter()
        d = overview(p, time.time(), week)
        took.append(time.perf_counter() - t0)
    assert seen == [], seen                                             # the event log never read
    assert min(took) < 0.2, took
    kinds = {k["name"]: k for k in d["kinds"]}
    assert len(kinds) >= 25, len(kinds)
    assert [s["name"] for s in d["systems"]][:4] == list(factory_shape.SYSTEMS)
    gap = kinds["gap"]
    assert gap["total"] == 700 and kinds["session"]["total"] == 2500
    assert gap["unfinished"] == 700 - gap["now"].get("done", 0) > 0
    assert gap["group"] == {"queued": "waiting", "working": "working", "checking": "working", "done": "done",
                            "parked": "stopped"}
    assert set(gap["by_group"]) == {"waiting", "working", "stopped", "done"}
    for i in range(d["points"]):                                       # a group's band is its states' summed
        assert gap["by_group"]["working"][i] == gap["counts"]["working"][i] + gap["counts"]["checking"][i]
    fin = gap["counts"]["done"]                                        # (nothing leaves done here): it only grows,
    assert fin == sorted(fin) and 0 < fin[-1] <= gap["now"]["done"]   # to at most the count now (buckets' middles)
    assert 0 < gap["arrived"] <= 700 and gap["rate_in"] == pytest.approx(gap["arrived"] / ((d["until"] - d["since"]) / 3600))
    assert gap["left"] > 0 and gap["rate_out"] > 0
    assert not gap["quiet"]
    quiet = [k for k in d["kinds"] if k["quiet"]]
    assert quiet and all(k["total"] == 0 for k in quiet if k["name"].startswith("ergostat.")), quiet


def test_the_overview_counts_an_item_changed_after_the_moment_as_it_stood(factory):
    """A moment a little past: an item with an event since is folded again from its own events, so the counts are
    those of then (never the item as it is now, never dropped)."""
    from ergostat.web.items_overview import overview
    p = factory
    before = overview(p, time.time(), 86400)
    at = time.time()
    p.events.add("gap.done", item="gap/0", at=at + 5)
    p.events.add("gap.queued", item="gap/new", at=at + 6)
    then = {k["name"]: k for k in overview(p, at, 86400)["kinds"]}["gap"]
    old = {k["name"]: k for k in before["kinds"]}["gap"]
    assert then["now"] == old["now"] and then["total"] == 700
    now = {k["name"]: k for k in overview(p, time.time() + 10, 86400)["kinds"]}["gap"]
    assert now["total"] == 701 and now["now"]["done"] >= old["now"].get("done", 0)


def test_out_counts_only_the_cards_finished_never_a_paused_or_leased_state_never_left(tmp_path, monkeypatch):
    """Rate out and ``left`` count the items that first reached a finished state by the card's own rule
    (``finish_of``), the same rule its unfinished count uses: a ``leased`` and a paused state that no item has left are
    never finished, though the older ``done_states`` rule would count them; an item changed after the moment counts
    as it stood then."""
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web.items_overview import overview
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    d = tmp_path / "m"
    d.mkdir()
    st = ["open", "leased", "parked", "done"]
    (d / "ergostat.yaml").write_text(
        "name: out-rule\nitems:\n  job:\n    id: job/*\n    states: [" + ", ".join(st) + "]\n    on: {"
        + ", ".join(f"job.{s}: {s}" for s in st) + "}\nmessages:\n  paused: {job: [parked]}\n")
    p = Project(mdl.load(d))
    t = time.time() - 3600
    evs = [("job.open", "job/1", t), ("job.leased", "job/1", t + 10),          # leased, never left
           ("job.open", "job/2", t + 1), ("job.parked", "job/2", t + 11),      # paused, never left
           ("job.open", "job/3", t + 2), ("job.done", "job/3", t + 12),        # finished
           ("job.open", "job/4", t + 3),                                         # finishes only after the moment
           ("job.open", "job/5", t + 4), ("job.done", "job/5", t + 14)]        # finished, changed after the moment
    p.events.add_many([{"type": ty, "item": i, "at": a} for ty, i, a in evs], new=True)
    at = time.time()
    p.events.add("job.done", item="job/4", at=at + 5)
    p.events.add("job.done", item="job/5", at=at + 6)
    got = overview(p, at, 86400)
    job = {k["name"]: k for k in got["kinds"]}["job"]
    assert job["finished"] == ["done"], job["finished"]
    assert job["total"] == 5 and job["unfinished"] == 3
    assert job["left"] == 2, job["left"]
    assert job["rate_out"] == pytest.approx(2 / (max(got["until"] - got["since"], 1.0) / 3600))


def test_the_endpoint_is_one_answer_and_takes_no_snapshot(factory, monkeypatch):
    from ergostat import state
    from ergostat.web.server import Live, api

    def no(*a, **kw):
        raise AssertionError("a snapshot was taken")
    monkeypatch.setattr(state, "snapshot", no)
    d = api(Live(factory), "items-overview", {"since": ["1d"]})
    assert d["until"] - d["since"] <= 86400 + 1 and {k["name"] for k in d["kinds"]} >= {"gap", "session"}
