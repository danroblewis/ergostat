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


def test_old_index_rebuilt_and_searchable(tmp_path):
    p = _project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", data={"title": "before upgrade"}, at=T0)
    path = _file(p)
    _cold()
    with sqlite3.connect(path) as c:                                         # as the layout before this change left it
        c.execute("alter table items drop column text")
        c.execute("update meta set value = ? where key = 'version'", (itemindex.VERSION - 1,))
    assert its.listing(p.events, p.model.spec)["total"] == 1                # any read: rebuilt, not only a search
    with sqlite3.connect(path) as c:
        assert c.execute("select value from meta where key = 'version'").fetchone()[0] == itemindex.VERSION
        assert c.execute("select count(*) from items where text is null").fetchone()[0] == 0
    assert _found(p, "upgrade") == ["ticket/1"]


def test_a_row_without_its_text_is_rebuilt_not_read_as_no_match(tmp_path):
    p = _project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", data={"title": "kept"}, at=T0)
    path = _file(p)
    _cold()
    with sqlite3.connect(path) as c:
        c.execute("update items set text = null")
    assert _found(p, "kept") == ["ticket/1"]


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
        for q in ("?search=", "?search=%20", "?search=alpha&at=1700000000"):
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
