"""Computed fields (SPEC §5a, *Computed fields*): a field's ``from:``, an expression over the object's other fields
worked out after each event is folded, its changes recorded as any field's; a computed ``state``'s are moves."""

from __future__ import annotations

import textwrap

import pytest

from ergostat import model as mdl
from ergostat.spec import itemindex, workbench
from ergostat.spec import items as its
from ergostat.store import Project

T0 = 1_700_000_000.0

STATE = """\
      'stopped'  if running == 0 and stop_requested else
      'stopping' if stop_requested else
      'pending'  if running == 0 else
      'degraded' if running < desired else
      'running'
"""

BODY = """\
projections:
  service:
    query: type.startswith('svc.')
    key: name
    time: data.at
    fields:
      name: text
      desired: {type: integer}
      running: {type: integer}
      stop_requested: {type: boolean}
      state:
        values: [pending, running, degraded, stopping, stopped]
        from: |
STATE
      short: {type: integer, from: "desired - running if desired != null and running != null else null"}
      health: {values: [ok, low], from: "'low' if short and short > 0 else 'ok'"}
    defaults:
      name: data.name
    events:
      scaled:
        when: type == 'svc.scaled'
        desired: data.desired
      counted:
        when: type == 'svc.counted'
        running: data.running
      stop:
        when: type == 'svc.stop'
        stop_requested: true
EXTRA
"""


def body(extra: str = "") -> str:
    state = textwrap.indent(STATE, "    ")
    return BODY.replace("STATE\n", state).replace("EXTRA\n", extra)


def project(tmp_path, extra: str = "") -> Project:
    (tmp_path / "ergostat.yaml").write_text(body(extra))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(e) for e in m.errors]
    return Project(m)


def errors(tmp_path, text: str) -> list[tuple[str, str]]:
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(text)
    _, problems = read(tmp_path / "ergostat.yaml", extremes=False)
    return [(x.code, x.message) for x in problems if x.level == "error"]


def add(p, t: str, at: float, **data):
    p.events.add(t, data={"name": "web", "at": T0 + at, **data}, at=T0 + at)


def items(p) -> dict:
    return {i.id: i for i in its.project(p.events, p.model.spec, "service")}


def test_the_state_is_worked_out_from_the_other_fields(tmp_path):
    p = project(tmp_path)
    add(p, "svc.scaled", 0, desired=3)
    add(p, "svc.counted", 1, running=0)
    add(p, "svc.counted", 2, running=2)
    add(p, "svc.counted", 3, running=3)
    add(p, "svc.stop", 4)
    add(p, "svc.counted", 5, running=0)
    it = its.one(p.events, p.model.spec, "web", "service")
    assert it.state == "stopped"
    assert [m["to"] for m in it.moves] == ["pending", "degraded", "running", "stopping", "stopped"]
    assert [m["time"] for m in it.moves][1:] == [T0 + 2, T0 + 3, T0 + 4, T0 + 5]
    assert "state" not in it.fields                              # the state is the item's, as an event-written one


def test_a_computed_field_reads_another_and_its_changes_are_kept(tmp_path):
    p = project(tmp_path)
    add(p, "svc.scaled", 0, desired=3)
    add(p, "svc.counted", 1, running=1)
    it = items(p)["web"]
    assert it.fields["short"] == 2 and it.fields["health"] == "low"
    add(p, "svc.counted", 2, running=3)
    it = items(p)["web"]
    assert it.fields["short"] == 0 and it.fields["health"] == "ok"
    full = its.fold("web", sorted(p.events.query(n=None, type="svc.*"), key=lambda e: e["time"]),
                    p.model.spec.items["service"], history=True)
    health = [(c["before"], c["after"], c["rule"]) for c in full.changes if c["path"] == "/health"]
    assert health == [(None, "ok", "computed"), ("ok", "low", "computed"), ("low", "ok", "computed")]


def test_its_moves_are_counted_by_a_sensor_and_out_of_order_events_fold_by_event_time(tmp_path):
    p = project(tmp_path, """\
stocks:
  degraded:
    sensor: {projection: service, state: degraded}
""")
    add(p, "svc.scaled", 0, desired=3)
    add(p, "svc.counted", 2, running=2)                          # degraded
    p.events.add("svc.counted", data={"name": "web", "at": T0 + 1, "running": 3}, at=T0 + 3)   # older, late: not taken
    n, _, _ = its.in_states(p.events, p.model.spec, "service", ["degraded"])
    assert n == 1
    assert its.moved(p.events, p.model.spec, "service", "to", "degraded", T0, T0 + 10) == [T0 + 2]
    add(p, "svc.counted", 4, running=3)
    assert its.in_states(p.events, p.model.spec, "service", ["degraded"])[0] == 0
    assert its.moved(p.events, p.model.spec, "service", "from", "degraded", T0, T0 + 10) == [T0 + 4]
    p.events.add("svc.counted", data={"name": "web", "at": T0 + 4, "running": 3}, at=T0 + 5)   # delivered twice
    assert [m["to"] for m in its.one(p.events, p.model.spec, "web", "service").moves] == ["pending", "degraded", "running"]


def test_two_projections_over_the_same_events_with_their_own_states(tmp_path):
    p = project(tmp_path, """\
  capacity:
    query: type.startswith('svc.')
    key: name
    fields:
      name: text
      desired: integer
      running: integer
      state:
        values: [empty, some, full]
        from: "'empty' if not running else 'full' if running >= desired else 'some'"
    defaults: {name: data.name}
    events:
      scaled: {when: "type == 'svc.scaled'", desired: data.desired}
      counted: {when: "type == 'svc.counted'", running: data.running}
""")
    add(p, "svc.scaled", 0, desired=2)
    add(p, "svc.counted", 1, running=1)
    add(p, "svc.counted", 2, running=2)
    a = its.one(p.events, p.model.spec, "web", "service")
    b = its.one(p.events, p.model.spec, "web", "capacity")
    assert [m["to"] for m in a.moves] == ["pending", "degraded", "running"]
    assert [m["to"] for m in b.moves] == ["empty", "some", "full"]


def test_a_value_not_among_its_values_refuses_the_event(tmp_path):
    p = project(tmp_path, """\
  odd:
    query: type == 'svc.scaled'
    key: name
    fields:
      name: text
      desired: integer
      size: {values: [small, big], from: "'small' if desired < 3 else 'huge' if desired > 9 else 'big'"}
    defaults: {name: data.name}
    events:
      scaled: {when: true, desired: data.desired}
""")
    add(p, "svc.scaled", 0, desired=2)
    add(p, "svc.scaled", 1, desired=12)
    it = its.one(p.events, p.model.spec, "web", "odd")
    assert it.fields["size"] == "small" and it.fields["desired"] == 2       # the whole event refused
    assert it.refused and "huge" in it.refused[-1]["why"] and "from:" in it.refused[-1]["why"]


def test_catch_up_equals_rebuild(tmp_path):
    p = project(tmp_path)
    for i in range(24):
        t = ["svc.scaled", "svc.counted", "svc.counted", "svc.stop"][i % 4]
        add(p, t, i, name=f"s{i % 3}", desired=i % 5, running=i % 4)
    def indexed():
        return {i.id: (i.state, i.fields) for i in its.project(p.events, p.model.spec, "service")}
    def fresh():
        return {i.id: (i.state, i.fields) for i in its.fold_all(p.events, p.model.spec, "service", None, False)}
    assert indexed() == fresh()
    itemindex.reindex(p.events, p.model.spec)
    assert indexed() == fresh()


def test_the_expression_is_in_the_index_key(tmp_path):
    a = project(tmp_path).model.spec
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "ergostat.yaml").write_text(body().replace("'low' if short", "'low' if short and short > 1 or short"))
    b = mdl.load(tmp_path / "b").spec
    assert itemindex.kinds_key(a) != itemindex.kinds_key(b)


@pytest.mark.parametrize("change, code, says", [
    ('short: {type: integer, from: "desired - running', 'computed-cycle', None),
    ('desired: {type: integer}', 'bad-computed', "data is the event's"),
    ('counted:\n        when', 'computed-field', "short is computed"),
    ('short: {type: integer, from:', 'bad-computed', "never folded"),
])
def test_check_errors(tmp_path, change, code, says):
    text = body()
    if code == "computed-cycle":
        text = text.replace("desired - running if desired", "desired - running if health and desired")
    elif "data is" in (says or ""):
        text = text.replace("'low' if short and short > 0", "'low' if data.x")
    elif code == "computed-field":
        text = text.replace("        running: data.running\n", "        running: data.running\n        short: 1\n")
    else:
        text = text.replace("short: {type: integer, from:", "short: {type: integer, fold: add, from:")
    got = errors(tmp_path, text)
    assert any(c == code and (says is None or says in m) for c, m in got), got
    if code == "computed-cycle":
        assert any("short -> health -> short" in m or "health -> short -> health" in m for _, m in got), got


def test_a_kind_writing_the_computed_state_and_a_computed_key_are_errors(tmp_path):
    text = body().replace("        stop_requested: true\n", "        stop_requested: true\n        state: \"'stopped'\"\n")
    assert any(c == "computed-field" for c, _ in errors(tmp_path, text))
    text = body().replace("    key: name\n", "    key: short\n")
    assert any(c == "bad-key" and "computed" in m for c, m in errors(tmp_path, text))


def test_the_good_model_checks(tmp_path):
    assert errors(tmp_path, body()) == []


def test_the_review_counts_computed_fields(tmp_path):
    p = project(tmp_path)
    add(p, "svc.scaled", 0, desired=3)
    add(p, "svc.counted", 1, running=1)
    add(p, "svc.counted", 2, running=3)
    defn = body().split("service:\n", 1)[1]
    r = workbench.review(p, {"name": "service", "yaml": textwrap.dedent(defn)})
    assert r["ok"], r
    lives = r["lifecycles"]
    assert {(t["from"], t["to"]) for t in lives["state"]["transitions"]} >= {("pending", "degraded"), ("degraded", "running")}
    assert {(t["from"], t["to"]) for t in lives["health"]["transitions"]} == {(None, "ok"), ("ok", "low"), ("low", "ok")}
    short = next(f for f in r["fields"] if f["field"] == "short")
    assert short["have"] == 1 and short.get("computed") is True
