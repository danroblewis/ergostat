"""Items about parts of the model (SPEC §5a, *About*; spec/about.py): a kind declares the field naming the parts its
items bear on; the item index keeps the links; explain, check and status point at the open items about a part."""

from __future__ import annotations

import io
import json
import re
import textwrap

import pytest

from ergostat import model as mdl
from ergostat.spec import about as ab
from ergostat.spec import itemindex as ii
from ergostat.spec.explain import explain
from ergostat.store import Project

T0 = 1_700_000_000.0

MODEL = """
name: about-test
stocks:
  a:
    sensor: {manual: true}
  b:
    sensor: {manual: true}
  c:
    sensor: {manual: true}
flows:
  in-a: {to: a}
  out-a: {from: a}
  in-b: {to: b}
  out-c: {from: c}
goals:
  a:
    stock: a
    hold: "<= 5"
  quiet:
    stock: b
    hold: "<= 5"
  calm:
    stock: c
    hold: "<= 5"
blocks:
  drain-a:
    type: program
    goal: a
    run: echo 1
    out: flow.out-a
  drain-c:
    type: program
    goal: calm
    run: echo 1
    out: flow.out-c
  feed:
    type: program
    run: echo 1
    every: 1h
    out: flow.in-b
projections:
  knowledge:
    query: key.startswith('knowledge/')
    fields:
      state:
        type: one of [active, retired]
    events:
      knowledge-found:
        when: type == 'knowledge.found'
        '...': data
        state: set('active')
      knowledge-retired:
        when: type == 'knowledge.retired'
        '...': data
        state: set('retired')
      other:
        when: true
        '...': data
    about: about
messages:
  done: {knowledge: [retired]}
"""


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    return tmp_path


def project(tmp_path, text=MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def found(p, id, about, title=None, at=T0):
    p.events.add("knowledge.found", item=id, data={"about": about, **({"title": title} if title else {})}, at=at)


def last_line(p, part) -> str:
    return explain(p.model.spec, part, p).splitlines()[-1]


def test_explain_lists_open_items_about_a_goal(home):
    p = project(home)
    found(p, "knowledge/one", ["goal.a"], "Failing open", at=T0)
    found(p, "knowledge/two", "goal.a", at=T0 + 1)                         # one name, not a list; no title
    found(p, "knowledge/old", ["goal.a", "stock.a"], "Retired one", at=T0 + 2)
    p.events.add("knowledge.retired", item="knowledge/old", at=T0 + 3)
    found(p, "knowledge/bee", ["stock.b"], "About b", at=T0 + 4)
    line = last_line(p, "goal.a")
    assert line == "Open items about goal.a: knowledge/two, knowledge/one (Failing open)."   # latest first
    assert "knowledge/old" not in line and "knowledge/bee" not in line
    assert last_line(p, "stock.b") == "Open items about stock.b: knowledge/bee (About b)."
    assert last_line(p, "stock.a") == "Open items about stock.a: none."          # the retired one is not listed
    for i in range(4):
        found(p, f"knowledge/more{i}", ["goal.a"], f"More {i}", at=T0 + 10 + i)
    line = last_line(p, "goal.a")
    assert line.count("knowledge/") == 5 and line.endswith(", and 1 more.")
    assert "knowledge/one" not in line                                      # the oldest is the one left out
    assert "Open items" not in explain(p.model.spec, "goal.a")              # without a project: no line


def test_about_replaced_not_merged_on_remake(home):
    p = project(home)

    def now():                                                             # each step folded on its own, as it comes
        return {k: [i for i, *_ in v] for k, v in ab.open_about(p.events, p.model.spec).items()}
    found(p, "knowledge/moved", ["goal.a"], "Moved")
    assert now() == {"goal.a": ["knowledge/moved"]}
    p.events.add("knowledge.changed", item="knowledge/moved", data={"about": ["goal.quiet"]}, at=T0 + 1)
    found(p, "knowledge/back", ["goal.a", "stock.a"], "Back", at=T0 + 2)
    assert now() == {"goal.quiet": ["knowledge/moved"], "goal.a": ["knowledge/back"], "stock.a": ["knowledge/back"]}
    p.events.add("knowledge.retired", item="knowledge/back", at=T0 + 3)
    assert now() == {"goal.quiet": ["knowledge/moved"]}
    found(p, "knowledge/back", ["stock.b"], "Back", at=T0 + 4)               # found again, under the same id
    got = ab.open_about(p.events, p.model.spec)
    assert {k: [i for i, *_ in v] for k, v in got.items()} == {"goal.quiet": ["knowledge/moved"],
                                                             "stock.b": ["knowledge/back"]}
    ix = ii.index_for(p.events, p.model.spec, False)
    assert sorted(ix.about()) == [("knowledge/back", "stock.b"), ("knowledge/moved", "goal.quiet")]   # even finished ones
    assert ix.links_from(["knowledge/back"]) == []                         # a part is not an item: no relation


def test_lookup_is_indexed_not_a_scan(home, monkeypatch):
    p = project(home)
    rows = [{"type": "knowledge.found", "item": f"knowledge/x{i}", "data": {"about": ["stock.b"], "title": "x"}}
            for i in range(5000)]
    for i in range(0, len(rows), 1000):
        p.events.add_many(rows[i:i + 1000]) if hasattr(p.events, "add_many") else [
            p.events.add(r["type"], item=r["item"], data=r["data"]) for r in rows[i:i + 1000]]
    found(p, "knowledge/mine", ["goal.a"], "Mine", at=T0 + 9e8)
    assert ii.index_for(p.events, p.model.spec, False).total() == 5001   # caught up: the record is folded
    read = {"rows": 0, "events": 0}
    real_item = ii.Index._item

    def item(self, *a, **k):
        read["rows"] += 1
        return real_item(self, *a, **k)

    def counted(real):
        def run(self, *a, **k):
            got = real(self, *a, **k)
            read["events"] += len(got) if isinstance(got, list) else 0
            return got
        return run
    monkeypatch.setattr(ii.Index, "_item", item)
    for name in ("of_items", "query", "items_of", "iter"):                 # every way to read the raw events
        if hasattr(type(p.events), name):
            monkeypatch.setattr(type(p.events), name, counted(getattr(type(p.events), name)))
    monkeypatch.setattr(ii, "fold", lambda *a, **k: pytest.fail("folded while looking up"))
    assert [i for i, *_ in ab.open_about(p.events, p.model.spec, ["goal.a"])["goal.a"]] == ["knowledge/mine"]
    assert read == {"rows": 1, "events": 0}                                 # the one item about it, read once


def test_no_kind_declares_about_no_lookup(home, monkeypatch):
    p = project(home, MODEL.replace("    about: about\n", ""))
    found(p, "knowledge/one", ["goal.a"])
    monkeypatch.setattr(ii, "index_for", lambda *a, **k: pytest.fail("looked up"))
    monkeypatch.setattr(ii.Index, "about", lambda *a, **k: pytest.fail("looked up"))
    assert "Open items" not in explain(p.model.spec, "goal.a", p)
    assert ab.open_about(p.events, p.model.spec, ["goal.a"]) == {}
    out: list = []
    ab.findings(p.model.spec, out)
    assert out == []


def _break_index(p, monkeypatch):
    ix = ii.index_for(p.events, p.model.spec, False)
    ix.close()
    ix.path.write_bytes(b"this is not a database" * 100)
    for suf in ("-wal", "-shm"):
        ix.path.with_name(ix.path.name + suf).unlink(missing_ok=True)

    def heal(self, e):                                                     # and it cannot be built again either
        raise e
    monkeypatch.setattr(ii.Index, "_heal", heal)


def test_unreadable_index_says_unknown(home, monkeypatch):
    p = project(home)
    found(p, "knowledge/one", ["goal.a"], "One")
    assert "knowledge/one" in last_line(p, "goal.a")
    _break_index(p, monkeypatch)
    line = last_line(p, "goal.a")
    assert line.startswith("Open items about goal.a: unknown, the item index could not be read") and "none" not in line
    out: list = []
    ab.findings(p.model.spec, out)                                         # check: unknown, not "no missing part"
    assert [f.code for f in out] == ["about-unknown"]


def test_corrupt_index_is_built_again_not_none(home):
    p = project(home)
    found(p, "knowledge/one", ["goal.a"], "One")
    ix = ii.index_for(p.events, p.model.spec, False)
    ix.close()
    ix.path.write_bytes(b"this is not a database" * 100)
    assert last_line(p, "goal.a") == "Open items about goal.a: knowledge/one (One)."   # healed from the record


def test_an_index_built_before_the_about_links_is_rebuilt(home):
    p = project(home)
    found(p, "knowledge/one", ["goal.a"], "One")
    ix = ii.index_for(p.events, p.model.spec, False)
    with ix.lock:                                          # as the layout before the @about links left it: no links
        ix.db.execute("delete from links")
        ix.db.execute("update meta set value = ? where key = 'version'", (ii.VERSION - 1,))
    ix.close()
    ii._OPEN.clear()
    assert last_line(p, "goal.a") == "Open items about goal.a: knowledge/one (One)."


def test_missing_part_is_a_finding_and_findings_carry_ids(home, capsys, monkeypatch):
    p = project(home)
    found(p, "knowledge/fb", ["goal.quiet"], "Feedback", at=T0)
    for n, name in enumerate(["goal.gone", "foo.x", "goal.", "block.nowhere", "stock.a.main"]):
        found(p, f"knowledge/bad{n}", [name, "stock.b"], at=T0 + 1 + n)
    found(p, "knowledge/gone-but-retired", ["goal.also-gone"], at=T0 + 9)
    p.events.add("knowledge.retired", item="knowledge/gone-but-retired", at=T0 + 10)
    from ergostat.cli import main
    from ergostat.mcp import Server
    from ergostat.spec import findings as fi
    from ergostat.spec.load import Problem
    real_late = fi.late                                                    # a finding check adds after read: ids too

    def late(spec, wait=None):
        return real_late(spec, wait) + [Problem("finding", "an extreme", None, "extreme-test", "goal.quiet")]
    monkeypatch.setattr(fi, "late", late)
    main(["-C", str(home), "check", "--json", "--no-coherence"])
    cli = json.loads(capsys.readouterr().out)["found"]
    mcp = json.loads(Server(home).call("check", {})["content"][0]["text"])["problems"]
    for problems in (cli, mcp):
        missing = {f["about"]: f for f in problems if f["code"] == "about-missing-part"}
        assert set(missing) == {"goal.gone", "foo.x", "goal.", "block.nowhere", "stock.a.main"}
        assert missing["goal.gone"]["items"] == ["knowledge/bad0"] and "knowledge/bad0" in missing["goal.gone"]["message"]
        fb = next(f for f in problems if f["code"] == "missing-feedback" and f["about"] == "goal.quiet")
        assert fb["items"] == ["knowledge/fb"] and "open items about it: knowledge/fb" in fb["message"]
        others = [f for f in problems if (f["about"] or "").startswith("block.") and f["code"] != "about-missing-part"]
        assert others and all("items" not in f for f in others)                 # none named: no ids
    ext = next(f for f in cli if f["code"] == "extreme-test")              # (the MCP's read runs its own extremes)
    assert ext["items"] == ["knowledge/fb"]


def test_loading_the_model_looks_nothing_up(home, monkeypatch):
    """The about findings are check's alone: loading a model that declares ``about:`` (every CLI command, the engine,
    a proposal's trial) never opens the item index for them."""
    from ergostat.spec import read
    p = project(home)
    found(p, "knowledge/gone", ["goal.gone"])
    monkeypatch.setattr(ii, "index_for", lambda *a, **k: pytest.fail("the item index opened on a load"))
    monkeypatch.setattr(ab, "open_about", lambda *a, **k: pytest.fail("looked up on a load"))
    m = mdl.load(home)
    assert m.spec is not None and ab.declared(m.spec)
    _, problems = read(home / "ergostat.yaml")
    assert not [x for x in problems if x.code.startswith("about-")]


def _off(p, name, value):
    p.measurements.add(f"sensor/{name}.main", value, at=__import__("time").time())


def test_status_off_loop_points_at_knowledge(home, capsys):
    from ergostat.cli import main
    p = project(home)
    for i in range(4):
        found(p, f"knowledge/g{i}", ["goal.a"], at=T0 + i)
    found(p, "knowledge/measured", ["stock.a"], at=T0 + 9)                  # about its measured value
    found(p, "knowledge/q", ["goal.calm", "stock.c"], at=T0 + 9)
    _off(p, "a", 50)
    _off(p, "c", 1)
    main(["-C", str(home), "status"])
    out = capsys.readouterr().out
    att = next(x for x in out.splitlines() if "goal a:" in x)
    assert re.search(r"items about it: knowledge/\w+, knowledge/\w+, knowledge/\w+ \+2$", att), att
    assert "knowledge/measured" in att                                       # the latest, through stock.a
    row = next(x for x in out.splitlines() if re.match(r"^a\s", x))
    assert re.search(r"\(knowledge/\w+, knowledge/\w+, knowledge/\w+ \+2\)", row), row
    calm = next(x for x in out.splitlines() if re.match(r"^calm\s", x))
    assert "holding" in calm and "knowledge/q" not in out                    # a loop that holds names none
    main(["-C", str(home), "status", "--json"])
    got = json.loads(capsys.readouterr().out)
    loops = got["loops"]
    assert loops["a"]["about"].endswith("+2") and "about" not in loops["calm"]
    assert {a.get("goal") for a in got["attention"]} >= {"a", "quiet"}, got["attention"]   # quiet: nothing holds it
    # --system S: only its goals' entries, the field matched
    from ergostat.cli import status as cs
    real = cs.parts_of
    cs.parts_of = lambda args, m: {"a", "drain-a"} if args.system == "s" else real(args, m)
    try:
        main(["-C", str(home), "status", "--system", "s", "--json"])
    finally:
        cs.parts_of = real
    att = json.loads(capsys.readouterr().out)["attention"]
    assert [a["what"] for a in att if a.get("goal")] == ["goal a"] and "items about it" in att[0]["says"], att


def test_status_names_the_items_on_the_loops_attention_line_not_its_suggestion(home, capsys, monkeypatch):
    """A goal's suggestion is headed ``goal NAME`` like its attention line; the items go on that line only (§5a)."""
    from ergostat import state as st
    from ergostat.cli import main
    p = project(home)
    found(p, "knowledge/g", ["goal.a"])
    _off(p, "a", 50)
    real = st.attention
    monkeypatch.setattr(st, "attention", lambda *a, **k: real(*a, **k) + [
        {"level": "hint", "what": "goal a", "goal": "a", "says": "was off 92% of the time: falling behind the load"}])
    main(["-C", str(home), "status", "--json"])
    att = [a for a in json.loads(capsys.readouterr().out)["attention"] if a.get("goal") == "a"]
    assert all(a["what"] == "goal a" for a in att), att
    hint = [a for a in att if a["level"] == "hint"]
    line = [a for a in att if a["level"] != "hint"]
    assert hint and line, att
    assert all("items about it" not in a["says"] for a in hint), hint
    assert all(a["says"].endswith("items about it: knowledge/g") for a in line), line
    main(["-C", str(home), "status"])
    out = capsys.readouterr().out
    assert out.count("items about it") == 1, out


def test_status_at_a_past_time_names_no_items(home, capsys):
    """The items are open now: a past snapshot's off loop does not name them (SPEC §5a)."""
    import time

    from ergostat.cli import main
    p = project(home)
    found(p, "knowledge/g", ["goal.a"], at=time.time() - 7200)
    p.measurements.add("sensor/a.main", 50, at=time.time() - 3600)
    main(["-C", str(home), "status", "--json"])
    assert json.loads(capsys.readouterr().out)["loops"]["a"].get("about") == "knowledge/g"   # live: named
    main(["-C", str(home), "status", "--at", "30m"])
    out = capsys.readouterr().out
    assert "goal a:" in out and "knowledge/" not in out, out
    main(["-C", str(home), "status", "--at", "30m", "--json"])
    got = json.loads(capsys.readouterr().out)
    assert "about" not in got["loops"]["a"] and "knowledge/" not in json.dumps(got["attention"])


def test_the_index_file_changes_with_its_layout_and_the_about_field(home, monkeypatch):
    """An index of another layout (main's VERSION 4 had text but no @about links) or of a kind without ``about:``
    is never opened as current: VERSION and each kind's ``about`` are part of the file's name."""
    p = project(home)
    found(p, "knowledge/one", ["goal.a"], "One")
    now = ii.index_for(p.events, p.model.spec, False).path
    ii._OPEN.clear()
    monkeypatch.setattr(ii, "VERSION", ii.VERSION - 1)
    assert ii.index_for(p.events, p.model.spec, False).path != now
    monkeypatch.undo()
    ii._OPEN.clear()
    assert ii.index_for(p.events, p.model.spec, False).path == now
    bare = project(home, MODEL.replace("    about: about\n", ""))
    assert ii.kinds_key(bare.model.spec) != ii.kinds_key(p.model.spec)


def test_status_with_an_unreadable_index_says_unknown(home, capsys, monkeypatch):
    from ergostat.cli import main
    p = project(home)
    found(p, "knowledge/g", ["goal.a"])
    _off(p, "a", 50)
    _break_index(p, monkeypatch)
    main(["-C", str(home), "status"])
    att = next(x for x in capsys.readouterr().out.splitlines() if "goal a:" in x)
    assert att.endswith("items about it: unknown (the item index could not be read)"), att


def test_mcp_explain_lists_the_same_items_as_the_cli(home, capsys):
    from ergostat.cli import main
    from ergostat.mcp import serve
    p = project(home)
    found(p, "knowledge/one", ["goal.a"], "One")
    main(["-C", str(home), "explain", "goal.a"])
    cli = capsys.readouterr().out.strip().splitlines()[-1]
    out = io.StringIO()
    serve(home, io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "explain", "arguments": {"part": "goal.a"}}}) + "\n"), out)
    text = json.loads(out.getvalue().splitlines()[0])["result"]["content"][0]["text"]
    assert cli == "Open items about goal.a: knowledge/one (One)." and text.strip().splitlines()[-1] == cli


