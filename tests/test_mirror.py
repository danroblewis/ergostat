"""Mirroring an outside log (SPEC §2, ``collect``'s ``mirror:``): each entry recorded once, under the cite of its
position (``cite:<sensor>:<type>:<position>``), the cursor confirmed against the record and recovered from it when
the collector's memory is lost; only the sensor named in a cite records it, and nothing pushed carries one."""

import io
import json
import textwrap
import time
import types
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

import pytest

from ergostat import mirror, rollup
from ergostat import model as mdl
from ergostat.intake import envelope
from ergostat.library.run import collect
from ergostat.mirror import MirrorError
from ergostat.spec.engine import Engine, observations
from ergostat.store import Project
from tests.ports import free_port
from tests.test_spec_engine import run_for

SENSOR = "feed-arriving.main"
ARGS = ["--name", "feed", "--kind", "q", "--command", 'echo "$ERGOSTAT_CURSOR" > cur.txt; cat src.jsonl',
        "--cursor-field", "n", "--mirror"]


class Mirror:
    def __init__(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
        monkeypatch.delenv("ERGOSTAT_STATE_DIR", raising=False)
        monkeypatch.setenv("ERGOSTAT_SENSOR", SENSOR)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "ergostat.yaml").write_text("name: m\n")
        self.dir, self.mp = tmp_path, monkeypatch
        self.p = Project(mdl.load(tmp_path))
        self.mem = self.p.dir / "library" / "feed" / "collect.json"

    def source(self, recs):
        (self.dir / "src.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))

    def run(self, args=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                rc = collect.main(args or ARGS)
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 1
                if not isinstance(e.code, int):
                    print(e.code, file=err)
        return rc, out.getvalue(), err.getvalue()

    def poll(self, record=True, sensor=SENSOR, args=None):
        """One poll as the engine runs it: its lines recorded (through observations and the engine's observer) when
        it exits 0, else a sensor.failed."""
        rc, out, err = self.run(args)
        if record and rc == 0:
            self.observe(out, sensor)
        elif record:
            self.p.events.add("sensor.failed", item=sensor, source="ergostat", data={"why": f"exited {rc}: {err[:200]}"})
        return rc, [json.loads(x) for x in out.splitlines() if x.startswith("{")], err

    def observe(self, out, sensor=SENSOR):
        Engine._observer(types.SimpleNamespace(p=self.p, spec=self.p.model.spec, say=lambda s: None), sensor)(*observations(out))

    def cursor(self):
        return (self.dir / "cur.txt").read_text().strip()


@pytest.fixture
def m(tmp_path, monkeypatch):
    return Mirror(tmp_path, monkeypatch)


def ns(said):
    return [x["data"]["n"] for x in said]


# ---- the cite id


def test_position_types_and_order():
    assert mirror.position(9, "int") == mirror.position("9", "int") == 9 < mirror.position("10", "int")
    for bad in (10.0, 1.5, -1, "09", True, "", "-3", None):
        with pytest.raises(MirrorError) as e:
            mirror.position(bad, "int")
        assert str(e.value)
    assert mirror.position("2026-01-02T03:04:05Z", "text") == "2026-01-02T03:04:05Z"
    with pytest.raises(MirrorError):
        mirror.position("a b", "text")
    c = mirror.cite("a.main", "i", "10")
    assert c == "cite:a.main:i:10" and mirror.parse(c) == ("a.main", "i", 10) and isinstance(mirror.parse(c)[2], int)
    t = mirror.cite("a.main", "t", "2026-01-02T03:04:05Z")
    assert mirror.parse(t) == ("a.main", "t", "2026-01-02T03:04:05Z")
    for bad in ("cite:a.main:i:09", "cite:a:x:1", "cite::i:1", "x:a:i:1", "cite:a.main:i"):
        with pytest.raises(MirrorError):
            mirror.parse(bad)
    with pytest.raises(MirrorError, match="both as whole numbers and as text"):
        mirror.key("i", 1, "t", "a.main")
    assert mirror.valid("cite:a.main:i:1", "a.main") is None and "only the sensor a.main" in mirror.valid("cite:a.main:i:1", "b.main")


# ---- the confirmed cursor, and lost memory


def test_the_confirmed_cursor_crosses_9_to_10(m):
    m.source([{"id": "a", "n": 8}, {"id": "b", "n": "9"}, {"id": "c", "n": 10}])
    rc, said, err = m.poll()
    assert rc == 0 and ns(said) == [8, "9", 10] and said[2]["id"] == f"cite:{SENSOR}:i:10", err
    rc, said, err = m.poll()
    assert rc == 0 and said == [] and m.cursor() == "10", err
    assert {e["id"] for e in m.p.events.query(n=None, source=SENSOR)} == {f"cite:{SENSOR}:i:{n}" for n in (8, 9, 10)}


@pytest.mark.parametrize("lose", ["delete", "garble"])
def test_lost_memory_resumes_after_10_not_9(m, lose):
    m.source([{"id": "a", "n": 8}, {"id": "b", "n": "9"}, {"id": "c", "n": 10}])
    m.poll()
    m.poll()
    if lose == "delete":
        m.mem.unlink()
    else:
        m.mem.write_text("{not json")
    rc, said, err = m.poll()
    assert rc == 0 and said == [] and m.cursor() == "10", err
    assert mirror.recorded(m.p.events, SENSOR) == ("i", 10)


def test_lost_memory_after_rollup_keeps_the_cite(m):
    m.source([{"id": "ab"[n % 2], "n": n} for n in range(1, 11)])
    rc, said, _ = m.poll()
    assert rc == 0 and len(said) == 10
    m.poll()
    got = rollup.compact(m.p, now=time.time() + 30 * 86400)
    assert got["items"] == 2
    assert not [e for e in m.p.events.query(n=None) if e["id"].startswith("cite:")], "only the snapshots hold them now"
    m.mem.unlink()
    rc, said, err = m.poll()
    assert rc == 0 and said == [] and m.cursor() == "10", err
    m.source([{"id": "a", "n": 11}])
    assert ns(m.poll()[1]) == [11]


def test_mixed_position_types_in_the_record_fail_closed(m):
    m.p.events.add("q.arrived", item="q/1", source=SENSOR, id=f"cite:{SENSOR}:i:3")
    m.p.events.add("q.arrived", item="q/2", source=SENSOR, id=f"cite:{SENSOR}:t:abc")
    m.source([{"id": "a", "n": 4}])
    rc, said, err = m.poll()
    assert rc == 1 and said == [] and "both as whole numbers and as text" in err


def test_lost_memory_reads_only_this_sensor_s_cites(m):
    m.p.events.add("q.arrived", item="q/1", source=SENSOR, id=f"cite:{SENSOR}:i:7")
    m.p.events.add("q.arrived", item="q/2", source=SENSOR)                                   # pushed as it, no id
    m.p.events.add("q.arrived", item="q/3", source="other.main", id="cite:other.main:i:500")
    m.p.events.add("q.arrived", item="q/4", source="other.main", id=f"cite:{SENSOR}:i:900")   # not its source
    m.p.events.add("q.arrived", item="q/5", source=SENSOR, id="cite:other.main:i:600")       # not its log
    assert mirror.recorded(m.p.events, SENSOR) == ("i", 7)
    assert mirror.recorded(m.p.events, "other.main") == ("i", 500)
    assert mirror.recorded(m.p.events, "nobody.main") is None


def test_a_store_error_while_recovering_fails_the_poll(m, monkeypatch):
    m.source([{"id": "a", "n": 1}])

    def broken(*a, **k):
        raise OSError("disk gone")
    monkeypatch.setattr(mirror, "recorded", broken)
    rc, said, err = m.poll()
    assert rc == 1 and said == [] and "disk gone" in err


# ---- what fails a poll, and what it leaves


def test_a_position_the_engine_would_refuse_fails_the_poll_with_its_reason(m):
    m.source([{"id": "a", "n": 1}, {"id": "b", "n": 2}])
    m.poll()
    m.source([{"id": "a", "n": 1}, {"id": "b", "n": 2}, {"id": "c", "n": 1.5}, {"id": "d", "n": 3}])
    rc, said, err = m.poll()
    assert rc == 1 and said == [] and "1.5" in err and "'c'" in err
    kept = json.loads(m.mem.read_text())["mirror"]
    assert {k: kept[k] for k in ("type", "cursor", "said")} == {"type": "i", "cursor": 2, "said": []}
    m.source([{"id": "d", "n": 3}, {"id": "e"}])
    rc, said, err = m.poll()
    assert rc == 1 and said == [] and "has no n" in err
    assert json.loads(m.mem.read_text())["mirror"]["cursor"] == 2
    rc, _, err = m.poll(args=[*ARGS[:-3], "--mirror"])
    assert rc == 2


def test_no_sensor_name_no_mirror(m):
    m.mp.delenv("ERGOSTAT_SENSOR")
    m.source([{"id": "a", "n": 1}])
    rc, said, err = m.poll(record=False)
    assert rc == 1 and said == [] and "ERGOSTAT_SENSOR is not set" in err


@pytest.mark.parametrize("refused", [False, True])
def test_a_said_position_not_recorded_fails_the_next_poll_then_is_read_again(m, refused):
    m.source([{"id": "a", "n": 1}, {"id": "b", "n": 2}])
    rc, said, _ = m.poll(record=False)                      # lost: a timeout, a crash, the engine refusing them
    assert rc == 0 and ns(said) == [1, 2]
    if refused:
        m.p.events.add("sensor.refused", item=SENSOR, source="ergostat", data={"why": "the engine said no"})
    rc, said, err = m.poll()
    assert rc == 1 and said == [] and f"position 1 of {SENSOR} was said but not recorded" in err
    assert ("the engine said no" if refused else "not in the record") in err
    rc, said, err = m.poll()
    assert rc == 0 and ns(said) == [1, 2] and m.cursor() == "", err
    rc, said, err = m.poll()
    assert rc == 0 and said == [] and m.cursor() == "2", err


def test_an_older_refusal_is_not_given_as_the_reason_for_a_later_loss(m):
    # Fails if the reason is read at any age (no after_seq of the poll that said them).
    m.p.events.add("sensor.refused", item=SENSOR, source="ergostat", data={"why": "a refusal from long ago"})
    m.source([{"id": "a", "n": 1}])
    rc, said, _ = m.poll(record=False)
    assert rc == 0 and ns(said) == [1]
    rc, said, err = m.poll()
    assert rc == 1 and "not in the record" in err and "long ago" not in err, err


def test_a_partly_recorded_poll_moves_the_cursor_to_what_was_recorded(m):
    m.source([{"id": "a", "n": 1}, {"id": "b", "n": 2}, {"id": "c", "n": 3}])
    rc, out, _ = m.run()
    m.observe(out.splitlines()[0])                          # only the first line made it
    rc, said, err = m.poll()
    assert rc == 1 and "position 2 of" in err
    rc, said, err = m.poll()
    assert rc == 0 and ns(said) == [2, 3] and m.cursor() == "1", err


def test_a_log_that_went_back_stops_the_mirror(m):
    m.source([{"id": str(n), "n": n} for n in range(11)])
    m.poll()
    m.poll()
    m.source([{"id": str(n), "n": n} for n in range(11)])  # the whole log again: skipped quietly
    rc, said, err = m.poll()
    assert rc == 0 and said == [], err
    m.source([{"id": str(n), "n": n} for n in range(4)])
    rc, said, err = m.poll()
    assert rc == 1 and said == [] and "went back: its newest entry 3 is before the cursor 10" in err


def test_a_restarted_log_that_grew_past_the_cursor_stops_the_mirror(m):
    m.source([{"id": f"old-{n}", "n": n} for n in range(11)])
    m.poll()
    m.poll()
    m.source([{"id": f"new-{n}", "n": n} for n in range(16)])   # restarted, and already past 10
    rc, said, err = m.poll()
    assert rc == 1 and said == [] and "its entry at the cursor 10 is not the one recorded" in err


def test_two_records_at_one_position_fail_the_poll(m):
    m.source([{"id": "a", "n": 1}, {"id": "b", "n": 1}])
    rc, said, err = m.poll()
    assert rc == 1 and said == [] and "two different records at position 1" in err
    m.source([{"id": "a", "n": 1}, {"id": "a", "n": 1}])
    assert ns(m.poll()[1]) == [1]


def test_at_most_5000_entries_a_poll(m):
    m.source([{"id": str(n), "n": n} for n in range(6000, 0, -1)])
    rc, said, _ = m.poll(record=False)
    assert rc == 0 and ns(said) == list(range(1, 5001))
    m.p.events.add_many([{"type": x["event"], "item": x["item"], "source": SENSOR, "data": x["data"], "id": x["id"]}
                         for x in said])
    rc, said, err = m.poll(record=False)
    assert rc == 0 and ns(said) == list(range(5001, 6001)) and m.cursor() == "5000", err


def test_text_positions_order_as_text(m):
    m.source([{"id": "a", "at": "2026-01-02T03:04:05Z"}, {"id": "b", "at": "2026-01-02T03:04:06Z"}])
    args = [*ARGS[:-3], "--cursor-field", "at", "--mirror", "--position", "text"]
    rc, said, err = m.poll(args=args)
    assert rc == 0 and said[1]["id"] == f"cite:{SENSOR}:t:2026-01-02T03:04:06Z", err
    m.mem.unlink()
    rc, said, err = m.poll(args=args)
    assert rc == 0 and said == [] and m.cursor() == "2026-01-02T03:04:06Z", err


# ---- the engine: a cite only from the sensor whose log it is


def test_a_sensor_line_with_a_plain_id_is_recorded_as_on_main(m):
    m.observe('{"event": "q.seen", "item": "q/1", "id": "x"}\n{"event": "q.seen", "item": "q/2", "id": 7}')
    got = m.p.events.query(n=None, type="q.seen")
    assert len(got) == 2 and all(len(e["id"]) == 32 for e in got)


def test_the_engine_refuses_a_cite_of_another_sensor_s_log(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    (tmp_path / "src.jsonl").write_text("".join(json.dumps({"id": str(n), "n": n}) + "\n" for n in (1, 2, 3)))
    feed = """
    name: m
    uses:
      feed:
        use: collect
        with: {kind: q, command: cat src.jsonl, mirror: true, cursor-field: n, poll: 0.5s}
    """
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(feed))
    spec = mdl.load(tmp_path).spec
    first = next(f"{f.name}.{n}" for f in spec.flows.values() for n, s in f.sensors.items() if s.run and "collect" in s.run)
    (tmp_path / "other.sh").write_text(f"echo '{json.dumps({'event': 'q.arrived', 'item': 'q/x', 'id': f'cite:{first}:i:999'})}'"
                                       "\necho 1\n")
    p = run_for(tmp_path, feed + """
    stocks:
      other:
        unit: x
        sensor:
          run: sh other.sh
          every: 0.3s
    """, 3)
    assert not m_ids(p, f"cite:{first}:i:999")
    why = [e["data"]["why"] for e in p.events.query(n=None, type="sensor.refused", item="other.main")]
    assert why and "only the sensor" in why[0]
    assert mirror.recorded(p.events, first) == ("i", 3)
    assert {e["id"] for e in p.events.query(n=None, type="q.arrived")} == {f"cite:{first}:i:{n}" for n in (1, 2, 3)}


def m_ids(p, id):
    return [e for e in p.events.query(n=None) if e["id"] == id]


@pytest.mark.slow
def test_mirror_end_to_end_through_the_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    (tmp_path / "src.jsonl").write_text("".join(json.dumps({"id": f"t{n}", "n": n, "event": "arrived"}) + "\n"
                                                for n in (5, 9, 10)))
    model = """
    name: m
    uses:
      feed:
        use: collect
        with: {kind: q, command: cat src.jsonl, mirror: true, cursor-field: n, poll: 0.4s}
    """
    p = run_for(tmp_path, model, 3)
    got = p.events.query(n=None, type="q.arrived")
    assert len(got) == 3 and len({e["source"] for e in got}) == 1, p.events.query(n=None, type="sensor.*")
    src = got[0]["source"]
    assert src.endswith(".main") and {e["id"] for e in got} == {f"cite:{src}:i:{n}" for n in (5, 9, 10)}
    assert {e["item"] for e in got} == {"q/t5", "q/t9", "q/t10"}
    (p.dir / "library" / "feed" / "collect.json").unlink()
    p = run_for(tmp_path, model, 2)
    assert len(p.events.query(n=None, type="q.arrived")) == 3
    assert not p.events.query(n=None, type="sensor.failed,sensor.refused", item=src)


# ---- nothing else records a cite id


def _post(url: str, body: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


HOOKED = """
name: m
intake:
  hooks:
    pager:
      event: {from: kind, map: {fired: alert.fired}}
      item: "alert/{key}"
      id: "cite:{key}"
"""


@pytest.fixture
def page(tmp_path, monkeypatch):
    from ergostat.web import serve
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    (tmp_path / "ergostat.yaml").write_text(HOOKED)
    p = Project(mdl.load(tmp_path))
    server, url = serve(p, free_port())
    yield p, url, (p.dir / "intake.token").read_text().strip()
    server.shutdown()
    server.server_close()


def test_push_refuses_a_cite_id(page):
    p, url, t = page
    body = json.dumps([{"event": "q.arrived", "item": "q/2", "id": "fine-1"},
                       {"event": "q.arrived", "item": "q/1", "id": "cite:a.main:i:1", "source": "a.main"}]).encode()
    code, got = _post(f"{url}/api/events?token={t}", body)
    assert code == 400 and "a mirror's own" in json.dumps(got)
    assert p.events.count() == 0


def test_a_webhook_refuses_a_cite_id(page):
    p, url, t = page
    code, got = _post(f"{url}/api/hooks/pager?token={t}", json.dumps({"kind": "fired", "key": "a.main:i:1"}).encode())
    assert code == 400 and "a mirror's own" in json.dumps(got)
    assert not m_ids(p, "cite:a.main:i:1") and not p.events.query(n=None, type="alert.fired")


def test_the_socket_event_op_refuses_a_cite_id(tmp_path, monkeypatch):
    from ergostat.calls import ops
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    (tmp_path / "ergostat.yaml").write_text("name: m\n")
    p = Project(mdl.load(tmp_path))
    eng = types.SimpleNamespace(p=p, spec=p.model.spec)
    with pytest.raises(Exception, match="a mirror's own"):
        ops.event(eng, {"events": [{"event": "q.arrived", "item": "q/1", "id": "cite:a.main:i:1"}], "source": "a.main"})
    assert p.events.count() == 0
    ops.event(eng, {"events": [{"event": "q.arrived", "item": "q/1", "id": "plain-1"}], "source": "a.main"})
    assert m_ids(p, "plain-1")


def test_event_add_without_an_engine_takes_no_cite_id(tmp_path, monkeypatch):
    from ergostat.cli import main
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ERGOSTAT_SOCKET", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ergostat.yaml").write_text("name: m\n")
    with pytest.raises(SystemExit):
        main(["event", "--add", "q.x", "--item", "q/1", "--as", "a.main", "--id", "cite:a.main:i:1"])
    assert main(["event", "--add", "q.x", "--item", "q/1", "--as", "a.main"]) == 0
    got = Project(mdl.load(tmp_path)).events.query(n=None, type="q.x")
    assert len(got) == 1 and got[0]["source"] == "a.main" and not got[0]["id"].startswith("cite:")


def test_a_block_line_with_a_cite_id_is_recorded_under_a_fresh_id(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    (tmp_path / "b.sh").write_text(f"echo '{json.dumps({'event': 'q.seen', 'item': 'q/1', 'id': 'cite:s.main:i:1'})}'\necho 0\n")
    p = run_for(tmp_path, """
    name: m
    stocks:
      s: {unit: x, sensor: {run: echo 1, every: 1s}}
    flows:
      f: {to: s}
    blocks:
      b:
        type: program
        run: sh b.sh
        every: 0.3s
        out: flow.f
    """, 2)
    assert p.events.query(n=None, type="q.seen"), "the block's line was recorded"
    assert not m_ids(p, "cite:s.main:i:1")


def test_a_legacy_agent_line_with_a_cite_id_is_recorded_under_a_fresh_id(m):
    from ergostat.runner import Recorder
    rec = Recorder(m.p, types.SimpleNamespace(name="a.main", parse=None), None)
    assert rec.take(json.dumps({"event": "q.seen", "item": "q/1", "id": f"cite:{SENSOR}:i:1"}))
    assert m.p.events.query(n=None, type="q.seen") and not m_ids(m.p, f"cite:{SENSOR}:i:1")


@pytest.mark.parametrize("kind", ["sqlite", "segments"])
def test_a_pushed_id_twice_is_still_recorded_once(tmp_path, kind):
    from ergostat.segments import Segments
    from ergostat.store import Events
    p = types.SimpleNamespace(events=Events(tmp_path) if kind == "sqlite" else Segments(tmp_path, seal=7))
    one = [{"event": "q.arrived", "item": "q/1", "id": "delivery-1"}]
    assert envelope.record(p, one)["recorded"] == 1
    assert envelope.record(p, one)["recorded"] == 0
    two = [{"event": "q.arrived", "item": "q/2", "id": "d-2"}, {"event": "q.arrived", "item": "q/3", "id": "d-3"}]
    assert envelope.record(p, two)["recorded"] == 2 and envelope.record(p, two)["recorded"] == 0
    assert p.events.count() == 3
