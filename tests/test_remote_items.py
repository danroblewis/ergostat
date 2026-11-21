"""A remote's items and events read in place for the Items and Record pages (SPEC §4c): only a declared remote, an
item id that is allowed, a hard budget of asks per period, one lock per remote across every decision, and nothing
that cannot be read shown as nothing."""

from __future__ import annotations

import json
import threading
import time
import types
import urllib.error
import urllib.request
from urllib.parse import quote

import pytest

from ergostat.remote import client, events, items
from tests.ports import free_port

LOCAL = """
name: home
remotes:
  r:
    url: http://127.0.0.1:1
    token-file: r.token
    every: 60s
  s:
    url: http://127.0.0.1:2
    token-file: r.token
    every: 60s
items:
  thing:
    id: thing/*
stocks:
  queue:
    sensor: {run: echo 1}
"""
DOWN = (0, None, None, "unreachable (refused)")


class Fake:
    """``client.get``, counted: the remote's answers from a small log of events and two items."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.log = [{"seq": i, "type": "thing.made", "item": f"t-{i}", "time": time.time() - 10, "id": f"e{i}"}
                    for i in (1, 2, 3)]
        self.down: tuple | None = None
        self.queue: list = []                          # bodies answered first, as they are
        self.hook = None                               # called with (url, path) before answering
        self.lock = threading.Lock()

    def get(self, url, path, token, params=None, etag=None, timeout=5.0):
        if path in ("model", "readings"):              # the model's own refresh and readings: not this gap's asks
            return DOWN
        with self.lock:
            self.calls.append((url, path, dict(params or {})))
        if self.hook:
            self.hook(url, path)
        if self.down:
            return self.down
        if self.queue:
            return 200, self.queue.pop(0), None, ""
        if path == "counts":
            return 200, {"kinds": {"thing": {"open": 2}}, "total": 2}, None, ""
        if path == "items":
            return 200, {"items": [{"id": "t-1", "kind": "thing", "state": "open"}], "total": 2, "kinds": []}, None, ""
        if path.startswith("items/"):
            return 200, {"id": path[6:], "fields": {"from": "there"}, "record": []}, None, ""
        last = self.log[-1]["seq"] if self.log else 0
        if path == "status":
            return 200, {"last_seq": last}, None, ""
        after, n = int(params["after"]), int(params["n"])
        nxt = min(after + n, last)
        return 200, {"events": [e for e in self.log if after < e["seq"] <= after + n], "next": nxt,
                     "more": nxt < last, "last_seq": last}, None, ""

    def asked(self, path=None):
        return [c for c in self.calls if path is None or c[1] == path]


@pytest.fixture
def site(tmp_path, monkeypatch):
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web import serve as web_serve
    d = tmp_path / "home"
    d.mkdir()
    (d / "ergostat.yaml").write_text(LOCAL)
    (d / "r.token").write_text("tok")
    monkeypatch.setattr(client, "get", lambda *a, **k: DOWN)
    p = Project(mdl.load(d))
    p.events.add("thing.made", item="t-1", data={"from": "here"})          # (ids without a / are local parts' own)
    p.events.add("thing.made", item="thing/1", data={"from": "here"})
    fake = Fake()
    monkeypatch.setattr(client, "get", fake.get)
    clock = [time.time()]
    now = types.SimpleNamespace(time=lambda: clock[0])
    monkeypatch.setattr(items, "time", now)
    monkeypatch.setattr(events, "time", now)
    items._state.clear()
    events._kept.clear()
    server, url = web_serve(p, free_port())
    s = types.SimpleNamespace(url=url, fake=fake, clock=clock, dir=d, spec=p.model.spec)
    yield s
    server.shutdown()
    server.server_close()
    items._state.clear()
    events._kept.clear()


def get(site, path):
    try:
        with urllib.request.urlopen(site.url + path, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def test_an_unconfigured_remote_is_refused_never_answered_locally(site):
    for path in ("/api/items?remote=nope", "/api/items/t-1?remote=nope", "/api/events?remote=nope"):
        code, body = get(site, path)
        assert code == 400, path
        assert body["ok"] is False and body["error"].startswith("no remote nope (this model's: r, s)")
        assert "t-1" not in json.dumps(body) and not {"items", "events", "item"} & set(body)
    assert site.fake.calls == []


def test_a_traversal_id_is_refused_before_any_request(site):
    for bad in ("../events", "incident/../events", "incident/..", "a//b", "/a", "a/", "a/.b", "..", "%2e%2e",
                "a/%2e%2e", "x y", "a/b c", "a\\b", "a" * 201, "a/" + "b" * 199, "a..b", "-x", "a/-x"):
        code, body = get(site, f"/api/items/{quote(bad, safe='')}?remote=r")
        assert code == 400, bad
        assert "item" not in body
        with pytest.raises(items.RemoteRefused) as e:
            items.detail(site.spec, "r", bad)
        assert e.value.code == 400
    with pytest.raises(items.RemoteRefused):
        items.detail(site.spec, "r", "")
    assert get(site, "/api/items/a/b?remote=r")[0] == 400                    # a second path segment: refused too
    assert site.fake.calls == []
    code, body = get(site, "/api/items/t-1?remote=r")
    assert code == 200 and site.fake.asked()[0][1] == "items/t-1"
    assert body["item"]["fields"] == {"from": "there"} and body["item"]["remote"] == "r"
    odd = "a:b@c#d+e=f"
    assert get(site, f"/api/items/{quote(odd, safe='')}?remote=r")[0] == 200
    assert site.fake.asked()[-1][1] == "items/" + quote(odd, safe="")
    for real in ("incident/3", "a/b", "ergostat.model-change/x:1"):      # a kind's ids hold a / (spec/compile.py)
        code, body = get(site, f"/api/items/{quote(real, safe='')}?remote=r")
        assert code == 200 and body["item"]["remote"] == "r", real
        assert site.fake.asked()[-1][1] == "items/" + quote(real, safe="")   # one segment, the / encoded

def test_repeated_listings_in_one_period_ask_the_remote_once_each(site):
    for _ in range(20):
        code, body = get(site, "/api/items?remote=r")
        assert code == 200 and body["ok"] and body["items"][0]["remote"] == "r"
        assert body["counts"] == {"thing": {"open": 2}} and body["url"] == "http://127.0.0.1:1"
    for _ in range(20):
        assert get(site, "/api/items?remote=r&kind=thing")[0] == 200
    assert len(site.fake.asked("counts")) == 1
    assert [c[2].get("kind") for c in site.fake.asked("items")] == [None, "thing"]
    site.clock[0] += 61
    assert get(site, "/api/items?remote=r")[0] == 200
    assert len(site.fake.asked("counts")) == 2 and len(site.fake.asked("items")) == 3


def test_paging_past_the_cache_is_bounded_per_period(site):
    refused = 0
    for off in range(50):
        code, body = get(site, f"/api/items?remote=r&offset={off}")
        if code == 503:
            refused += 1
            assert "again in" in body["error"] and "items" not in body and body["ok"] is False
        else:
            assert code == 200 and body["items"]
    assert len(site.fake.calls) == items.ASKS and refused == 50 - (items.ASKS - 1)
    code, body = get(site, "/api/items?remote=r&offset=0")             # cached: still served, budget spent or not
    assert code == 200 and body["items"]
    assert get(site, "/api/items?remote=r&offset=999999&n=99999")[0] == 503   # clamped, and still within the budget
    assert len(site.fake.calls) == items.ASKS


@pytest.mark.parametrize("down", [DOWN, (401, None, None, "401 no such token"), (403, None, None, "403 forbidden"),
                                  (500, None, None, "500 broken")])
def test_a_remote_that_does_not_answer_is_asked_once_a_period(site, down):
    site.fake.down = down
    for _ in range(10):
        code, body = get(site, "/api/items?remote=r")
        assert code == 502 and body["error"] == down[3] and "items" not in body
    for _ in range(10):
        code, body = get(site, "/api/items/t-1?remote=r")
        assert code == 502 and body["error"] == down[3] and "item" not in body
    assert len(site.fake.calls) == 1
    site.clock[0] += 61                                  # it answers again: read and kept
    site.fake.down = None
    assert get(site, "/api/items?remote=r")[1]["ok"] is True
    site.clock[0] += 61                                  # then fails: what was kept, marked
    site.fake.down = down
    asked = len(site.fake.calls)
    for _ in range(5):
        code, body = get(site, "/api/items?remote=r")
        assert code == 200 and body["ok"] is False and body["why"] == down[3] and body["age"] >= 61 and body["items"]
    assert len(site.fake.calls) == asked + 1


def test_concurrent_item_listings_ask_once(site):
    n, second = 8, threading.Event()
    first = []

    def hook(url, path):
        if not first:
            first.append(path)
            second.wait(1.0)                             # the first ask held until another arrives (or a second)
        else:
            second.set()
    site.fake.hook = hook
    gate, got = threading.Barrier(n), []

    def one():
        gate.wait()
        got.append(items.listing(site.spec, "r", "thing", None, 50, 0))
    ts = [threading.Thread(target=one) for _ in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert len(got) == n and all(g["items"] for g in got)
    assert len(site.fake.asked("counts")) == 1 and len(site.fake.asked("items")) == 1


def test_concurrent_record_polls_read_events_once_a_period(site):
    n, second, first = 8, threading.Event(), []

    def hook(url, path):
        if not first:
            first.append(path)
            second.wait(1.0)
        else:
            second.set()
    site.fake.hook = hook
    gate, got = threading.Barrier(n), []

    def one():
        gate.wait()
        got.append(events.follow(site.spec, "r")[0])
    ts = [threading.Thread(target=one) for _ in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert len(site.fake.asked("status")) == 1 and len(site.fake.asked("events")) == 1
    assert len(got) == n and all(g and [e["seq"] for e in g["events"]] == [1, 2, 3] and g["cursor"] == 3 for g in got)
    # through the gap: a second poll started while the first is reading its page waits, then finds the period read
    site.clock[0] += 61
    site.fake.hook = None
    site.fake.log.append({"seq": 4, "type": "thing.moved", "item": "t-1", "time": time.time(), "id": "e4"})
    later, inside, asked = {}, threading.Event(), threading.Event()
    real = site.fake.get

    def during(url, path, token, params=None, **k):
        if path == "events" and not inside.is_set():
            inside.set()
            later["t"] = threading.Thread(target=lambda: later.update(view=events.follow(site.spec, "r")[0]))
            later["t"].start()
            asked.wait(0.5)                              # (set only if the second poll got in to ask)
        elif inside.is_set():
            asked.set()
        return real(url, path, token, params, **k)
    client.get = during                                  # (the fixture's monkeypatch puts the original back)
    try:
        mine = events.follow(site.spec, "r")[0]
        later["t"].join(30)
    finally:
        client.get = real
    assert not asked.is_set() and len(site.fake.asked("events")) == 2
    assert [e["seq"] for e in mine["events"]] == [1, 2, 3, 4]
    assert [e["seq"] for e in later["view"]["events"]] == [1, 2, 3, 4] and later["view"]["cursor"] == 4


def test_events_are_merged_by_seq_and_a_remade_remote_restarts(site):
    kept, _ = events.follow(site.spec, "r")
    assert [e["seq"] for e in kept["events"]] == [1, 2, 3] and kept["cursor"] == 3
    site.clock[0] += 61                                  # the same page again (a remote that ignores after): nothing added
    site.fake.queue = [{"events": site.fake.log[:], "next": 3, "more": False, "last_seq": 3}]
    kept, _ = events.follow(site.spec, "r")
    assert [e["seq"] for e in kept["events"]] == [1, 2, 3]
    site.clock[0] += 61                                  # its record made again: two events, seq from 1
    site.fake.log = [{"seq": i, "type": "fresh.made", "item": f"n-{i}", "time": time.time(), "id": f"f{i}"} for i in (1, 2)]
    kept, _ = events.follow(site.spec, "r")
    assert [(e["seq"], e["type"]) for e in kept["events"]] == [(1, "fresh.made"), (2, "fresh.made")]
    assert kept["cursor"] == 2 and site.fake.asked("events")[-1][2]["after"] == 0      # max(0, 2 - 1000)
    with events._lock("r"):                              # a long record remade under a long cursor
        events._kept["r|http://127.0.0.1:1"]["cursor"] = 5000
    site.clock[0] += 61
    site.fake.log = [{"seq": i, "type": "again.made", "item": "a-1", "time": time.time(), "id": f"g{i}"}
                     for i in range(1, 1501)]
    kept, _ = events.follow(site.spec, "r")
    assert site.fake.asked("events")[-2][2]["after"] == 5000 and site.fake.asked("events")[-1][2]["after"] == 500
    assert [e["seq"] for e in kept["events"]] == list(range(501, 1501)) and kept["cursor"] == 1500


def test_record_shows_cached_events_with_age_when_the_remote_stops(site):
    code, body = get(site, "/api/events?remote=r")
    assert code == 200 and body["ok"] is True and [e["seq"] for e in body["events"]] == [1, 2, 3]
    assert all(e["remote"] == "r" for e in body["events"])
    assert [e["seq"] for e in get(site, "/api/events?remote=r&n=1&type=thing.*")[1]["events"]] == [3]
    site.clock[0] += 61
    site.fake.down = DOWN
    code, body = get(site, "/api/events?remote=r")
    assert code == 200 and body["ok"] is False and "unreachable" in body["why"] and body["age"] > 0
    assert [e["seq"] for e in body["events"]] == [1, 2, 3]


@pytest.mark.parametrize("how", ["directory", "missing", "empty"])
def test_an_unreadable_token_file_is_an_error_not_no_events(site, how):
    f = site.dir / "r.token"
    f.unlink()
    if how == "directory":
        f.mkdir()
    elif how == "empty":
        f.write_text("")
    for path in ("/api/events?remote=r", "/api/items?remote=r", "/api/items/t-1?remote=r"):
        code, body = get(site, path)
        assert code == 502 and "token-file" in body["error"] and body["ok"] is False, (path, body)
        assert not {"events", "items", "item"} & set(body)
    assert site.fake.calls == []


def test_an_item_from_a_remote_that_does_not_answer(site):
    site.fake.down = DOWN
    code, body = get(site, "/api/items/t-1?remote=r")
    assert code == 502 and "unreachable" in body["error"] and "item" not in body and "here" not in json.dumps(body)
    site.clock[0] += 61
    site.fake.down = None
    assert get(site, "/api/items/t-1?remote=r")[1]["item"]["fields"] == {"from": "there"}
    site.clock[0] += 61
    site.fake.down = DOWN
    code, body = get(site, "/api/items/t-1?remote=r")
    assert code == 200 and body["ok"] is False and body["age"] >= 61 and body["item"]["fields"] == {"from": "there"}
    site.clock[0] += 61
    site.fake.down = (404, None, None, "404 no such item")
    code, body = get(site, "/api/items/t-1?remote=r")
    assert code == 404 and body["error"] == "no such item at r" and "item" not in body


@pytest.mark.parametrize("what,body", [("items", {"items": "x"}), ("counts", []), ("events", {"events": None})])
def test_an_unexpected_answer_is_a_failure(site, what, body):
    if what == "items":                                   # (counts answered well first, then the listing not)
        site.fake.queue = [{"kinds": {}, "total": 0}, body]
    else:
        site.fake.queue = [body] if what == "counts" else [{"last_seq": 3}, body]
    path = "/api/events?remote=r" if what == "events" else "/api/items?remote=r"
    code, got = get(site, path)
    assert code == 502 and got["error"] == "unexpected answer" and got["ok"] is False
    assert not {"events", "items"} & set(got)
    site.clock[0] += 61                                   # read well, then malformed: what was kept, marked
    assert get(site, path)[1]["ok"] is True
    site.clock[0] += 61
    site.fake.queue = [body] if what != "items" else [{"kinds": {}, "total": 0}, body]
    code, got = get(site, path)
    assert code == 200 and got["ok"] is False and got["why"] == "unexpected answer"
    assert got["events" if what == "events" else "items"]


def test_a_hung_remote_blocks_only_its_own_callers(site):
    held, inside = threading.Event(), threading.Event()

    def hook(url, path):
        if url.endswith(":1"):
            inside.set()
            held.wait(30)
    site.fake.hook = hook
    t = threading.Thread(target=lambda: get(site, "/api/items?remote=r"))
    t.start()
    try:
        assert inside.wait(10)
        code, body = get(site, "/api/items?remote=s")
        assert code == 200 and body["remote"] == "s"
        code, body = get(site, "/api/items")
        assert code == 200 and [i["id"] for i in body["items"]] == ["thing/1"]
        assert events.follow(site.spec, "s")[0]["events"]
    finally:
        held.set()
        t.join(30)


def test_local_routes_are_unchanged_without_remote(site):
    code, body = get(site, "/api/items")
    assert code == 200 and body["remotes"] == [{"name": "r", "url": "http://127.0.0.1:1"},
                                               {"name": "s", "url": "http://127.0.0.1:2"}]
    assert [i["id"] for i in body["items"]] == ["thing/1"] and not any("remote" in i for i in body["items"])
    code, one = get(site, "/api/items/t-1")
    assert code == 200 and one["fields"] == {"from": "here"} and "remote" not in one
    code, evs = get(site, "/api/events")
    assert code == 200 and isinstance(evs, list) and [e["item"] for e in evs] == ["t-1", "thing/1"]
    assert site.fake.calls == []
