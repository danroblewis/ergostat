"""A remote composed of remotes (SPEC §4c): instance ids, the chain (``via``) each served part came through, the
checks a consumer makes before composing (malformed, too big, cycles, depth, names, collisions), and readings
carried through a middle with the age they have at their origin."""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
import types
import urllib.request
from pathlib import Path

import pytest

from ergostat import spec as sp
from ergostat.remote import cache, client, compose, instance, measures, readings, serve, tokens
from ergostat.store import state_dir
from tests.ports import free_port, free_ports

A = """
name: a
stocks:
  open:
    unit: incidents
    sensor: {run: echo 3, every: 5s}
flows:
  opened: {to: open}
"""

M = """
name: m
remotes:
  a:
    url: http://127.0.0.1:1
    token-file: a.token
stocks:
  mine:
    sensor: {run: echo 1}
"""

L = """
name: l
remotes:
  m:
    url: http://127.0.0.1:1
    token-file: m.token
"""

FAKE = "http://127.0.0.1:1"


def write(d: Path, text: str, name: str = "ergostat.yaml") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text)
    return d / "ergostat.yaml"


def plant(root: Path, project: str, remote: str, body: dict) -> Path:
    """A remote's served model put in a project's cache, as a refresh would have left it (no network)."""
    d = cache.folder(project, root, remote)
    (d / cache.MODEL).write_text(json.dumps({**body, "fetched": time.time()}))
    (d / cache.STATUS).write_text(json.dumps({"checked": time.time(), "ok": True, "version": body.get("version"),
                                              "next": time.time() + 3600}))
    return d


def own(root: Path, project: str) -> str:
    return instance.own(state_dir(project, root))


def body(inst, sections: dict) -> dict:
    out = {"format": serve.FORMAT, "name": "m", "instance": inst, "sections": sections}
    out["version"] = serve.version_of(out)
    return out


def ids(n: int) -> list[str]:
    return [f"{i + 1:016x}" for i in range(n)]


def load(path: Path):
    spec, problems = sp.read(path, extremes=False)
    assert not [p for p in problems if p.level == "error"], [str(p) for p in problems if p.level == "error"]
    return spec, problems


def codes(problems, code: str) -> list:
    return [p for p in problems if p.code == code]


def middle(tmp_path):
    """A's served model in M's cache; M's own root."""
    a = serve.model(write(tmp_path / "a", A))
    mroot = tmp_path / "m"
    write(mroot, M)
    plant(mroot, "m", "a", a)
    return a, mroot


# --- the instance id ---------------------------------------------------------------------------------------------

def test_the_instance_id_is_made_once_and_kept(tmp_path):
    first = instance.own(tmp_path)
    assert instance.ID.fullmatch(first)
    assert (tmp_path / "instance").read_text() == first + "\n"
    assert instance.own(tmp_path) == first
    assert not list(tmp_path.glob("instance.*.tmp"))                # its temp file deleted


def test_a_racer_in_the_gap_before_the_id_is_written_reads_a_whole_id(tmp_path, monkeypatch):
    real, theirs = instance._fill, []

    def racing(path, text):                     # the competitor runs to the end before this caller's id is written
        if not theirs:
            theirs.append(None)
            theirs[0] = instance.own(tmp_path)
        real(path, text)
    monkeypatch.setattr(instance, "_fill", racing)
    mine = instance.own(tmp_path)
    assert theirs[0] is not None and instance.ID.fullmatch(theirs[0])
    assert mine == theirs[0] == (tmp_path / "instance").read_text().strip()


class _Live:
    def __init__(self, d):
        self.p = types.SimpleNamespace(dir=d, model=types.SimpleNamespace(name="m", spec=None, path=None))

    def get(self):
        return self.p


@pytest.mark.parametrize("bad", ["", "xyz\n", "0" * 17 + "\n", "a directory"])
def test_an_empty_malformed_or_unreadable_instance_file_is_refused_not_replaced(tmp_path, bad):
    from ergostat.web import remote_api
    d = tmp_path / "state"
    d.mkdir()
    f = d / "instance"
    if bad == "a directory":
        f.mkdir()
    else:
        f.write_text(bad)
    with pytest.raises(instance.InstanceError):
        instance.own(d)
    assert f.is_dir() if bad == "a directory" else f.read_text() == bad
    for head in ("model", "status"):
        code, got = remote_api.answer(_Live(d), f"v1/{head}", {})
        assert code == 503 and "instance id" in got["error"]
    lroot = tmp_path / "l"                                           # a consumer whose own id is bad composes no remote
    write(lroot, L)
    plant(lroot, "l", "m", body(ids(1)[0], {"stocks": {"x": {"via": []}}}))
    lf = state_dir("l", lroot) / "instance"
    if bad == "a directory":
        lf.mkdir()
    else:
        lf.write_text(bad)
    spec, problems = load(lroot / "ergostat.yaml")
    assert codes(problems, "remote-instance") and "m-x" not in spec.stocks and "m" in spec.systems
    assert not spec.remotes["m"]["parts"]


# --- serving and composing ---------------------------------------------------------------------------------------

def test_a_middle_serves_its_imported_parts_with_their_chain(tmp_path):
    a, mroot = middle(tmp_path)
    write(mroot, M + "goals:\n  calm: {stock: a-waiting, hold: '<= 3'}\n")     # a reference a serves no part for
    with compose.offline():
        got = serve.model(mroot / "ergostat.yaml")
    me = own(mroot, "m")
    assert got["instance"] == me and a["instance"] != me
    st = got["sections"]["stocks"]
    assert st["a-open"]["via"] == [a["instance"]] and got["sections"]["flows"]["a-opened"]["via"] == [a["instance"]]
    assert st["mine"]["via"] == [] and got["sections"]["goals"]["calm"]["via"] == []
    assert "a-waiting" not in st and "a-gone" not in st                       # stand-ins are not served
    assert all("via" in v for sec in got["sections"].values() for v in sec.values())
    (state_dir("m", mroot) / "instance").write_text("f" * 16 + "\n")          # only the instance changes
    with compose.offline():
        again = serve.model(mroot / "ergostat.yaml")
    assert again["sections"] == got["sections"] and again["version"] != got["version"]


def test_a_middle_never_serves_its_remotes_url(tmp_path):
    a, mroot = middle(tmp_path)
    url = "https://user:secret@a.example.invalid:8443"
    write(mroot, M.replace("http://127.0.0.1:1", url).replace(
        "a.token\n", "a.token\n  b:\n    url: https://b.example.invalid\n    token-file: b.token\n"
                     "    description: the owner's words\n"))
    plant(mroot, "m", "a", a)
    with compose.offline():
        got = serve.model(mroot / "ergostat.yaml")
        spec, _ = load(mroot / "ergostat.yaml")
    text = json.dumps(got)
    assert "secret" not in text and "a.example.invalid" not in text and "b.example.invalid" not in text
    assert got["sections"]["systems"]["a"]["description"] == "remote: a, composed from another ergostat"
    assert got["sections"]["systems"]["b"]["description"] == "the owner's words"      # what the owner wrote is kept
    assert url in spec.systems["a"]                                        # shown locally as before


def test_parts_two_hops_away_are_composed_and_read_through_the_middle(tmp_path):
    a, mroot = middle(tmp_path)
    with compose.offline():
        m = serve.model(mroot / "ergostat.yaml")
    lroot = tmp_path / "l"
    write(lroot, L)
    plant(lroot, "l", "m", m)
    spec, _ = load(lroot / "ergostat.yaml")
    assert spec.stocks["m-a-open"].system == "m-a" and spec.within["m-a"] == "m"
    assert spec.stocks["m-a-open"].sensors["main"].query == {"source": "m", "series": "sensor/a-open.main"}
    assert spec.stocks["m-a-open"].where.chain == (a["instance"], m["instance"])
    assert spec.stocks["m-mine"].where.chain == (m["instance"],)


def test_a_part_coming_back_is_cut_as_a_cycle(tmp_path):
    lroot = tmp_path / "l"
    write(lroot, L)
    me, there = own(lroot, "l"), ids(1)[0]
    plant(lroot, "l", "m", body(there, {"stocks": {"x": {"via": []}, "back": {"via": [me]}},
                                        "flows": {"f": {"from": "x", "to": "back", "via": []}}}))
    spec, problems = load(lroot / "ergostat.yaml")
    assert "m-back" not in spec.stocks and "m-x" in spec.stocks
    assert spec.flows["m-f"].source == "m-x" and spec.flows["m-f"].target is None      # its end became a cloud
    found = codes(problems, "remote-cycle")
    assert len(found) == 1 and "1 of its parts" in found[0].message
    plant(lroot, "l", "m", body(me, {"stocks": {"x": {"via": []}}}))         # the remote is this ergostat itself
    spec, problems = load(lroot / "ergostat.yaml")
    assert "m-x" not in spec.stocks and codes(problems, "remote-cycle") and not spec.remotes["m"]["parts"]


def test_a_chain_longer_than_the_most_is_cut(tmp_path):
    lroot = tmp_path / "l"
    write(lroot, L)
    x, y, z, there = ids(4)
    plant(lroot, "l", "m", body(there, {"stocks": {"three": {"via": [x, y]}, "four": {"via": [x, y, z]}}}))
    spec, problems = load(lroot / "ergostat.yaml")
    assert compose.DEPTH_MOST == 3
    assert "m-three" in spec.stocks and "m-four" not in spec.stocks
    assert codes(problems, "remote-too-deep")


def _sections(there):
    return {"stocks": {"x": {"via": []}, "y": {"via": [ids(9)[8]]}}}


MALFORMED = {
    "no instance": lambda b: b.pop("instance"),
    "instance XYZ": lambda b: b.update(instance="XYZ"),
    "a part without via": lambda b: b["sections"]["stocks"]["x"].pop("via"),
    "via a string": lambda b: b["sections"]["stocks"]["x"].update(via=ids(1)[0]),
    "an id of abc": lambda b: b["sections"]["stocks"]["x"].update(via=["abc"]),
    "a repeated id": lambda b: b["sections"]["stocks"]["x"].update(via=[b["instance"]]),
    "VIA_MOST + 1 ids": lambda b: b["sections"]["stocks"]["x"].update(via=ids(compose.VIA_MOST + 1)),
}


@pytest.mark.parametrize("case", list(MALFORMED))
def test_a_remote_with_missing_or_malformed_instance_or_via_is_refused(tmp_path, case):
    lroot = tmp_path / "l"
    write(lroot, L + "stocks:\n  here: {sensor: {run: echo 1}}\n")
    b = body("e" * 16, _sections("e" * 16))
    MALFORMED[case](b)
    plant(lroot, "l", "m", b)
    spec, problems = load(lroot / "ergostat.yaml")                # the model still loads
    assert "here" in spec.stocks and "m" in spec.systems
    assert not [n for n in spec.stocks if n.startswith("m-")] and not spec.remotes["m"]["parts"]
    assert codes(problems, "remote-malformed")


def test_a_remote_serving_more_parts_than_the_most_is_refused(tmp_path, monkeypatch):
    assert compose.PARTS_MOST == 2000 and not [k for k in compose.KEYS if "most" in k or "parts" in k]
    lroot = tmp_path / "l"
    write(lroot, L.replace("    token-file: m.token\n", "    token-file: m.token\n    parts-most: 5\n"))
    _, problems = sp.read(lroot / "ergostat.yaml", extremes=False)
    assert [p for p in problems if p.code == "unknown-key" and "parts-most" in p.message]
    write(lroot, L)
    monkeypatch.setattr(compose, "PARTS_MOST", 5)
    plant(lroot, "l", "m", body("e" * 16, {"stocks": {f"s{i}": {"via": []} for i in range(6)}}))
    spec, problems = load(lroot / "ergostat.yaml")
    assert codes(problems, "remote-too-big") and not [n for n in spec.stocks if n.startswith("m-")]
    plant(lroot, "l", "m", body("e" * 16, {"stocks": {f"s{i}": {"via": []} for i in range(5)}}))
    spec, problems = load(lroot / "ergostat.yaml")
    assert not codes(problems, "remote-too-big") and len([n for n in spec.stocks if n.startswith("m-")]) == 5


@pytest.mark.parametrize("bad", ["Open", "a_b", "n" * 62, "sensor"])
def test_a_composed_name_that_is_not_a_name_is_refused(tmp_path, bad):
    lroot = tmp_path / "l"
    write(lroot, L.replace("  m:\n", "  mm:\n"))                  # mm-<62 characters> is 65 long
    stocks = {"fine": {"via": []}}
    if bad == "sensor":
        stocks["read"] = {"via": [], "sensors": {"Bad_one": {"kind": "run"}}}
        offending = "Bad_one"
    else:
        stocks[bad] = {"via": []}
        offending = bad if bad != "n" * 62 else f"mm-{bad}"
    plant(lroot, "l", "mm", body("e" * 16, {"stocks": stocks}))
    spec, problems = load(lroot / "ergostat.yaml")
    found = codes(problems, "remote-bad-name")
    assert found and repr(offending) in found[0].message
    assert "mm-fine" in spec.stocks and [n for n in spec.stocks if n.startswith("mm-")] == ["mm-fine"]


def test_a_local_part_named_like_an_imported_one_wins(tmp_path):
    lroot = tmp_path / "l"
    write(lroot, L + "    show: [stock.a-open, stock.other]\ninclude: [more.yaml]\n")
    write(lroot, "stocks:\n  m-a-open:\n    description: our own\n    sensor: {run: echo 1}\n", "more.yaml")
    served = {"systems": {"top": {"via": [], "show": ["stock.a-open", "stock.other"]}},
              "stocks": {"a-open": {"via": []}, "other": {"via": []}},
              "flows": {"a-drain": {"from": "a-open", "to": "other", "via": []}},
              "auxiliaries": {"a-load": {"equation": "stock.a-open * 2", "via": []}}}
    plant(lroot, "l", "m", body("e" * 16, served))
    spec, problems = load(lroot / "ergostat.yaml")
    assert not codes(problems, "defined-twice")
    shown = {x["part"]: x for x in spec.remotes["m"]["show"]}  # m's box never shows our stock as m's measure
    assert shown["stock:m-a-open"]["missing"] is True and shown["stock:m-other"]["missing"] is False
    assert any("stock:m-a-open" in p.message for p in codes(problems, "remote-show-unresolved"))
    box = {"remote": {"name": "m", "state": "ok"}, "label": "m",
           "measures": [{"part": "stock:m-a-open", "value": "1"}]}
    measures.mark(spec, box, {"at": time.time(), "times": {"sensor/m-a-open.main": time.time()}})
    assert box["measures"][0]["missing"] and box["measures"][0]["value"] == "not served"
    write(lroot, L + "include: [more.yaml]\n")                # its top system's served show: the same
    spec, problems = load(lroot / "ergostat.yaml")
    shown = {x["part"]: x for x in spec.remotes["m"]["show"]}
    assert shown["stock:m-a-open"].get("missing") is True and not shown["stock:m-other"].get("missing")
    assert codes(problems, "remote-show-unresolved")
    plant(lroot, "l", "m", body("e" * 16, {k: v for k, v in served.items() if k != "systems"}))
    spec, problems = load(lroot / "ergostat.yaml")
    assert not codes(problems, "defined-twice")
    assert spec.stocks["m-a-open"].description == "our own" and "m-other" in spec.stocks
    drain = spec.flows["m-a-drain"]                     # the remote's flow never drains the local stock
    assert drain.source is None and drain.target == "m-other"
    assert "m-a-open" not in str(spec.auxiliaries["m-a-load"].equation or "")
    taken = codes(problems, "remote-name-taken")
    assert taken and "more.yaml" in taken[0].message and "remote m" in taken[0].message
    assert "stock.m-a-open" not in spec.remotes["m"]["parts"]
    write(lroot, L + "  m-a:\n    url: http://127.0.0.1:1\n    token-file: ma.token\n")       # two remotes collide
    plant(lroot, "l", "m-a", body("d" * 16, {"stocks": {"open": {"via": [], "description": "from m-a"},
                                                        "pool": {"via": []}},
                                             "flows": {"leak": {"from": "open", "to": "pool", "via": []}}}))
    spec, problems = load(lroot / "ergostat.yaml")
    assert spec.stocks["m-a-open"].where.remote == "m" and "stock.m-a-open" in spec.remotes["m"]["parts"]
    leak = spec.flows["m-a-leak"]                       # m-a's flow never drains m's stock of the same name
    assert leak.where.remote == "m-a" and leak.source is None and leak.target == "m-a-pool"
    taken = [p for p in codes(problems, "remote-name-taken") if p.about == "stock.m-a-open"]
    assert taken and "remote m-a" in taken[0].message and not codes(problems, "defined-twice")
    plant(lroot, "l", "m", body("e" * 16, {"systems": {"a": {"via": [], "description": "m's a"}}}))
    spec, problems = load(lroot / "ergostat.yaml")      # a box is put first: m-a's box beats m's served system a
    assert "m-a" in spec.systems and spec.systems["m-a"] != "m's a"
    taken = [p for p in codes(problems, "remote-name-taken") if "m-a" in (p.about or "")]
    assert taken and "remote m" in taken[0].message, [p.message for p in problems]
    assert not codes(problems, "defined-twice")


# --- reading age -------------------------------------------------------------------------------------------------

class _S:
    def __init__(self, q, every=10.0):
        self.query, self.every = q, every


def _consumer(tmp_path):
    lroot = tmp_path / "l"
    write(lroot, L)
    plant(lroot, "l", "m", body("e" * 16, {"stocks": {"x": {"via": [], "sensors": {"main": {"kind": "run"}}}}}))
    (lroot / "m.token").write_text("tok")
    spec, _ = load(lroot / "ergostat.yaml")
    return spec, _S({"source": "m", "series": "sensor/x.main"})


def _answering(monkeypatch, got):
    monkeypatch.setattr(readings.client, "get", lambda *a, **k: (200, got, None, ""))
    readings._kept.clear()


def test_a_reading_with_no_time_or_no_now_is_stale(tmp_path, monkeypatch):
    spec, s = _consumer(tmp_path)
    now = time.time()
    _answering(monkeypatch, {"now": now, "series": {"sensor/x.main": {"value": 4, "time": None}}})
    v, why = readings.read(spec, spec.sources["m"], s)
    assert v is None and "has no time" in why
    _answering(monkeypatch, {"series": {"sensor/x.main": {"value": 4, "time": now}}})
    v, why = readings.read(spec, spec.sources["m"], s)
    assert v is None and "without its own time" in why
    nan, inf = float("nan"), float("inf")                            # JSON's NaN and Infinity literals
    _answering(monkeypatch, {"now": now, "series": {"sensor/x.main": {"value": 4, "time": nan}}})
    v, why = readings.read(spec, spec.sources["m"], s)
    assert v is None and "has no time" in why
    _answering(monkeypatch, {"now": inf, "series": {"sensor/x.main": {"value": 4, "time": inf}}})
    v, why = readings.read(spec, spec.sources["m"], s)
    assert v is None and "without its own time" in why
    _answering(monkeypatch, {"now": nan, "series": {"sensor/x.main": {"value": 4, "time": now}}})
    v, why = readings.read(spec, spec.sources["m"], s)
    assert v is None and "without its own time" in why
    _answering(monkeypatch, {"now": now, "series": {"sensor/x.main": {"value": 4, "time": now - 1}}})
    assert readings.read(spec, spec.sources["m"], s) == (4.0, "")


def test_a_relay_file_that_cannot_be_written_is_said(tmp_path, monkeypatch):
    spec, s = _consumer(tmp_path)
    _answering(monkeypatch, {"now": time.time(), "series": {"sensor/x.main": {"value": 4, "time": time.time()}}})

    def refused(*_a):
        raise OSError("disk full")
    monkeypatch.setattr(readings, "keep", refused)
    v, _ = readings.read(spec, spec.sources["m"], s)
    st = cache.status(cache.folder("l", tmp_path / "l", "m"))
    assert v == 4 and st["read_ok"] is True and "could not be written (disk full)" in st["read_why"]


def test_a_reading_from_the_future_is_refused(tmp_path, monkeypatch):
    spec, s = _consumer(tmp_path)
    now = time.time()
    _answering(monkeypatch, {"now": now, "series": {"sensor/x.main": {"value": 4, "time": now + 60}}})
    v, why = readings.read(spec, spec.sources["m"], s)
    assert v is None and "in its own future" in why
    _answering(monkeypatch, {"now": now, "series": {"sensor/x.main": {"value": 4, "time": now + 2}}})
    assert readings.read(spec, spec.sources["m"], s) == (4.0, "")


def _get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


class _Upstream:
    """A (at the fake url) as the middle's readings see it: its answers set by the test; any other url asked for real."""

    def __init__(self, monkeypatch):
        self.real, self.reply = client.get, None
        monkeypatch.setattr(client, "get", self)

    def __call__(self, url, path, token, params=None, etag=None, timeout=5.0, tls=None):
        if url != FAKE:
            return self.real(url, path, token, params, etag, timeout, tls=tls)
        if path != "readings" or self.reply is None:
            return 0, None, None, "unreachable (refused)"
        return 200, self.reply(), None, ""


@pytest.fixture
def chain(tmp_path, monkeypatch):
    """M (with A's model in its cache, A answered by the test) serving its page; L reading M over it."""
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web import serve as web_serve
    a, mroot = middle(tmp_path)
    (mroot / "a.token").write_text("tok")
    p = Project(mdl.load(mroot))
    up = _Upstream(monkeypatch)
    server, url = web_serve(p, free_port())
    tok = tokens.issue(p.dir, "l")
    lroot = tmp_path / "l"
    write(lroot, L.replace(FAKE, url))
    (lroot / "m.token").write_text(tok)
    readings._kept.clear()
    try:
        yield types.SimpleNamespace(a=a, p=p, up=up, url=url, tok=tok, lroot=lroot, mspec=p.model.spec,
                                    dir=Path(p.model.spec.remotes["a"]["dir"]))
    finally:
        server.shutdown()
        server.server_close()


def _m_reads(c):
    """M's own sensor of a-open reading A once (as its runner would), and recording what it took."""
    readings._kept.clear()
    s = c.mspec.stocks["a-open"].sensors["main"]
    v, why = readings.read(c.mspec, c.mspec.sources["a"], s)
    if v is not None:
        c.p.measurements.add("sensor/a-open.main", v)                  # M's own record: stamped with M's now
    return v, why


def test_a_middle_serves_the_origin_age_not_its_own_time(chain):
    c = chain
    ahead = 1000.0                                                   # A's clock is 1,000 s ahead; its reading 50 s old
    c.up.reply = lambda: {"now": time.time() + ahead, "instance": c.a["instance"],
                          "series": {"sensor/open.main": {"value": 3, "time": time.time() + ahead - 50}}}
    assert _m_reads(c) == (3.0, "")
    got = _get(f"{c.url}/remote/v1/readings?series=sensor/a-open.main&ref=stock.a-open", c.tok)
    now = got["now"]
    for g in (got["series"]["sensor/a-open.main"], got["refs"]["stock.a-open"]):
        assert g["value"] == 3 and abs(g["time"] - (now - 50)) < 1.0, g
    assert got["instance"] == instance.own(c.p.dir)
    latest = c.p.measurements.latest("sensor/a-open.main")          # M did record it, at its own now
    assert latest and latest[0] > now - 5
    for t_now, t_at in ((time.time(), float("nan")), (float("inf"), float("inf"))):   # a NaN age is never kept
        c.up.reply = lambda t_now=t_now, t_at=t_at: {"now": t_now, "instance": c.a["instance"],
                                                     "series": {"sensor/open.main": {"value": 4, "time": t_at}}}
        assert _m_reads(c)[0] is None
        kept = json.loads((c.dir / readings.RELAYED).read_text())
        assert kept["series"]["sensor/open.main"]["age"] is None
        g = _get(f"{c.url}/remote/v1/readings?series=sensor/a-open.main", c.tok)["series"]["sensor/a-open.main"]
        assert g["value"] is None and g["time"] is None and g["why"], g


def test_a_middle_with_its_upstream_down_never_serves_fresh_looking_data(chain):
    c = chain
    t0 = time.time()
    c.up.reply = lambda: {"now": time.time(), "instance": c.a["instance"],
                          "series": {"sensor/open.main": {"value": 3, "time": time.time() - 50}}}
    assert _m_reads(c) == (3.0, "")
    t1 = time.time()
    c.up.reply = None                                                # A stops answering
    v, why = _m_reads(c)
    assert v is None and "unreachable" in why
    got = _get(f"{c.url}/remote/v1/readings?series=sensor/a-open.main", c.tok)["series"]["sensor/a-open.main"]
    assert got["value"] == 3 and "a at" in got["unreachable"]
    assert t0 - 50 - 1 <= got["time"] <= t1 - 50 + 1                 # the old time, not when it was asked again
    lspec, _ = load(c.lroot / "ergostat.yaml")                      # L, reading M for real
    ls = lspec.stocks["m-a-open"].sensors["main"]
    readings._kept.clear()
    v, why = readings.read(lspec, lspec.sources["m"], ls)
    assert v is None and "not current" in why and "a at" in why
    (c.dir / readings.RELAYED).unlink()                              # nothing kept from A at all
    got = _get(f"{c.url}/remote/v1/readings?series=sensor/a-open.main", c.tok)["series"]["sensor/a-open.main"]
    assert got["value"] is None and got["time"] is None and got["why"]
    readings._kept.clear()
    v, why = readings.read(lspec, lspec.sources["m"], ls)
    assert v is None and "no reading" in why
    c.up.reply = lambda: {"now": time.time(), "instance": "9" * 16,  # A's state remade: a new id, M's cache still old
                          "series": {"sensor/open.main": {"value": 5, "time": time.time() - 1}}}
    assert _m_reads(c) == (5.0, "")
    got = _get(f"{c.url}/remote/v1/readings?series=sensor/a-open.main", c.tok)["series"]["sensor/a-open.main"]
    assert got["value"] is None and got["time"] is None and "9" * 16 in got["why"]
    readings._kept.clear()
    v, why = readings.read(lspec, lspec.sources["m"], ls)
    assert v is None


def test_a_larger_answer_than_the_most_fails_the_call():
    class Big(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(client.BODY_MOST + 1))
            self.end_headers()
            chunk = b" " * 2**20
            left = client.BODY_MOST + 1
            try:
                while left:
                    n = min(left, len(chunk))
                    self.wfile.write(chunk[:n])
                    left -= n
            except OSError:
                pass

        def log_message(self, *a):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), Big)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        code, got, _, why = client.get(f"http://127.0.0.1:{server.server_address[1]}", "model", "tok", timeout=10)
        assert code == 0 and got is None and "too large" in why
    finally:
        server.shutdown()
        server.server_close()


# --- end to end ----------------------------------------------------------------------------------------------------

def _cli(d: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ergostat", "-C", str(d), *args], capture_output=True, text=True,
                          timeout=60)


def _start(d: Path, port: int) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "run", "--foreground", "--port", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def _stop(proc: subprocess.Popen) -> None:
    import signal
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(5)


def _until(what, seconds: float, why: str):
    end, last = time.time() + seconds, None
    while time.time() < end:
        try:
            last = what()
            if last:
                return last
        except Exception as e:                  # (a page not up yet)
            last = e
        time.sleep(0.5)
    raise AssertionError(f"{why}: not within {seconds:g}s (last: {last!r})")


def _page(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


@pytest.mark.slow
def test_three_instances_read_a_part_two_hops_away_and_mark_it_stale_when_the_origin_stops(tmp_path):
    pa, pm, pl = free_ports(3)
    aroot, mroot, lroot = tmp_path / "a", tmp_path / "m", tmp_path / "l"
    write(aroot, "name: a\nstocks:\n  open:\n    sensor: {run: echo 7, every: 3s}\n")
    write(mroot, f"name: m\nremotes:\n  a: {{url: 'http://127.0.0.1:{pa}', token-file: a.token, every: 10s}}\n")
    write(lroot, f"name: l\nremotes:\n  m: {{url: 'http://127.0.0.1:{pm}', token-file: m.token, every: 10s}}\n")
    procs: list[subprocess.Popen] = []
    try:
        procs.append(_start(aroot, pa))
        _until(lambda: _page(f"http://127.0.0.1:{pa}/api/status")["running"], 30, "A's page")
        tok = _cli(aroot, "remote", "token", "m")
        assert tok.returncode == 0, tok.stderr
        (mroot / "a.token").write_text(tok.stdout.strip())
        procs.append(_start(mroot, pm))
        _until(lambda: _page(f"http://127.0.0.1:{pm}/api/status")["running"], 30, "M's page")
        tok = _cli(mroot, "remote", "token", "l")
        assert tok.returncode == 0, tok.stderr
        (lroot / "m.token").write_text(tok.stdout.strip())
        procs.append(_start(lroot, pl))
        base = f"http://127.0.0.1:{pl}"
        _until(lambda: _page(f"{base}/api/status")["running"], 30, "L's page")

        def reached():
            got = _page(f"{base}/api/part/stock/m-a-open")["now"]
            return got if got and got.get("value") == 7 else None
        _until(reached, 90, "A's value read at L, two hops away")
        _stop(procs[0])                                              # the origin stops
        stopped = time.time()

        def failed():
            evs = _page(f"{base}/api/events?type=sensor.failed&n=50")
            return [e for e in evs if e["item"] == "m-a-open.main" and e["time"] > stopped
                    and any(w in (e.get("data") or {}).get("why", "") for w in ("stale", "not current", "unreachable",
                                                                               "no reading"))]
        said = _until(failed, 120, "L's sensor failing as stale or unreachable")
        at = _page(f"{base}/api/part/stock/m-a-open")["now"]["at"]
        assert said and at is not None
        first_fail = min(e["time"] for e in said)

        def failed_again():                                          # one more failure after the first: a whole period
            return [e for e in failed() if e["time"] > first_fail]
        _until(failed_again, 60, "a second failure of L's sensor")
        assert _page(f"{base}/api/part/stock/m-a-open")["now"]["at"] <= first_fail       # nothing newer recorded
    finally:
        for p in procs:
            _stop(p)
