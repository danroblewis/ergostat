"""The ticket factory's watcher records Jira's issue links and parent as the ticket's relations (ticket.linked, a
whole set per relation), compared with the fold at each reading, failing closed on anything it can't read."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.spec import items as its
from ergostat.store import Project

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "ticket-factory"
MODS = ("tf", "fakes", "jira", "watch", "daemon")


def _pop():
    for m in MODS:
        sys.modules.pop(m, None)


@pytest.fixture
def tf(tmp_path, monkeypatch):
    """A fresh copy of the example, offline, its record through the real `ergostat` CLI; its bin/ modules imported."""
    d = tmp_path / "tf"
    shutil.copytree(EXAMPLE, d, ignore=shutil.ignore_patterns("run", "reports", "__pycache__", "factory.conf",
                                                              "prometheus.yaml"))
    monkeypatch.setenv("TF_OFFLINE", "1")
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ERGOSTAT_CMD", f"{sys.executable} -m ergostat -C {d}")
    monkeypatch.delenv("ERGOSTAT_SOCKET", raising=False)
    monkeypatch.syspath_prepend(str(d / "bin"))
    _pop()
    import fakes
    import jira
    import tf as tf_
    import watch
    tf_.d, tf_.fakes, tf_.jira, tf_.watch = d, fakes, jira, watch
    yield tf_
    _pop()


def _fold(t, tid):
    p = Project(mdl.load(t.d))
    it = its.one(p.events, p.model.spec, tid)
    return it.fields if it else None


def _events(t, type, item=None):
    return Project(mdl.load(t.d)).events.query(n=None, type=type, **({"item": item} if item else {}))


def _record(t):
    def found(e):
        t.record(e["event"], e["item"], e["data"], by="arrivals.main")
    return found


def _board(t, key, **fields):
    with t.fakes._state("jira") as j:
        t.fakes._issues(j)[key].update(fields)


def _blocks(key, side="inwardIssue"):
    return {"type": {"name": "Blocks"}, side: {"key": key}}


# --- links(): the mapping, and failing closed ---------------------------------------------------------

def test_jira_links_are_read_as_relations(tf):
    links = tf.jira.links
    got = links({"issuelinks": [_blocks("A-1"), _blocks("A-2", "outwardIssue"),
                                {"type": {"name": "Duplicate"}, "outwardIssue": {"key": "A-3"}},
                                {"type": {"name": "Duplicate"}, "inwardIssue": {"key": "A-4"}},
                                {"type": {"name": "Relates"}, "inwardIssue": {"key": "A-6"}},
                                {"type": {"name": "Clones"}, "outwardIssue": {"key": "A-5"}}],
                 "parent": {"key": "EP-9"}})
    assert got == {"blocked_by": ["ticket/A-1"], "duplicates": ["ticket/A-3"],
                   "relates_to": ["ticket/A-5", "ticket/A-6"], "parent": ["ticket/EP-9"]}
    empty = {"blocked_by": [], "duplicates": [], "relates_to": [], "parent": []}
    assert links({"issuelinks": []}) == empty and links({"issuelinks": [], "parent": None}) == empty


@pytest.mark.parametrize("fields", [
    {"issuelinks": [{"type": {"name": "Blocks"}}]},                                    # neither side
    {"issuelinks": [{"type": {"name": "Blocks"}, "inwardIssue": {"id": "1"}}]},        # a linked issue with no key
    {"issuelinks": [], "parent": {"id": "1"}},                                         # a parent with no key
    {"issuelinks": [{"type": {"id": "1"}, "inwardIssue": {"key": "A-1"}}]},            # no type.name
    {"issuelinks": ["A-1"]},                                                           # not a dict
    {},                                                                                # issuelinks missing
    {"issuelinks": {"0": _blocks("A-1")}},                                             # not a list
    {"issuelinks": [_blocks("../x")]},                                                 # fails the allowlist
], ids=["no-side", "no-key", "parent-no-key", "no-type-name", "not-dict", "missing", "not-list", "bad-key"])
def test_an_unreadable_link_makes_links_none(tf, fields):
    assert tf.jira.links(fields) is None


def test_an_epic_on_data_center_is_not_read_as_parent(tf):
    """DC gives an epic as the Epic Link custom field, not fields.parent: it is not read (README says so)."""
    assert tf.jira.links({"issuelinks": [], "customfield_10008": "EP-1"})["parent"] == []


# --- the watcher --------------------------------------------------------------------------------------

def test_a_ticket_found_at_this_reading_gets_its_links_at_once(tf):
    tf.watch.look(_record(tf))
    types = [e["type"] for e in Project(mdl.load(tf.d)).events.query(n=None, item="ticket/SCRUM-2")]
    assert types.index("ticket.found") < types.index("ticket.linked")
    assert _fold(tf, "ticket/SCRUM-2")["blocked_by"] == ["ticket/SCRUM-1"]
    assert not _events(tf, "ticket.linked", "ticket/SCRUM-1"), "no links: nothing written"


def test_an_unchanged_answer_records_nothing(tf):
    tf.watch.look(_record(tf))
    tf.watch.look(_record(tf))
    assert len(_events(tf, "ticket.linked", "ticket/SCRUM-2")) == 1


def test_a_malformed_entry_beside_a_blocks_link_leaves_blocked_by_unchanged(tf, capsys):
    tf.watch.look(_record(tf))
    assert _fold(tf, "ticket/SCRUM-2")["blocked_by"] == ["ticket/SCRUM-1"]
    # beside the Blocks link, a new one and one with neither side: dropping the bad one would write [1, 3]
    _board(tf, "SCRUM-2", issuelinks=[_blocks("SCRUM-1"), _blocks("SCRUM-3"), {"type": {"name": "Blocks"}}])
    _board(tf, "SCRUM-3", issuelinks=[_blocks("SCRUM-1")])                 # another in the same batch: still written
    capsys.readouterr()
    tf.watch.look(_record(tf))
    assert _fold(tf, "ticket/SCRUM-2")["blocked_by"] == ["ticket/SCRUM-1"]
    assert len(_events(tf, "ticket.linked", "ticket/SCRUM-2")) == 1
    assert _fold(tf, "ticket/SCRUM-3")["blocked_by"] == ["ticket/SCRUM-1"], "one None issue stops no other's write"
    assert "SCRUM-2: a link or parent that can't be read" in capsys.readouterr().err


def test_a_link_removed_in_jira_is_removed_from_the_ticket(tf):
    tf.watch.look(_record(tf))
    _board(tf, "SCRUM-2", issuelinks=[])
    tf.watch.look(_record(tf))
    assert _fold(tf, "ticket/SCRUM-2")["blocked_by"] == []


def test_relates_to_is_held_by_each_side_and_cleared_on_both(tf):
    """Jira shows a Relates link on both issues: each ticket holds its own relates_to; removed, both are cleared."""
    tf.watch.look(_record(tf))
    _board(tf, "SCRUM-1", issuelinks=[{"type": {"name": "Relates"}, "outwardIssue": {"key": "SCRUM-3"}}])
    _board(tf, "SCRUM-3", issuelinks=[{"type": {"name": "Relates"}, "inwardIssue": {"key": "SCRUM-1"}}])
    tf.watch.look(_record(tf))
    assert _fold(tf, "ticket/SCRUM-1")["relates_to"] == ["ticket/SCRUM-3"]
    assert _fold(tf, "ticket/SCRUM-3")["relates_to"] == ["ticket/SCRUM-1"]
    _board(tf, "SCRUM-1", issuelinks=[])
    _board(tf, "SCRUM-3", issuelinks=[])
    tf.watch.look(_record(tf))
    assert _fold(tf, "ticket/SCRUM-1")["relates_to"] == [] and _fold(tf, "ticket/SCRUM-3")["relates_to"] == []


def test_a_newer_reading_in_the_check_to_write_gap_is_caught_up_next_reading(tf):
    seen = {}

    def held(e):
        if e["event"] == "ticket.linked" and "held" not in seen:              # only reading 1's write is held back
            seen["held"] = e
            _board(tf, "SCRUM-2", issuelinks=[_blocks("SCRUM-3")])            # answer B
            tf.watch.look(_record(tf))                                        # a whole second reading records B
            seen["inner"] = _fold(tf, "ticket/SCRUM-2")["blocked_by"]
        _record(tf)(e)
    tf.watch.look(held)
    assert seen["held"]["data"] == {"blocked_by": {"set": ["ticket/SCRUM-1"]}}
    assert seen["inner"] == ["ticket/SCRUM-3"], "the inner reading's write was recorded before A landed"
    assert _fold(tf, "ticket/SCRUM-2")["blocked_by"] == ["ticket/SCRUM-1"], "A landed last: the gap was hit"
    tf.watch.look(_record(tf))
    assert _fold(tf, "ticket/SCRUM-2")["blocked_by"] == ["ticket/SCRUM-3"], "caught up at the next reading"


def test_links_are_written_only_for_tickets_in_the_record(tf):
    with tf.fakes._state("jira") as j:
        tf.fakes._issues(j)["SCRUM-99"] = {"key": "SCRUM-99", "summary": "x", "status": "In Progress",
                                           "labels": [tf.conf("JIRA_LABEL")], "description": "", "comments": [],
                                           "created": 0, "issuelinks": [_blocks("SCRUM-1")]}
    tf.watch.look(_record(tf))
    assert _fold(tf, "ticket/SCRUM-99") is None and not _events(tf, "ticket.linked", "ticket/SCRUM-99")


def test_jira_failing_on_links_writes_nothing_and_the_reading_is_still_answered(tf, monkeypatch):
    tf.watch.look(_record(tf))
    _board(tf, "SCRUM-2", issuelinks=[])

    def down():
        raise tf.jira.JiraError("Jira is down")
    monkeypatch.setattr(tf.jira, "linked", down)
    got = tf.watch.read(["arrivals.main"])
    assert isinstance(got["arrivals.main"], float)
    assert _fold(tf, "ticket/SCRUM-2")["blocked_by"] == ["ticket/SCRUM-1"]
    assert len(_events(tf, "ticket.linked")) == 1


# --- the search -------------------------------------------------------------------------------------

@pytest.mark.parametrize("api", ["2", "3"])
def test_the_links_search_asks_for_links_and_parent_capped(tf, monkeypatch, api):
    monkeypatch.setenv("TF_JIRA_API", api)
    monkeypatch.setattr(tf.jira, "OFFLINE", False)
    asked = []

    def call(method, path, body=None, query=None):
        asked.append((method, path, body, query))
        return {"issues": [], "total": 0}
    monkeypatch.setattr(tf.jira, "_call", call)
    assert tf.jira.linked() == {}
    method, path, body, query = asked[0]
    if api == "3":
        assert (method, path) == ("POST", "/search/jql")
        assert body["fields"] == ["issuelinks", "parent"] and body["maxResults"] == 500
        assert body["jql"] == tf.jira._scope()
    else:
        assert (method, path) == ("GET", "/search")
        assert query["fields"] == "issuelinks,parent" and query["maxResults"] == 500
        assert query["jql"] == tf.jira._scope()


@pytest.mark.parametrize("api", ["2", "3"])
def test_the_links_search_pages_to_the_cap_and_an_issue_past_it_keeps_its_relations(tf, monkeypatch, api):
    """Jira answers at most 100 a page: linked() pages up to 500 and stops; the 501st is not looked at, so the
    watcher writes nothing for it (it keeps what it has)."""
    monkeypatch.setenv("TF_JIRA_API", api)
    monkeypatch.setattr(tf.jira, "OFFLINE", False)
    every = [{"key": f"P-{n}", "fields": {"issuelinks": []}} for n in range(1, 602)]
    asked = []

    def call(method, path, body=None, query=None):
        asked.append(body or query)
        at = int((body or {}).get("nextPageToken") or (query or {}).get("startAt") or 0)
        most = min(100, int((body or query)["maxResults"]))
        page = every[at:at + most]
        more = at + most < len(every)
        return {"issues": page, "total": len(every), **({"nextPageToken": str(at + most)} if more else {})}
    monkeypatch.setattr(tf.jira, "_call", call)
    got = tf.jira.linked()
    assert len(got) == 500 and "P-500" in got and "P-501" not in got and len(asked) == 5
    assert [a["maxResults"] for a in asked] == [500, 400, 300, 200, 100]

    written = []
    known = {"ticket/P-501": {"blocked_by": ["ticket/P-1"]}, "ticket/P-1": {"blocked_by": ["ticket/P-2"]}}
    tf.watch.linked(known, written.append)
    assert [e["item"] for e in written] == ["ticket/P-1"], "the one past the cap keeps its blocked_by"


def test_a_search_issue_without_a_key_fails_the_whole_reading(tf, monkeypatch):
    monkeypatch.setattr(tf.jira, "OFFLINE", False)
    monkeypatch.setattr(tf.jira, "_call", lambda *a, **k: {"issues": [{"fields": {"issuelinks": []}}]})
    with pytest.raises(tf.jira.JiraError):
        tf.jira.linked()


# --- the daemon -------------------------------------------------------------------------------------

def test_the_offline_daemon_records_a_blocked_ticket(tf):
    env = {**os.environ, "ERGOSTAT_NO_SOCKET": "1"}
    c = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tf.d), "check"], env=env, capture_output=True,
                       text=True, timeout=120)
    assert c.returncode == 0 and "bad-relation" not in c.stdout, c.stdout + c.stderr
    lines = "".join(json.dumps(x) + "\n" for x in ({"op": "read", "sensor": "arrivals.main", "request": "1"},
                                                   {"op": "stop"}))
    r = subprocess.run(["python3", "bin/watch.py", "serve"], cwd=tf.d, env=env, input=lines, capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0 and [json.loads(x) for x in r.stdout.splitlines()] == [{"reading": 18.0, "request": "1"}]
    assert _fold(tf, "ticket/SCRUM-2")["blocked_by"] == ["ticket/SCRUM-1"]
    assert {e["source"] for e in _events(tf, "ticket.linked")} == {"arrivals.main"}
