"""Searching items (SPEC §5a, *Search*): the items whose fields' text contains every word, casefolded, kept on each
item's own row of the item index and written again whenever the item is folded; the CLI and the API agree."""

from __future__ import annotations

import json
import sqlite3
import textwrap
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.goodmodel import keep
from ergostat.spec import itemindex
from ergostat.spec import items as its
from ergostat.store import Project

T0 = 1_700_000_000.0
MODEL = """
name: sr
items:
  ticket:
    id: ticket/*
    states: [open, done]
    on: {ticket.done: done}
"""


def _project(tmp_path) -> Project:
    d = tmp_path / "sr"
    d.mkdir(exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    return Project(mdl.load(d))


def _found(p, words: str, **kw) -> list[str]:
    return sorted(i["id"] for i in its.listing(p.events, p.model.spec, search=its.words_of(words), **kw)["items"])


def _cold() -> None:
    """As a process that starts: nothing of the index in memory."""
    for ix in list(itemindex._OPEN.values()):
        ix.close()
    itemindex._OPEN.clear()


def _three(p) -> None:
    p.events.add("ticket.opened", item="ticket/1", at=T0,
                 data={"title": "Alpha", "notes": {"deep": ["x", "the BETA here"]}, "city": "Straße"})
    p.events.add("ticket.opened", item="ticket/2", at=T0 + 1, data={"title": "alpha only", "cut": "50% off"})
    p.events.add("ticket.opened", item="ticket/3", at=T0 + 2, data={"title": "beta only", "cut": "500 a_b"})
    p.events.add("ticket.opened", item="ticket/4", at=T0 + 3, data={"cut": "axb"})


def test_search_finds_by_every_word(tmp_path):
    p = _project(tmp_path)
    _three(p)
    assert _found(p, "alpha beta") == ["ticket/1"]              # both words, one nested, in any case
    assert _found(p, "ALPHA") == ["ticket/1", "ticket/2"]
    assert _found(p, "beta alpha") == ["ticket/1"]              # the order of the words does not matter
    assert _found(p, "STRASSE") == ["ticket/1"]                  # casefolded, not only lowered
    assert _found(p, "50%") == ["ticket/2"]                      # no LIKE: % and _ are only themselves
    assert _found(p, "a_b") == ["ticket/3"]
    assert _found(p, "alpha", kind="ticket", state="done") == []
    got = its.listing(p.events, p.model.spec, search=["alpha"], n=1)
    assert got["total"] == 2 and [i["id"] for i in got["items"]] == ["ticket/2"]    # the latest first, paged


def test_changed_field_stops_matching(tmp_path):
    from ergostat.rollup import compact
    p = _project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=T0, data={"title": "gamma"})
    assert _found(p, "gamma") == ["ticket/1"]
    p.events.add("ticket.renamed", item="ticket/1", at=T0 + 1, data={"title": "delta", "about": "kappa"})
    assert _found(p, "gamma") == [] and _found(p, "delta") == ["ticket/1"]         # a field replaced
    p.events.add("ticket.opened", item="ticket/1", at=T0 + 2, set={"title": "omega"})
    assert _found(p, "kappa") == [] and _found(p, "delta") == [] and _found(p, "omega") == ["ticket/1"]   # a same-id set
    _cold()
    assert _found(p, "kappa") == [] and _found(p, "omega") == ["ticket/1"]          # a process that starts
    assert compact(p, now=T0 + 2 + p.storage.rollup_after + 3600)["items"] == 1     # its events now one snapshot
    itemindex.reindex(p.events, p.model.spec)                                       # folded from the snapshot alone
    assert _found(p, "gamma") == [] and _found(p, "kappa") == [] and _found(p, "omega") == ["ticket/1"]


def test_forgotten_item_leaves_search(tmp_path):
    p = _project(tmp_path)
    p.events.add("ticket.opened", item="ticket/9", at=T0, data={"title": "zeta"})
    p.events.add("ticket.opened", item="ticket/1", at=T0 + 100, data={"title": "zeta too"})
    assert _found(p, "zeta") == ["ticket/1", "ticket/9"]
    p.events.prune(T0 + 50)
    assert _found(p, "zeta") == ["ticket/1"]


def test_old_index_rebuilt_and_searchable(tmp_path):
    p = _project(tmp_path)
    _three(p)
    path = itemindex.index_for(p.events, p.model.spec, False).path
    _cold()
    with sqlite3.connect(path) as c:                 # as main's previous layout left it: no text, its VERSION
        c.execute("alter table items drop column text")
        c.execute("update meta set value = ? where key = 'version'", (itemindex.VERSION - 1,))
    c.close()
    assert _found(p, "alpha beta") == ["ticket/1"]
    with sqlite3.connect(path) as c:
        assert c.execute("select value from meta where key = 'version'").fetchone()[0] == itemindex.VERSION
    c.close()


def test_a_row_without_its_text_is_rebuilt_not_read_as_no_match(tmp_path):
    p = _project(tmp_path)
    _three(p)
    ix = itemindex.index_for(p.events, p.model.spec, False)
    with ix.lock:
        ix.db.execute("update items set text = null where id = 'ticket/1'")
    assert _found(p, "alpha beta") == ["ticket/1"]
    with ix.lock:
        assert ix.db.execute("select count(*) from items where text is null").fetchone()[0] == 0


def test_words_past_the_cap_are_not_searched(tmp_path):
    p = _project(tmp_path)
    text = "before " + "x" * (its.TEXT_MOST - len("before ") - len(" inside")) + " inside" + " beyond"
    p.events.add("ticket.opened", item="ticket/1", at=T0, data={"body": text})
    assert _found(p, "before") == _found(p, "inside") == ["ticket/1"]
    assert _found(p, "beyond") == []


def test_search_cli_and_api_agree(tmp_path, capsys):
    from ergostat.web.server import Live, api, handler
    p = _project(tmp_path)
    _three(p)
    d = p.model.path.parent
    from_api = sorted(i["id"] for i in api(Live(p), "items", {"search": ["alpha beta"]})["items"])
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(p))
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def get(query: str):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/items?{query}", timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        st, got = get("search=Alpha+BETA")
        assert st == 200 and sorted(i["id"] for i in got["items"]) == from_api == ["ticket/1"]
        assert get("search=")[0] == 400 and get("search=+++")[0] == 400               # blank: refused, not all
        assert get("search=" + "+".join("abcdefghi"))[0] == 400                         # 9 words
        assert get("search=" + "+".join("abcdefgh"))[0] == 200                          # 8: taken
    finally:
        srv.shutdown()
        srv.server_close()
    assert keep(p) is None
    with open(d / "ergostat.yaml", "a") as f:                     # broken: the CLI reads on the last good model
        f.write("\nbroken: [\n")
    capsys.readouterr()
    assert main(["-C", str(d), "item", "--search", "alpha beta", "--json"]) == 0
    out, err = capsys.readouterr()
    assert sorted(i["id"] for i in json.loads(out)["items"]) == from_api and "last good model" in err
    assert main(["-C", str(d), "item", "--search", "alpha", "-n", "0", "--json"]) == 0      # -n clamped to 1..
    assert len(json.loads(capsys.readouterr().out)["items"]) == 1
    assert main(["-C", str(d), "item", "--search", "alpha", "-n", "100000", "--json"]) == 0  # ..items.LISTED
    assert len(json.loads(capsys.readouterr().out)["items"]) == 2
    assert main(["-C", str(d), "item", "--search", "  "]) == 2 and "needs a word" in capsys.readouterr().err
    assert main(["-C", str(d), "item", "--search", " ".join("abcdefghi")]) == 2
    assert "at most 8" in capsys.readouterr().err


def test_search_with_at_refused(tmp_path, capsys):
    p = _project(tmp_path)
    _three(p)
    d = p.model.path.parent
    assert main(["-C", str(d), "item", "--search", "alpha", "--at", "30m"]) == 2
    assert "--at" in capsys.readouterr().err
