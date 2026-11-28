"""What a projection publishes from its own objects (SPEC §5a, *Emitted events*): ``emit:``, a field's transitions and
a condition's edges, published live only, once each, inferred, never read back by default; blocks triggered by them."""

from __future__ import annotations

import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.spec import emit, itemindex, workbench
from ergostat.spec import items as its
from ergostat.store import Project

T0 = 1_700_000_000.0

BODY = """\
projections:
  instance:
    query: type.startswith('vm.')
    key: name
    time: data.at
    name: "'vm ' + name"
    fields:
      name: text
      state: {values: [pending, running, stopping, stopped]}
      latency_ms: {type: number}
      desired: {type: integer}
      running: {type: integer}
      health: {values: [empty, some, full], from: "'empty' if not running else 'full' if running >= desired else 'some'"}
    defaults:
      name: data.name
    events:
      state:
        when: type == 'vm.state'
        state: data.state
      latency:
        when: type == 'vm.latency'
        latency_ms: data.ms
      count:
        when: type == 'vm.count'
        desired: data.desired
        running: data.running
    emit:
EMIT
EXTRA
"""
EMIT = """\
      state: transitions
      health: transitions
      slow: latency_ms > 500
"""


def body(emit_: str = EMIT, extra: str = "") -> str:
    return BODY.replace("EMIT\n", emit_).replace("EXTRA\n", extra)


def project(tmp_path, emit_: str = EMIT, extra: str = "") -> Project:
    (tmp_path / "ergostat.yaml").write_text(body(emit_, extra))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(e) for e in m.errors]
    return Project(m)


def errors(tmp_path, text: str, level: str = "error") -> list[tuple[str, str]]:
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(text)
    _, problems = read(tmp_path / "ergostat.yaml", extremes=False)
    return [(x.code, x.message) for x in problems if x.level == level]


def add(p, t: str, at: float, name: str = "web", recorded: float | None = None, **data):
    return p.events.add(t, data={"name": name, "at": T0 + at, **data}, at=T0 + (recorded if recorded is not None else at))


def publish(p, type: str | None = None) -> list[dict]:
    """The index caught up and its outbox recorded, as the engine's loop does; every emitted event (of ``type``)."""
    ix = itemindex.index_for(p.events, p.model.spec, False)
    while emit.drain(ix, p.events):
        pass
    return [e for e in p.events.query(n=None) if emit.emitted(e) and (type is None or e["type"].startswith(type))]


def started(p) -> None:
    """The index made (its mark: nothing recorded so far publishes), as a running ergostat has it."""
    publish(p)


def test_transitions_are_published_live_with_from_to_and_the_cause(tmp_path):
    p = project(tmp_path)
    started(p)
    a = add(p, "vm.state", 0, state="running")
    b = add(p, "vm.state", 1, state="stopping")
    add(p, "vm.state", 2, state="stopping")                       # no change: nothing
    got = [e for e in publish(p) if e["type"] == "instance.state-changed"]
    assert [(e["data"]["from"], e["data"]["to"]) for e in got] == [(None, "running"), ("running", "stopping")]
    e = got[1]
    assert e["source"] == "projection:instance" and e["item"] == "web" and e["causedby"] == b["id"]
    assert e["time"] == T0 + 1                                    # the causing event's own time
    d = e["data"]
    assert d["projection"] == "instance" and d["key"] == {"name": "web"} and d["name"] == "vm web"
    assert d["cause"] == {"id": b["id"], "time": T0 + 1} and d["version"] == p.model.spec.items["instance"].emit_version
    assert got[0]["causedby"] == a["id"]


def test_a_condition_is_published_on_its_edges_only(tmp_path):
    p = project(tmp_path)
    started(p)
    for i, ms in enumerate([100, 600, 700, 800, 200, 100, None]):
        add(p, "vm.latency", i, ms=ms)
    got = [e for e in publish(p) if e["type"].startswith("instance.slow")]
    assert [e["type"] for e in got] == ["instance.slow", "instance.slow-cleared"]
    assert got[0]["data"]["fields"] == {"latency_ms": 600} and got[1]["data"]["fields"] == {"latency_ms": 200}


def test_a_computed_fields_transitions(tmp_path):
    p = project(tmp_path)
    started(p)
    add(p, "vm.count", 0, desired=2, running=0)
    add(p, "vm.count", 1, desired=2, running=1)
    add(p, "vm.count", 2, desired=2, running=2)
    got = [(e["data"]["from"], e["data"]["to"]) for e in publish(p) if e["type"] == "instance.health-changed"]
    assert got == [(None, "empty"), ("empty", "some"), ("some", "full")]


def test_a_rebuild_after_the_definition_changes_publishes_nothing_for_the_past(tmp_path):
    p = project(tmp_path)
    started(p)
    add(p, "vm.latency", 0, ms=600)
    assert len(publish(p, "instance.slow")) == 1
    (tmp_path / "ergostat.yaml").write_text(body(EMIT.replace("> 500", "> 50")))
    p2 = Project(mdl.load(tmp_path))
    add(p2, "vm.latency", 1, ms=60)                               # recorded before the new definition's index is made
    assert len(publish(p2, "instance.slow")) == 1                 # the refold publishes nothing
    add(p2, "vm.latency", 2, ms=40)                               # live, under the new one: cleared
    got = publish(p2, "instance.slow")
    assert [e["type"] for e in got] == ["instance.slow", "instance.slow-cleared"]
    assert got[1]["data"]["version"] != got[0]["data"]["version"]


def test_catch_up_publishes_once_and_a_replay_never_doubles(tmp_path):
    p = project(tmp_path)
    started(p)
    add(p, "vm.state", 0, state="running")                        # recorded while nothing folds: caught up later
    add(p, "vm.state", 1, state="stopped")
    assert len(publish(p)) == 3                                   # (its health, empty, as it arrives: once)
    ix = itemindex.index_for(p.events, p.model.spec, False)
    rows = [e for e in p.events.query(n=None) if emit.emitted(e)]
    with ix.lock:                                                 # a crash after recording, before the outbox emptied
        import json
        ix.db.executemany("insert into emits(projection, ev) values (?, ?)",
                          [("instance", json.dumps({**{k: e[k] for k in ("id", "type", "item", "source", "causedby", "data")},
                                                    "at": e["time"]})) for e in rows])
    assert len(publish(p)) == 3
    ix.close()
    itemindex._OPEN.clear()                                       # another process, the same index file
    assert len(publish(p)) == 3


def test_out_of_order_events_publish_the_change_as_the_fold_sees_it(tmp_path):
    p = project(tmp_path)
    started(p)
    add(p, "vm.state", 5, state="running")
    add(p, "vm.state", 2, state="pending", recorded=6)            # older, late: the fold does not take it
    add(p, "vm.state", 9, state="stopped", recorded=7)
    got = [(e["data"]["from"], e["data"]["to"]) for e in publish(p) if e["type"] == "instance.state-changed"]
    assert got == [(None, "running"), ("running", "stopped")]


def test_projections_do_not_read_emitted_events_unless_their_query_names_the_source(tmp_path):
    extra = """\
  watcher:
    query: type.startswith('instance.')
    key: id
    fields: {id: text, seen: {type: integer, fold: add}}
    events:
      any: {when: true, id: data.id, seen: 1}
  named:
    query: source == 'projection:instance'
    key: id
    fields: {id: text, seen: {type: integer, fold: add}}
    events:
      any: {when: true, id: data.id, seen: 1}
"""
    p = project(tmp_path, extra=extra)
    started(p)
    add(p, "vm.state", 0, state="running")
    assert publish(p)
    assert its.project(p.events, p.model.spec, "watcher") == []
    named = its.project(p.events, p.model.spec, "named")
    assert [(i.id, i.fields["seen"]) for i in named] == [("web", 2)]          # its state and its health
    assert [i.id for i in its.project(p.events, p.model.spec, "instance")] == ["web"]


@pytest.mark.parametrize("change, code, says", [
    ("      wobble: transitions\n", "bad-emit", "not one of its fields"),
    ("      latency_ms: transitions\n", "bad-emit", "values:"),
    ("      slow: latency_ms >\n", "bad-emit", "parse"),
    ("      slow: data.ms > 5\n", "bad-emit", "data is the event's"),
    ("      state: transitions\n      state-changed: latency_ms > 1\n", "emit-collision", "state-changed"),
])
def test_check_errors(tmp_path, change, code, says):
    got = errors(tmp_path, body(change))
    assert any(c == code and says in m for c, m in got), got


def test_a_query_reading_its_own_emitted_events_is_a_loop(tmp_path):
    text = body().replace("query: type.startswith('vm.')", "query: type.startswith('vm.') or source == 'projection:instance'")
    assert any(c == "emit-loop" for c, _ in errors(tmp_path, text))


def test_the_good_model_checks_and_a_trigger_on_an_emitted_type_is_known(tmp_path):
    blocks = """\
blocks:
  pager:
    type: program
    on: {event: instance.slow, emits: [page.sent]}
    run: "true"
  typo:
    type: program
    on: {event: instance.slwo, emits: [page.sent]}
    run: "true"
"""
    assert errors(tmp_path, body(extra=blocks)) == []
    found = errors(tmp_path, body(extra=blocks), "finding")
    unknown = [m for c, m in found if c == "unknown-event"]
    assert len(unknown) == 1 and "instance.slwo" in unknown[0] and "instance.slow" in unknown[0]


def test_the_review_counts_what_each_entry_would_publish(tmp_path):
    p = project(tmp_path)
    for i, ms in enumerate([100, 600, 700, 200, 900]):
        add(p, "vm.latency", i, ms=ms)
    add(p, "vm.state", 0, state="running", name="db")
    defn = body().split("instance:\n", 1)[1]
    r = workbench.review(p, {"name": "instance", "yaml": textwrap.dedent(defn)})
    assert r["ok"], r
    by = {x["entry"]: x for x in r["emits"]}
    assert by["slow"]["types"] == {"instance.slow": 2, "instance.slow-cleared": 1} and by["slow"]["objects"] == 1
    assert by["state"]["types"] == {"instance.state-changed": 2}           # each arrives
    assert not [e for e in p.events.query(n=None) if emit.emitted(e)]          # nothing published
    from ergostat.cli.trying import review_text
    assert "emit       slow: instance.slow 2, instance.slow-cleared 1" in review_text(r)


def test_publishing_costs_per_change_not_the_records_age(tmp_path):
    p = project(tmp_path)
    started(p)
    many = [{"type": "vm.latency", "at": T0 + i, "data": {"name": f"vm{i % 50}", "at": T0 + i, "ms": 100 + (i % 7) * 100}}
            for i in range(20_000)]
    p.events.add_many(many, new=True)
    publish(p)

    def one_batch() -> float:
        t = time.perf_counter()
        for i in range(50):
            add(p, "vm.latency", 30_000 + i, name=f"vm{i}", ms=900)
        publish(p)
        return time.perf_counter() - t
    early = one_batch()
    p.events.add_many([{**e, "at": e["at"] + 40_000, "data": {**e["data"], "at": e["data"]["at"] + 40_000}} for e in many],
                      new=True)
    publish(p)
    late = one_batch()
    assert late < max(0.5, early * 4), (early, late)


def test_a_block_is_started_by_an_emitted_event(tmp_path):
    from ergostat.spec.engine import Engine
    blocks = """\
blocks:
  pager:
    type: program
    on: {event: instance.slow, emits: [page.sent]}
    run: "echo '{\\"event\\": \\"page.sent\\"}'"
"""
    p = project(tmp_path, extra=blocks)
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        time.sleep(0.3)
        now = time.time()
        p.events.add("vm.latency", data={"name": "web", "at": now, "ms": 900}, at=now)
        end = time.time() + 20
        while time.time() < end and not p.events.query(n=None, type="agent.started", item="pager"):
            time.sleep(0.05)
        runs = p.events.query(n=None, type="agent.started", item="pager")
        assert runs, [x["type"] for x in p.events.query(n=None)]
        slow = p.events.query(n=None, type="instance.slow")
        assert runs[0]["causedby"] == slow[0]["id"]
    finally:
        e.close()
