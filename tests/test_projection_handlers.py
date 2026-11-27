"""A projection's handlers (spec/handlers.py, SPEC §5a): which events it reads (match:), the item each belongs to
(key:), and what each event type does to the item, field by field, as an expression."""

from __future__ import annotations

import textwrap

import pytest

from ergostat import model as mdl
from ergostat.library.templates import TemplateError
from ergostat.library.templates import read as read_template
from ergostat.spec import handlers as h
from ergostat.spec import itemindex
from ergostat.spec import items as its
from ergostat.store import Project

T0 = 1_700_000_000.0

MISSION = """
projections:
  mission:
    query: type.startswith('mission.')
    key: key
    fields:
      state:
        values: [planned, ongoing, done]
      last_seen: {}
      name: {}
      crew: {}
      retry_count: {}
      last_error: {}
      errors: {}
      completed_at: {}
      outcome: {}
      turpitude: {}
      drift: {}
      low: {}
      high: {}
      mean: {}
      var: {}
      sd: {}
      reads: {}
      firstread: {}
      tags: {}
    events:
      mission-planned:
        when: type == 'mission.planned'
        last_seen: time
        state: set('planned')
        name: data.name
        crew: data.crew
      mission-started:
        when: type == 'mission.started'
        last_seen: time
        state: set('ongoing')
      mission-retried:
        when: type == 'mission.retried'
        last_seen: time
        retry_count: add(1)
        last_error: data.reason
        errors: append(data.reason, 2)
      mission-joined:
        when: type == 'mission.joined'
        last_seen: time
        crew: union(data.member)
      mission-left:
        when: type == 'mission.left'
        last_seen: time
        crew: remove(data.member)
      mission-completed:
        when: type == 'mission.completed'
        last_seen: time
        state: set('done')
        completed_at: time
        outcome: data.outcome
      mission-read:
        when: type == 'mission.read'
        last_seen: time
        turpitude: rms(data.turpitude)
        drift: add(data.turpitude)
        low: min(data.turpitude)
        high: max(data.turpitude)
        mean: mean(data.turpitude)
        var: variance(data.turpitude)
        sd: stdev(data.turpitude)
        reads: count()
        firstread: first(data.turpitude)
      mission-tagged:
        when: type == 'mission.tagged'
        last_seen: time
        tags: merge(data.tags)
      mission-cleared:
        when: type == 'mission.cleared'
        last_seen: time
        outcome: unset()
      other:
        when: true
        '...': data
        last_seen: time
"""


def _project(tmp_path, body: str, extra_files: dict | None = None):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(body))
    for n, t in (extra_files or {}).items():
        (tmp_path / n).write_text(textwrap.dedent(t))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(e) for e in m.errors]
    return Project(m)


def _errors(tmp_path, body: str, extra_files: dict | None = None) -> str:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(body))
    for n, t in (extra_files or {}).items():
        (tmp_path / n).write_text(textwrap.dedent(t))
    try:
        m = mdl.load(tmp_path)
    except mdl.ModelError as e:
        return str(e)
    return "\n".join(str(e) for e in m.errors)


def _items(p, kind=None) -> dict:
    return {i.id: i for i in its.project(p.events, p.model.spec, kind)}


def _fresh(p) -> dict:
    return {(i.kind, i.id): (i.state, i.fields, i.n, [(m["from"], m["to"]) for m in i.moves])
            for i in its.fold_all(p.events, p.model.spec, None, None, False)}


def _indexed(p) -> dict:
    out = {}
    for i in its.project(p.events, p.model.spec):
        full = its.one(p.events, p.model.spec, i.id, i.kind) if i.kind else None
        out[(i.kind, i.id)] = (i.state, i.fields, i.n, [(m["from"], m["to"]) for m in (full.moves if full else [])])
    return out


def test_each_built_in_and_value_form(tmp_path):
    p = _project(tmp_path, MISSION)
    a = lambda t, data=None, at=0: p.events.add(t, item="mission/1", data=data or {}, at=T0 + at)   # noqa: E731
    a("mission.planned", {"name": "apollo", "crew": ["a"]})
    a("mission.started", at=1)
    a("mission.retried", {"reason": "x"}, at=2)
    a("mission.retried", {"reason": "y"}, at=3)
    a("mission.retried", {"reason": "z"}, at=4)
    a("mission.joined", {"member": "b"}, at=5)
    a("mission.left", {"member": "a"}, at=6)
    for i, x in enumerate([3.0, 4.0]):
        a("mission.read", {"turpitude": x}, at=7 + i)
    a("mission.tagged", {"tags": {"k": 1}}, at=9)
    a("mission.completed", {"outcome": "ok"}, at=10)
    it = _items(p)["mission/1"]
    f = it.fields
    assert it.state == "done"
    assert [m["to"] for m in it.moves] == ["planned", "ongoing", "done"]
    assert f["name"] == "apollo" and f["crew"] == ["b"]
    assert f["retry_count"] == 3 and f["last_error"] == "z" and f["errors"] == ["y", "z"]
    assert f["drift"] == 7.0 and f["low"] == 3.0 and f["high"] == 4.0 and f["mean"] == 3.5
    assert f["var"] == pytest.approx(0.5) and f["sd"] == pytest.approx(0.5 ** 0.5)
    assert f["turpitude"] == pytest.approx(((9 + 16) / 2) ** 0.5)
    assert f["reads"] == 2 and f["firstread"] == 3.0
    assert f["tags"] == {"k": 1} and f["outcome"] == "ok" and f["completed_at"] == T0 + 10
    assert f["last_seen"] == T0 + 10                         # "*": on every event, before the type's own handler
    assert "state" not in f                                  # the state is the item's, not a field
    a("mission.cleared", at=11)
    assert "outcome" not in _items(p)["mission/1"].fields


def test_a_state_move_is_counted(tmp_path):
    p = _project(tmp_path, MISSION + """
stocks:
  ongoing:
    sensor: {projection: mission, state: ongoing}
""")
    p.events.add("mission.planned", item="mission/1", data={}, at=T0)
    p.events.add("mission.started", item="mission/1", data={}, at=T0 + 1)
    p.events.add("mission.planned", item="mission/2", data={}, at=T0 + 2)
    n, _, _ = its.in_states(p.events, p.model.spec, "mission", ["ongoing"])
    assert n == 1
    assert its.moved(p.events, p.model.spec, "mission", "to", "ongoing", T0, T0 + 10) == [T0 + 1]
    assert p.model.spec.items["mission"].on == {"mission.planned": "planned", "mission.started": "ongoing",
                                                "mission.completed": "done"}


def test_match_by_type_glob_and_by_a_data_field_and_a_composite_key(tmp_path):
    p = _project(tmp_path, """
projections:
  instance:
    query: source == 'aws' and data['detail-type'] == 'EC2 Instance State-change Notification'
    key: [data.region, "data.detail['instance-id']"]
    fields:
      status: {}
      region: {}
    events:
      other:
        when: true
        '...': data
        status: data.detail.state
        region: data["region"]
  noted:
    query: type.startswith('note.')
""")
    ev = lambda st, at, region="eu-west-1", src="aws": p.events.add(   # noqa: E731
        "aws.ec2", source=src, at=T0 + at,
        data={"detail-type": "EC2 Instance State-change Notification", "region": region,
              "detail": {"instance-id": "i-1", "state": st}})
    ev("pending", 0)
    ev("running", 1)
    ev("running", 2, region="us-east-1")
    ev("stopped", 3, src="gcp")                               # another source: not read
    p.events.add("note.added", item="note/1", data={"text": "hi"}, at=T0 + 4)
    p.events.add("other.thing", item="note/2", data={"text": "no"}, at=T0 + 5)
    got = _items(p, "instance")
    assert set(got) == {"eu-west-1/i-1", "us-east-1/i-1"}
    assert got["eu-west-1/i-1"].fields["status"] == "running" and got["eu-west-1/i-1"].n == 2
    assert got["eu-west-1/i-1"].fields["region"] == "eu-west-1"
    assert set(_items(p, "noted")) == {"note/1"}
    one = its.one(p.events, p.model.spec, "eu-west-1/i-1", "instance")
    assert one.fields["status"] == "running"
    assert _indexed(p) == _fresh(p)                           # catch-up == rebuild


def test_expressions_current_arithmetic_brackets_and_a_missing_field(tmp_path):
    p = _project(tmp_path, """
projections:
  t:
    query: key.startswith('t/')
    fields:
      n: {}
      late: {}
      region: {}
      gone: {}
      both: {}
      word: {}
      dollar: {}
      nine: {}
      yes: {}
      modded: {}
      inn: {}
    events:
      t-x:
        when: type == 't.x'
        n: (current or 0) + 1
        late: time - data.planned_at > 3600
        region: data["aws-region"]
        gone: data.no.such.path
        both: data.a * 2 if data.a != null and not false else -1
        word: set('add(data.blah)')
        dollar: "'$5'"
        nine: 9
        yes: true
        modded: 7 % 3 + 2 ** 3 - 10 // 3
        inn: "'b' in data.list"
      other:
        when: true
""")
    p.events.add("t.x", item="t/1", data={"planned_at": T0 - 7200, "aws-region": "eu", "a": 2, "list": ["b"]}, at=T0)
    p.events.add("t.x", item="t/1", data={"planned_at": T0, "list": []}, at=T0 + 1)
    f = _items(p)["t/1"].fields
    assert f["n"] == 2 and f["late"] is False and f["region"] is None and f["gone"] is None
    assert f["both"] == -1 and f["word"] == "add(data.blah)" and f["dollar"] == "$5"
    assert f["nine"] == 9 and f["yes"] is True and f["modded"] == 1 + 8 - 3 and f["inn"] is False


@pytest.mark.parametrize("value, says", [
    ("planned", "planned is not a name: write set('planned') for the text"),
    ("data.__class__", "starting with _"),
    ("__import__('os')", "__import__() is not a fold function"),
    ("[x for x in data]", "ListComp is not allowed"),
    ("lambda: 1", "Lambda is not allowed"),
    ("len(data)", "len() is not a fold function"),
    ("data.a.b()", "the methods a value has are"),
    ("add(1, 2)", "add takes 1 argument, not 2"),
    ("add(x=1)", "without names"),
    ("data[1:2]", "slices are not allowed"),
    ("add(", "does not parse"),
    ("1 if mean(data.x) else 2", "it is the whole expression"),
    ("data.a @ data.b", "MatMult is not allowed"),
    ("(data).a.__dict__", "starting with _"),
    ("current.x()", "the methods a value has are"),
])
def test_what_an_expression_may_not_do(value, says):
    with pytest.raises(h.BadExpr, match=None) as e:
        h.compile_value(value)
    assert says in str(e.value)


@pytest.mark.parametrize("node", ["1 + 2", "-data.a", "not data.a", "data.a and data.b or data.c", "1 < data.a <= 3",
                                  "data.a if data.b else data.c", "data['x-y'][0]", "add(1)", "'t'", "null", "True",
                                  "None", "current", "key", "type", "source", "time", "data.a in data.b"])
def test_what_an_expression_may_do(node):
    h.compile_value(node)


def test_check_errors_a_bare_word_an_unknown_state_and_a_function(tmp_path):
    out = _errors(tmp_path, """
projections:
  t:
    fields:
      state:
        values: [a, b]
      n: {}
    events:
      t-x:
        when: type == 't.x'
        state: b
      t-y:
        when: type == 't.y'
        state: set('c')
      t-z:
        when: type == 't.z'
        n: ewma(data.x, 0.1)
      other:
        when: true
        '...': data
""")
    assert "events.t-x.state: b is not a name: write set('b') for the text" in out
    assert "'c' is not one of its values" in out
    assert "ewma() is not a fold function" in out


def test_a_state_from_the_event_not_among_its_states_refuses_the_event(tmp_path):
    p = _project(tmp_path, """
projections:
  t:
    fields:
      state:
        values: [a, b]
      seen: {}
    events:
      t-x:
        when: type == 't.x'
        state: data.to
        seen: add(1)
      other:
        when: true
        '...': data
""")
    p.events.add("t.x", item="t/1", data={"to": "b"}, at=T0)
    p.events.add("t.x", item="t/1", data={"to": "zz"}, at=T0 + 1)
    it = its.one(p.events, p.model.spec, "t/1", "t")
    assert it.state == "b" and it.fields == {"seen": 1}
    assert "'zz'" in it.refused[0]["why"] or "zz" in it.refused[0]["why"]


FOLDS = """
def ewma(current, x, alpha):
    return x if current is None else current + alpha * (x - current)


def boom(current, x):
    raise ValueError("no " + str(x))
"""


def test_a_user_function_and_its_refusal_and_a_refold_when_its_file_changes(tmp_path):
    body = """
functions: [folds.py]
projections:
  t:
    fields:
      avg: {}
    events:
      t-x:
        when: type == 't.x'
        avg: ewma(data.x, 0.5)
      t-bad:
        when: type == 't.bad'
        avg: boom(data.x)
      other:
        when: true
        '...': data
"""
    p = _project(tmp_path, body, {"folds.py": FOLDS})
    p.events.add("t.x", item="t/1", data={"x": 10}, at=T0)
    p.events.add("t.x", item="t/1", data={"x": 20}, at=T0 + 1)
    p.events.add("t.bad", item="t/1", data={"x": 3}, at=T0 + 2)
    it = _items(p)["t/1"]
    assert it.fields["avg"] == 15.0
    assert "boom: ValueError: no 3" in it.refused[0]["why"]
    ix = itemindex.index_for(p.events, p.model.spec, False)
    (tmp_path / "folds.py").write_text(FOLDS.replace("alpha * (x - current)", "(x - current)"))
    p2 = Project(mdl.load(tmp_path))
    assert itemindex.index_for(p2.events, p2.model.spec, False).path != ix.path      # another fold: another index
    assert _items(p2)["t/1"].fields["avg"] == 20.0


def test_user_function_errors(tmp_path):
    for name, body, files, says in [
        ("arity", "functions: [folds.py]\nprojections:\n  t:\n    fields:\n      a: {}\n    events:\n      t-x:\n        when: type == 't.x'\n        a: ewma(data.x)\n      other:\n        when: true\n        '...': data\n",
         {"folds.py": FOLDS}, "does not fit it"),
        ("unknown", "functions: [folds.py]\nprojections:\n  t:\n    fields:\n      a: {}\n    events:\n      t-x:\n        when: type == 't.x'\n        a: nope(1)\n      other:\n        when: true\n        '...': data\n",
         {"folds.py": FOLDS}, "nope() is not a fold function"),
        ("shadow", "functions: [folds.py]\nprojections:\n  t:\n    fields:\n      a: {}\n    events:\n      t-x:\n        when: type == 't.x'\n        a: add(1)\n      other:\n        when: true\n        '...': data\n",
         {"folds.py": "def add(current, x):\n    return 0\n"}, "add is a built-in fold function"),
        ("loads", "functions: [folds.py]\n", {"folds.py": "def x(:\n"}, "folds.py does not load"),
        ("missing", "functions: [gone.py]\n", {}, "gone.py: cannot be read"),
    ]:
        d = tmp_path / name
        d.mkdir()
        assert says in _errors(d, body, files), name


def test_a_template_may_not_bring_functions(tmp_path):
    f = tmp_path / "t.yaml"
    f.write_text("template: t\nfunctions: [x.py]\n")
    with pytest.raises(TemplateError, match="unknown section 'functions'"):
        read_template(f, builtin=False)
    inc = tmp_path / "m"
    inc.mkdir()
    (inc / "more.yaml").write_text("functions: [x.py]\n")
    assert "functions: belongs in the main file only" in _errors(inc, "include: [more.yaml]\n")


def test_a_block_line_may_say_key(tmp_path):
    from ergostat.runner import keyed
    assert keyed({"event": "a.b", "key": "t/1"}) == ({"event": "a.b", "item": "t/1"}, None)
    assert keyed({"event": "a.b", "key": "t/1", "item": "t/1"})[1] is None
    assert "both, differently" in keyed({"event": "a.b", "key": "t/1", "item": "t/2"})[1]


def test_catch_up_equals_rebuild(tmp_path):
    p = _project(tmp_path, MISSION)
    for i in range(30):
        p.events.add(["mission.planned", "mission.retried", "mission.read", "mission.started"][i % 4],
                     item=f"mission/{i % 5}", data={"reason": str(i), "turpitude": float(i), "name": f"n{i}"}, at=T0 + i)
        if i % 7 == 0:
            assert _indexed(p) == _fresh(p)
    itemindex.reindex(p.events, p.model.spec)
    assert _indexed(p) == _fresh(p)


SPREAD = """
projections:
  m:
    fields:
      state:
        values: [planned, ongoing]
      retry_count: {}
      started_by: {}
      n: {}
      region: {}
      seen: {}
    events:
      m-planned:
        when: type == 'm.planned'
        "...": data
        state: set('planned')
        retry_count: 0
      m-updated:
        when: type == 'm.updated'
        "...": pick(data, 'name', 'crew')
        started_by: data.by
      m-secret:
        when: type == 'm.secret'
        "...": omit(data, 'secret')
      m-renamed:
        when: type == 'm.renamed'
        "...": rename(data, by='started_by')
      m-counted:
        when: type == 'm.counted'
        "...": data
        n: add(data.n)
      m-nested:
        when: type == 'm.nested'
        "...": data.detail
        region: data["aws-region"]
      m-bad:
        when: type == 'm.bad'
        "...": data.n
      m-none:
        when: type == 'm.none'
        "...": data.missing
        seen: 1
      other:
        when: true
"""


def test_a_spread_and_its_helpers(tmp_path):
    p = _project(tmp_path, SPREAD)
    a = lambda t, d, at: p.events.add(t, item="m/1", data=d, at=T0 + at)   # noqa: E731
    a("m.planned", {"name": "x", "retry_count": 5, "extra": 1}, 0)
    it = its.one(p.events, p.model.spec, "m/1", "m")
    assert it.state == "planned" and it.fields == {"name": "x", "retry_count": 0, "extra": 1}   # what follows wins
    a("m.updated", {"name": "y", "crew": ["a"], "other": 1, "by": "me"}, 1)
    assert its.one(p.events, p.model.spec, "m/1", "m").fields == {"name": "y", "retry_count": 0, "extra": 1, "crew": ["a"],
                                                                  "started_by": "me"}
    a("m.secret", {"secret": "s", "public": 1}, 2)
    a("m.renamed", {"by": "you"}, 3)
    a("m.counted", {"n": 2, "k": 1}, 4)
    a("m.counted", {"n": 3, "k": 2}, 5)
    a("m.nested", {"detail": {"state": "running", "deep": {"a": 1}}, "aws-region": "eu"}, 6)
    f = its.one(p.events, p.model.spec, "m/1", "m").fields
    assert "secret" not in f and f["public"] == 1 and f["started_by"] == "you"
    assert f["k"] == 2 and f["n"] == 5                        # the entry's own n wins over the spread's: 2 + 3
    assert f["deep"] == {"a": 1} and f["region"] == "eu"
    a("m.bad", {"n": 3}, 7)
    a("m.none", {}, 8)
    it = its.one(p.events, p.model.spec, "m/1", "m")
    assert "a spread takes an object" in it.refused[-1]["why"]
    assert it.fields["seen"] == 1                             # a null spread does nothing; the rest applies


def test_helpers_may_not_take_other_keywords():
    with pytest.raises(h.BadExpr, match="names are given as text"):
        h.compile_value("pick(data, a='b')")
    h.compile_value("rename(pick(data, 'a'), a='b')")
