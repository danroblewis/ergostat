"""Changesets (SPEC §5a): an event changes its item by a JSON Patch, a whole new document (set), or
plain data folded by its kind's rules; a changeset that cannot apply is refused whole, with why;
every change is kept, per path, and an item can be read as it stood at any time."""

import copy
import json
import random
import textwrap
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.spec.changes import fold_event
from ergostat.spec.jsonpatch import PatchError, apply
from ergostat.store import ChangesetError, Project

ROOT = Path(__file__).resolve().parent.parent

# RFC 6902, appendix A: (name, document, patch, result or None for an error)
RFC = [
    ("A.1 adding an object member", {"foo": "bar"}, [{"op": "add", "path": "/baz", "value": "qux"}],
     {"baz": "qux", "foo": "bar"}),
    ("A.2 adding an array element", {"foo": ["bar", "baz"]}, [{"op": "add", "path": "/foo/1", "value": "qux"}],
     {"foo": ["bar", "qux", "baz"]}),
    ("A.3 removing an object member", {"baz": "qux", "foo": "bar"}, [{"op": "remove", "path": "/baz"}], {"foo": "bar"}),
    ("A.4 removing an array element", {"foo": ["bar", "qux", "baz"]}, [{"op": "remove", "path": "/foo/1"}],
     {"foo": ["bar", "baz"]}),
    ("A.5 replacing a value", {"baz": "qux", "foo": "bar"}, [{"op": "replace", "path": "/baz", "value": "boo"}],
     {"baz": "boo", "foo": "bar"}),
    ("A.6 moving a value", {"foo": {"bar": "baz", "waldo": "fred"}, "qux": {"corge": "grault"}},
     [{"op": "move", "from": "/foo/waldo", "path": "/qux/thud"}],
     {"foo": {"bar": "baz"}, "qux": {"corge": "grault", "thud": "fred"}}),
    ("A.7 moving an array element", {"foo": ["all", "grass", "cows", "eat"]}, [{"op": "move", "from": "/foo/1", "path": "/foo/3"}],
     {"foo": ["all", "cows", "eat", "grass"]}),
    ("A.8 testing a value: success", {"baz": "qux", "foo": ["a", 2, "c"]},
     [{"op": "test", "path": "/baz", "value": "qux"}, {"op": "test", "path": "/foo/1", "value": 2}],
     {"baz": "qux", "foo": ["a", 2, "c"]}),
    ("A.9 testing a value: error", {"baz": "qux"}, [{"op": "test", "path": "/baz", "value": "bar"}], None),
    ("A.10 adding a nested member object", {"foo": "bar"}, [{"op": "add", "path": "/child", "value": {"grandchild": {}}}],
     {"foo": "bar", "child": {"grandchild": {}}}),
    ("A.11 ignoring unrecognized elements", {"foo": "bar"}, [{"op": "add", "path": "/baz", "value": "qux", "xyz": 123}],
     {"foo": "bar", "baz": "qux"}),
    ("A.12 adding to a nonexistent target", {"foo": "bar"}, [{"op": "add", "path": "/baz/bat", "value": "qux"}], None),
    ("A.13 an invalid patch: no op", {"foo": "bar"}, [{"path": "/baz", "value": "qux"}], None),
    ("A.14 ~ escape ordering", {"/": 9, "~1": 10}, [{"op": "test", "path": "/~01", "value": 10}], {"/": 9, "~1": 10}),
    ("A.15 comparing strings and numbers", {"/": 9, "~1": 10}, [{"op": "test", "path": "/~01", "value": "10"}], None),
    ("A.16 adding an array value", {"foo": ["bar"]}, [{"op": "add", "path": "/foo/-", "value": ["abc", "def"]}],
     {"foo": ["bar", ["abc", "def"]]}),
]


@pytest.mark.parametrize("name,doc,patch,want", RFC, ids=[r[0].split(" ")[0] for r in RFC])
def test_json_patch_does_what_rfc_6902_says(name, doc, patch, want):
    was = copy.deepcopy(doc)
    if want is None:
        with pytest.raises(PatchError):
            apply(doc, patch)
        assert doc == was, "a refused patch left the document changed"
    else:
        apply(doc, patch)
        assert doc == want


@pytest.mark.parametrize("patch,why", [
    ([{"op": "remove", "path": "/nope"}], "not there"),
    ([{"op": "replace", "path": "/nope", "value": 1}], "not there"),
    ([{"op": "add", "path": "/list/9", "value": 1}], "past the end"),
    ([{"op": "add", "path": "/list/01", "value": 1}], "not an array index"),
    ([{"op": "remove", "path": "/list/-"}], "not an array index"),
    ([{"op": "add", "path": "no-slash", "value": 1}], "starts with /"),
    ([{"op": "move", "from": "/a", "path": "/a/b"}], "its own child"),
    ([{"op": "copy", "from": "/nope", "path": "/b"}], "not there"),
    ([{"op": "test", "path": "/a", "value": 1}], "not"),           # a boolean is not a number
    ([{"op": "jump", "path": "/a"}], "not an operation"),
    ([{"op": "add", "path": "/x~2", "value": 1}], "escaped"),
])
def test_a_bad_patch_is_refused_with_why_and_never_half_applied(patch, why):
    doc = {"a": True, "list": [1, 2]}
    with pytest.raises(PatchError, match=why):
        apply(doc, [{"op": "add", "path": "/first", "value": 1}, {"op": "add", "path": "/list/-", "value": 3}, *patch])
    assert doc == {"a": True, "list": [1, 2]}, "the operations before the bad one were undone"


def test_copy_and_whole_document_and_what_changed():
    doc = {"a": {"b": [1]}, "n": 1}
    done = apply(doc, [{"op": "copy", "from": "/a", "path": "/c"}, {"op": "add", "path": "/c/b/-", "value": 2},
                       {"op": "replace", "path": "/n", "value": 2}, {"op": "remove", "path": "/a/b/0"}])
    assert doc == {"a": {"b": []}, "c": {"b": [1, 2]}, "n": 2}
    assert [(op, path) for op, path, _, _ in done] == [("copy", "/c"), ("add", "/c/b/1"), ("replace", "/n"), ("remove", "/a/b/0")]
    assert done[0][3] == {"b": [1]}, "what was copied is kept as it was, not as the copy became"
    apply(doc, [{"op": "replace", "path": "", "value": {"x": 1}}])
    assert doc == {"x": 1}
    with pytest.raises(PatchError):
        apply(doc, [{"op": "replace", "path": "", "value": [1]}])


MODEL = """
items:
  ticket:
    id: ticket/*
    states: [open, done]
    on:
      ticket.done: done
    show: [title]
    fold:
      notes: append
      spent: sum
      low: min
      high: max
      tags: union
      meta: merge
      opened_by: first
"""


def project(tmp_path, text=MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


def item(p, id="ticket/1", **kw):
    return its.one(p.events, p.model.spec, id)


def test_each_fold_rule(tmp_path):
    p = project(tmp_path)
    t = time.time() - 100
    for i, d in enumerate([
        {"title": "a", "notes": "first", "spent": 1.5, "low": 5, "high": 5, "tags": ["b", "a"], "meta": {"x": {"y": 1}},
         "opened_by": "ann"},
        {"title": "b", "notes": ["second", "third"], "spent": 2, "low": 3, "high": 9, "tags": "c", "meta": {"x": {"z": 2}, "w": 0},
         "opened_by": "bob"},
        {"notes": "fourth", "spent": 0.5, "low": 4, "high": 1, "tags": ["a", "d"], "meta": {"x": {"y": 7}}},
    ]):
        p.events.add("ticket.noted", item="ticket/1", data=d, at=t + i)
    f = item(p).fields
    assert f["title"] == "b"                                            # replace, the default
    assert f["notes"] == ["first", "second", "third", "fourth"]         # append: a list given is each of its values
    assert f["spent"] == 4.0
    assert f["low"] == 3 and f["high"] == 9
    assert f["tags"] == ["a", "b", "c", "d"]                            # union: a set, sorted
    assert f["meta"] == {"x": {"y": 7, "z": 2}, "w": 0}                 # merge: deep
    assert f["opened_by"] == "ann"                                      # first


def test_a_rule_that_cannot_fold_refuses_the_whole_event(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.noted", item="ticket/1", data={"spent": 1, "title": "a"})
    bad = p.events.add("ticket.noted", item="ticket/1", data={"spent": "lots", "title": "b"})
    it = item(p)
    assert it.fields == {"spent": 1, "title": "a"}, "none of the refused event's data was folded"
    assert it.refused and it.refused[0]["event"] == bad["id"] and "sum needs numbers" in it.refused[0]["why"]
    assert it.n == 2, "the refused event is still in the record, and counted"


def test_set_is_remove_everything_then_add_the_whole_document(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", data={"title": "a", "notes": "x", "spent": 3}, at=1000)
    s = p.events.add("ticket.reset", item="ticket/1", set={"title": "b", "owner": "cy"}, at=1001)
    d = its.detail(p.events, p.model.spec, "ticket/1")
    assert d["fields"] == {"title": "b", "owner": "cy"}
    by = {f: [(c["op"], c["before"], c["after"]) for c in cs if c["event"] == s["id"]] for f, cs in d["history"].items()}
    assert by["title"] == [("remove", "a", None), ("add", None, "b")]
    assert by["spent"] == [("remove", 3, None)] and by["owner"] == [("add", None, "cy")]
    assert all(c["form"] == "set" for cs in d["history"].values() for c in cs if c["event"] == s["id"])
    # the same as the patch it stands for
    doc = {"title": "a", "notes": ["x"], "spent": 3}
    fold_event(doc, {"set": {"title": "b", "owner": "cy"}}, {})
    assert doc == {"title": "b", "owner": "cy"}


def test_a_patch_event_and_its_refusal(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", data={"title": "a"}, at=1000)
    p.events.add("ticket.tagged", item="ticket/1", patch=[{"op": "add", "path": "/labels", "value": []},
                                                         {"op": "add", "path": "/labels/-", "value": "bug"}], at=1001)
    no = p.events.add("ticket.retitled", item="ticket/1", patch=[{"op": "test", "path": "/title", "value": "z"},
                                                                {"op": "replace", "path": "/title", "value": "never"}], at=1002)
    d = its.detail(p.events, p.model.spec, "ticket/1")
    assert d["fields"] == {"title": "a", "labels": ["bug"]}
    assert d["refused"][0]["event"] == no["id"] and d["refused"][0]["form"] == "patch" and "test /title" in d["refused"][0]["why"]
    assert [c["op"] for c in d["history"][""]] == ["refused"]
    assert [(c["op"], c["path"]) for c in d["history"]["labels"]] == [("add", "/labels"), ("add", "/labels/0")]
    assert p.events.get(no["id"])["patch"][0]["op"] == "test", "the record keeps the patch as it was sent"


def test_an_event_changes_its_item_one_way(tmp_path):
    p = project(tmp_path)
    with pytest.raises(ChangesetError):
        p.events.add("ticket.x", item="ticket/1", data={"a": 1}, patch=[{"op": "add", "path": "/b", "value": 1}])
    with pytest.raises(ChangesetError):
        p.events.add("ticket.x", item="ticket/1", patch={"op": "add"})
    with pytest.raises(ChangesetError):
        p.events.add("ticket.x", item="ticket/1", set=[1])
    with pytest.raises(ChangesetError):
        p.events.add("thing.x", item="inbox-short", patch=[{"op": "add", "path": "/b", "value": 1}])


def test_history_per_path_and_the_item_as_of_any_time(tmp_path):
    p = project(tmp_path)
    e1 = p.events.add("ticket.opened", item="ticket/1", data={"title": "a", "notes": "n1", "spent": 1}, at=1000)
    e2 = p.events.add("ticket.noted", item="ticket/1", data={"title": "b", "notes": "n2", "spent": 2}, at=2000)
    p.events.add("ticket.done", item="ticket/1", patch=[{"op": "remove", "path": "/title"}], at=3000)
    d = its.detail(p.events, p.model.spec, "ticket/1")
    assert [(c["op"], c["before"], c["after"], c["event"]) for c in d["history"]["title"]] == [
        ("add", None, "a", e1["id"]), ("replace", "a", "b", e2["id"]), ("remove", "b", None, d["history"]["title"][2]["event"])]
    assert [(c["path"], c["after"], c["rule"]) for c in d["history"]["notes"]] == [
        ("/notes", [], "append"), ("/notes/0", "n1", "append"), ("/notes/1", "n2", "append")]
    assert [(c["before"], c["after"], c["rule"]) for c in d["history"]["spent"]] == [(None, 1, "sum"), (1, 3, "sum")]
    assert d["changes"] == {"title": 3, "notes": 3, "spent": 2}
    then = its.detail(p.events, p.model.spec, "ticket/1", until=2500)          # as it stood at 2500
    assert then["fields"] == {"title": "b", "notes": ["n1", "n2"], "spent": 3} and then["state"] == "open"
    assert len(then["history"]["title"]) == 2
    first = its.detail(p.events, p.model.spec, "ticket/1", until=1500)
    assert first["fields"] == {"title": "a", "notes": ["n1"], "spent": 1}
    assert its.detail(p.events, p.model.spec, "ticket/1", until=500) is None
    # what history holds is what was there then, never what it became later
    assert d["history"]["notes"][0]["after"] == []


def test_fold_rules_are_compile_checked(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("items:\n  t:\n    id: t/*\n    fold:\n      a: apend\n      b: sum\n")
    spec, problems = read(tmp_path / "ergostat.yaml")
    bad = [x for x in problems if x.code == "bad-fold"]
    assert bad and "apend" in bad[0].message and "append" in bad[0].message
    assert spec.items["t"].fold == {"b": "sum"}
    (tmp_path / "ergostat.yaml").write_text("items:\n  t:\n    id: t/*\n    fold: [a]\n")
    _, problems = read(tmp_path / "ergostat.yaml")
    assert any(x.code == "not-a-map" for x in problems)


def _latest_wins(events) -> dict:
    """How items were folded before changesets: each key's latest value."""
    out: dict = {}
    for e in events:
        out.update(e.get("data") or {})
    return out


def _value(r: random.Random, depth=0):
    pick = r.randrange(7 if depth < 2 else 5)
    if pick == 5:
        return [_value(r, depth + 1) for _ in range(r.randrange(3))]
    if pick == 6:
        return {f"k{i}": _value(r, depth + 1) for i in range(r.randrange(3))}
    return [None, r.randint(-5, 5), r.random(), "x" * r.randrange(4), True][pick]


EXAMPLES = sorted(p for p in (ROOT / "examples").iterdir() if (p / "ergostat.yaml").exists())


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_every_examples_items_fold_as_they_did_where_no_rules_were_added(example):
    """With no fold rule, every key replaces its field: each example's kinds, given random events
    carrying their fields (and others), fold exactly as the old latest-wins merge did."""
    spec = mdl.load(example).spec
    r = random.Random(example.name)
    for k in spec.items.values():
        names = [*k.show, *k.formats, "note", "why", "result"]
        plain = [n for n in names if n not in k.fold]
        evs = [{"id": f"e{i}", "time": 1000.0 + i, "type": r.choice([*k.on, "x.y"]),
                "data": {n: _value(r) for n in r.sample(plain, r.randrange(len(plain) + 1))}} for i in range(40)]
        it = its.fold(f"{k.id.rstrip('*')}1", evs, k)
        assert it.fields == _latest_wins(evs), k.name
        # a state rule's refusal only: a final state's, or an event's moves-from: (it bars a move, never a field)
        assert all((x["form"] == "final" and k.final) or (x["form"] == "from" and x["type"] in k.moves_from)
                   for x in it.refused), k.name


def test_the_model_change_kind_folds_as_the_review_queue_read_it(tmp_path):
    """The review queue reads changes to the model through the same fold as every item."""
    from ergostat.numbers import proposals as pr
    p = project(tmp_path)
    pr.event(p, "abc", "made", {"title": "t", "reasons": [{"says": "raw"}], "made_by": "b"})
    pr.event(p, "abc", "checked", {"title": "t", "reasons": [{"says": "raw", "verified": ["ok"]}]})
    pr.event(p, "abc", "passed", {"verdict": {"verdict": "passed", "why": "w1"}})
    st, f = pr.changes(p)["abc"]
    assert st == "passed" and f["reasons"] == [{"says": "raw", "verified": ["ok"]}] and f["verdict"]["why"] == "w1"
    d = its.detail(p.events, p.model.spec, "ergostat.model-change/abc")
    assert [c["after"] for c in d["history"]["reasons"]] == [[{"says": "raw"}], [{"says": "raw", "verified": ["ok"]}]]


def test_the_cli_records_a_patch_and_says_when_it_was_refused(tmp_path, capsys):
    from ergostat.cli import main
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    home = ["-C", str(tmp_path)]
    assert main([*home, "event", "--add", "ticket.opened", "--item", "ticket/1", "--data", '{"title": "a", "spent": 2}']) == 0
    assert main([*home, "event", "--add", "ticket.noted", "--item", "ticket/1", "--data", '{"spent": 3}']) == 0
    assert main([*home, "event", "--add", "ticket.fixed", "--item", "ticket/1",
                 "--patch", '[{"op": "test", "path": "/title", "value": "zz"}]']) == 1
    assert "changed nothing: test /title" in capsys.readouterr().err
    assert main([*home, "event", "--add", "ticket.x", "--item", "ticket/1", "--data", "{}", "--set", '{"a": 1}']) == 0
    capsys.readouterr()
    assert main([*home, "item", "ticket/1", "--history", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["fields"] == {"a": 1} and [c["op"] for c in got["history"]["spent"]] == ["add", "replace", "remove"]
    assert main([*home, "item", "ticket/1", "--history", "spent"]) == 0
    out = capsys.readouterr().out
    assert "spent" in out and "(sum)" in out and "by set" in out
