"""Search over items' fields (SPEC §5a, *Search*): the items whose text contains every word, kept in the item index
(spec/itemindex.py) and rewritten with each fold, from the command line and the API."""

from __future__ import annotations

import json
import sqlite3
import textwrap
import threading
import urllib.error
import urllib.request

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.rollup import upkeep
from ergostat.spec import itemindex
from ergostat.spec import items as its
from ergostat.spec.item_sets import BadSet
from ergostat.store import Project

T0 = 1_700_000_000.0
MODEL = """
items:
  ticket:
    id: ticket/*
    states: [open, done]
    on: {ticket.done: done}
  note:
    id: note/*
"""


def _project(tmp_path, extra: str = "") -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL) + extra)
    return Project(mdl.load(tmp_path))


def _found(p, search: str, **k) -> list[str]:
    return [i["id"] for i in its.listing(p.events, p.model.spec, search=search, **k)["items"]]


def _cold() -> None:
    """As a process that starts: nothing of the index in memory, its file closed."""
    for ix in list(itemindex._OPEN.values()):
        ix.close()
    itemindex._OPEN.clear()


def _file(p) -> str:
    return str(itemindex.index_for(p.events, p.model.spec, False).path)


def test_search_finds_by_every_word(tmp_path):
    p = _project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", data={"title": "ALPHA release", "meta": {"tags": ["x", "Beta"]}}, at=T0)
    p.events.add("ticket.opened", item="ticket/2", data={"title": "alpha only"}, at=T0 + 1)          # the decoy: one word
    p.events.add("ticket.opened", item="ticket/3", data={"title": "beta only"}, at=T0 + 2)           # and the other
    p.events.add("note.made", item="note/1", data={"body": "Alphabet and betamax"}, at=T0 + 3)        # substrings
    assert _found(p, "alpha beta") == ["note/1", "ticket/1"]                 # newest first; a nested field's word too
    assert _found(p, "BETA Alpha", kind="ticket") == ["ticket/1"]
    assert _found(p, "alpha", kind="ticket", state="open") == ["ticket/2", "ticket/1"]
    assert _found(p, "alpha", kind="ticket", state="done") == []
    assert its.listing(p.events, p.model.spec, search="alpha beta")["total"] == 2
    p.events.add("ticket.opened", item="ticket/4", data={"price": "50% off", "k": "Ärger STRAẞE"}, at=T0 + 4)
    assert _found(p, "50%") == ["ticket/4"]                                  # % and _ are no wildcards
    assert _found(p, "_") == [] and _found(p, "a_p") == []
    assert _found(p, "ärger straße") == ["ticket/4"] == _found(p, "ÄRGER strasse")   # casefolded, not only ASCII
    for bad in ("", "   ", " ".join(["w"] * (its.SEARCH_WORDS + 1))):
        with pytest.raises(BadSet):
            its.listing(p.events, p.model.spec, search=bad)


def test_words_past_the_cap_are_not_searched(tmp_path):
    p = _project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", data={"a": "early", "b": "x" * its.TEXT_MOST, "c": "late"}, at=T0)
    assert _found(p, "early") == ["ticket/1"] and _found(p, "late") == []       # as SPEC §5a says: the first 65,536


def test_changed_field_stops_matching(tmp_path):
    p = _project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", data={"title": "old words", "deep": {"n": "remnant"}}, at=T0)
    assert _found(p, "old") == ["ticket/1"]
    p.events.add("ticket.renamed", item="ticket/1", data={"title": "new words"}, at=T0 + 1)
    assert _found(p, "old") == [] and _found(p, "new") == ["ticket/1"] and _found(p, "remnant") == ["ticket/1"]
    p.events.add("ticket.remade", item="ticket/1", set={"title": "remade"}, at=T0 + 2)            # the same id made again
    assert _found(p, "remnant") == [] and _found(p, "new") == [] and _found(p, "remade") == ["ticket/1"]
    p.events.add(its.SNAPSHOT, item="ticket/1", set={"title": "restored"}, at=T0 + 3)
    assert _found(p, "remade") == [] and _found(p, "restored") == ["ticket/1"]
    _cold()                                                                  # and so on disk, for a process that starts
    assert _found(p, "remade") == [] and _found(p, "restored") == ["ticket/1"]


def test_forgotten_item_leaves_search(tmp_path):
    p = _project(tmp_path, "keep: 1d\n")
    now = T0 + 10 * 86400
    p.events.add("ticket.opened", item="ticket/old", data={"title": "findme"}, at=T0)
    p.events.add("ticket.opened", item="ticket/live", data={"title": "findme"}, at=now - 10)
    assert _found(p, "findme") == ["ticket/live", "ticket/old"]
    upkeep(p, now=now)
    assert _found(p, "findme") == ["ticket/live"]
    with sqlite3.connect(_file(p)) as c:
        assert c.execute("select count(*) from items where instr(text, 'findme')").fetchone()[0] == 1


def test_old_index_rebuilt_and_searchable(tmp_path, monkeypatch):
    p = _project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", data={"title": "before upgrade"}, at=T0)
    monkeypatch.setattr(itemindex, "VERSION", itemindex.VERSION - 1)
    old = _file(p)                                                           # folded by the release before this one
    _cold()
    with sqlite3.connect(old) as c:                                          # and in its layout: no text at all
        c.execute("drop index items_textless")
        c.execute("alter table items drop column text")
    monkeypatch.undo()
    new = _file(p)                                                           # the upgrade: its own file, from the record
    assert new != old
    assert its.listing(p.events, p.model.spec)["total"] == 1
    assert _found(p, "upgrade") == ["ticket/1"]
    with sqlite3.connect(new) as c:
        assert c.execute("select value from meta where key = 'version'").fetchone()[0] == itemindex.VERSION
        assert c.execute("select count(*) from items where text is null").fetchone()[0] == 0
    _cold()                                                                  # an old stamp at the new path: rebuilt too
    with sqlite3.connect(new) as c:
        c.execute("update meta set value = ? where key = 'version'", (itemindex.VERSION - 1,))
        c.execute("update items set text = ''")
    assert _found(p, "upgrade") == ["ticket/1"]


def test_a_row_without_its_text_is_rebuilt_not_read_as_no_match(tmp_path):
    p = _project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", data={"title": "kept"}, at=T0)
    path = _file(p)
    _cold()
    with sqlite3.connect(path) as c:
        c.execute("update items set text = null")
    assert _found(p, "kept") == ["ticket/1"]
    with sqlite3.connect(path) as c:                                         # the check before each search: one lookup
        plan = " ".join(r[-1] for r in c.execute("explain query plan select 1 from items where text is null limit 1"))
    assert "items_textless" in plan, plan


def _model_repo(tmp_path):
    d = tmp_path / "rz"
    d.mkdir()
    (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    p = Project(mdl.load(d))
    p.events.add("ticket.opened", item="ticket/1", data={"title": "alpha beta"}, at=T0)
    p.events.add("ticket.opened", item="ticket/2", data={"title": "alpha"}, at=T0 + 1)
    p.events.add("note.made", item="note/1", data={"body": "beta, then alpha"}, at=T0 + 2)
    return d, p


def test_search_cli_and_api_agree(tmp_path, capsys):
    from http.server import ThreadingHTTPServer

    from ergostat.goodmodel import keep
    from ergostat.web.server import handler
    d, p = _model_repo(tmp_path)
    assert main(["-C", str(d), "item", "--search", "alpha beta", "--json"]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert set(cli) == set(its.listing(p.events, p.model.spec))               # the listing's shape
    assert [i["id"] for i in cli["items"]] == ["note/1", "ticket/1"]
    assert main(["-C", str(d), "item", "--search", "beta alpha", "-n", "100000"]) == 0
    table = capsys.readouterr().out
    assert "note/1" in table and "ticket/1" in table and "ticket/2" not in table
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(p))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/api/items"

    def get(q):
        try:
            with urllib.request.urlopen(url + q, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        code, got = get("?search=alpha%20beta")
        assert code == 200 and [i["id"] for i in got["items"]] == [i["id"] for i in cli["items"]]
        assert [i["id"] for i in get("?search=alpha&kind=ticket&n=1")[1]["items"]] == ["ticket/2"]
        for q in ("?search=", "?search=%20", "?search=alpha&at=1700000000", "?search=alpha&kind=ticket&where=title:x",
                  "?search=alpha&where=title:x", "?search=alpha&kind=ticket&state=open,done",
                  "?search=alpha&kind=ticket&state=open&alone=1"):
            assert get(q)[0] == 400, q                                       # never "everything"
    finally:
        srv.shutdown()
        srv.server_close()
    assert keep(p) is None                                                   # the last good model, then a broken YAML
    with open(d / "ergostat.yaml", "a") as f:
        f.write("\nbroken: [\n")
    assert main(["-C", str(d), "item", "--search", "alpha beta", "--json"]) == 0
    out, err = capsys.readouterr()
    assert [i["id"] for i in json.loads(out)["items"]] == ["note/1", "ticket/1"] and "last good" in err


def test_search_with_at_refused(tmp_path, capsys):
    d, _ = _model_repo(tmp_path)
    assert main(["-C", str(d), "item", "--search", "alpha", "--at", "30m"]) == 2
    assert "--at" in capsys.readouterr().err
    assert main(["-C", str(d), "item", "--search", "  "]) == 2
    assert "1 to 8 words" in capsys.readouterr().err


def _many(p, n: int, done_every: int = 3) -> None:
    """``n`` tickets, ticket/0 the oldest, each with a cost (``n - i``: the oldest costs most) and every
    ``done_every``-th finished."""
    evs = [{"type": "ticket.opened", "item": f"ticket/{i}", "data": {"title": f"t{i}", "cost": n - i}, "at": T0 + i}
           for i in range(n)]
    evs += [{"type": "ticket.done", "item": f"ticket/{i}", "at": T0 + i + 0.5} for i in range(0, n, done_every)]
    p.events.add_many(evs, new=True)


def test_a_kinds_page_reaches_every_item_and_its_search_every_match(tmp_path):
    p = _project(tmp_path)
    _many(p, 1200)
    page = lambda **k: its.kind_page(p.events, p.model.spec, "ticket", **k)   # noqa: E731
    seen, off = [], 0
    while True:                                                  # Next, to the end: every item, newest first
        got = page(n=25, offset=off)
        assert got["total"] == 1200 and got["offset"] == off
        seen += [i.id for i in got["items"]]
        if off + 25 >= got["total"]:
            break
        off += 25
    assert seen == [f"ticket/{i}" for i in range(1199, -1, -1)]  # the last page's last row is the oldest
    assert page(n=25, offset=99_999)["offset"] == 1175           # past the end: the last page
    hit = page(n=25, q="ticket/200")                             # the 1,000th newest (unfinished: 200 % 3 = 2)
    assert [i.id for i in hit["items"]] == ["ticket/200"] and hit["total"] == 1 and hit["finished"] == 0
    old = page(n=25, q="ticket/3")                               # ticket/3, 30-39, 300-399: 111, a third finished
    assert old["total"] == 111 and old["finished"] == sum(1 for i in [3, *range(30, 40), *range(300, 400)] if i % 3 == 0)
    assert [i.id for i in page(n=300, q="ticket/3")["items"]][-1] == "ticket/3"   # the oldest of them, finished
    assert page(q="t1199")["total"] == 1 and page(q="t1199", state="done")["total"] == 0   # a word of its fields
    assert [i.id for i in page(q="ticket/0", state="done")["items"]] == ["ticket/0"]


def test_a_kinds_sort_runs_over_the_whole_set_and_says_its_cut_past_5000(tmp_path):
    p = _project(tmp_path)
    _many(p, 1200)
    top = its.kind_page(p.events, p.model.spec, "ticket", n=25, sort="-cost")
    assert top["items"][0].id == "ticket/0" and top["items"][0].fields["cost"] == 1200 and top["cut"] is None
    assert [i.fields["cost"] for i in its.kind_page(p.events, p.model.spec, "ticket", n=3, sort="cost")["items"]] == [1, 2, 3]
    assert its.kind_page(p.events, p.model.spec, "ticket", n=25, offset=10_000, sort="cost")["items"][-1].id == "ticket/0"
    big = tmp_path / "big"
    big.mkdir()
    p2 = _project(big)
    _many(p2, 6000)
    got = its.kind_page(p2.events, p2.model.spec, "ticket", n=25, sort="-cost")
    assert got["total"] == 6000 and got["cut"] == its.SORTED_MOST     # sorted among the newest 5,000 only, and said
    assert got["items"][0].id == "ticket/1000" and got["items"][0].fields["cost"] == 5000
    assert its.kind_page(p2.events, p2.model.spec, "ticket", n=25, offset=99_999, sort="-cost")["offset"] == 4975


def test_the_api_pages_searches_and_sorts_one_kind(tmp_path):
    from http.server import ThreadingHTTPServer

    from ergostat.web.server import handler
    p = _project(tmp_path)
    _many(p, 120)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(p))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/api/items?kind=ticket"

    def get(q):
        with urllib.request.urlopen(url + q, timeout=10) as r:
            return json.loads(r.read())
    try:
        got = get("&n=25&offset=100")
        assert got["total"] == 120 and got["offset"] == 100 and [i["id"] for i in got["items"]][-1] == "ticket/0"
        assert len(got["items"]) == 20 and {"ticket", "note"} <= {k["name"] for k in got["kinds"]}
        assert get("&n=25&offset=500")["offset"] == 100                         # past the end: the last page
        s = get("&n=25&q=ticket/1")                                             # 1, 10-19, 100-119: 31 of them
        assert s["total"] == 31 and s["finished"] == sum(1 for i in [1, *range(10, 20), *range(100, 120)] if i % 3 == 0)
        assert get("&n=5&sort=-cost")["items"][0]["id"] == "ticket/0"           # the most, of all 120, on page 1
        assert get("&n=5&sort=cost&offset=5")["items"][0]["fields"]["cost"] == 6
    finally:
        srv.shutdown()
        srv.server_close()
