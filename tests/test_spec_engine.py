"""ergostat closes a loop itself: a YAML model run by the engine holds its goal, records what was
commanded and what was moved, holds (does not queue) commands while a block runs, and reads a
Prometheus source."""

import json
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from ergostat import model as mdl
from ergostat.spec.engine import Engine, number_in, prometheus
from ergostat.store import Project

LOOP = """
name: t
stocks:
  inbox:
    unit: files
    sensor:
      run: mkdir -p inbox; ls inbox | wc -l
      every: 0.3s
flows:
  arrivals:
    to: inbox
  processed:
    from: inbox
goals:
  inbox-short:
    stock: inbox
    hold: "<= 6"
    tolerance: 2
blocks:
  keep-short:
    type: onoff
    goal: inbox-short
    until: "<= 3"
    out: block.worker
  worker:
    type: program
    run: ls inbox | head -2 > .batch; (cd inbox && xargs rm -f < ../.batch); wc -l < .batch
    in: block.keep-short
    out: flow.processed
  drop:
    type: program
    run: mkdir -p inbox; mktemp inbox/j.XXXXXX > /dev/null; mktemp inbox/j.XXXXXX > /dev/null; echo 2
    every: 0.4s
    out: flow.arrivals
"""


def run_for(tmp_path, text: str, seconds: float) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    p = Project(mdl.load(tmp_path))
    e = Engine(p, say=lambda s: None)
    e.start_all()
    time.sleep(seconds)
    e.close()
    return p


def test_the_engine_closes_the_loop(tmp_path):
    p = run_for(tmp_path, LOOP, 6)
    ev = p.events
    offs = ev.query(n=None, type="loop.off", item="inbox-short")
    backs = ev.query(n=None, type="loop.holding", item="inbox-short")
    assert offs and len(backs) >= 2, "the goal went off and came back"
    moved = ev.query(n=None, type="valve.opened", item="worker")
    assert moved and all(e["data"]["flow"] == "processed" for e in moved)
    assert ev.query(n=None, type="block.commanded", item="worker")
    decided = [e["data"]["decision"] for e in ev.query(n=None, type="controller.decided", item="inbox-short")]
    assert "act: worker" in decided and "stop: worker" in decided
    level = p.measurements.latest("sensor/inbox.main")[1]
    assert level <= 12, "held near the goal, not running away"


def test_a_slow_block_is_not_queued_up(tmp_path):
    slow = LOOP.replace("run: ls inbox | head -2", "run: sleep 1.5; ls inbox | head -2").replace("every: 0.4s", "every: 0.2s")
    p = run_for(tmp_path, slow, 5)
    starts = p.events.query(n=None, type="agent.started", item="worker")
    ends = p.events.query(n=None, type="agent.ran", item="worker") + p.events.query(n=None, type="agent.failed", item="worker")
    assert starts and len(starts) <= len(ends) + 1, "never two runs at once"
    assert len(starts) <= 4                       # about 5s / 1.5s: no backlog of held commands


def test_commanded_amount_is_clamped_by_max(tmp_path):
    text = """
    stocks:
      q:
        unit: jobs
        sensor:
          run: echo 50
          every: 0.3s
    flows:
      done:
        from: q
    goals:
      short:
        stock: q
        hold: "<= 10"
    blocks:
      size:
        type: proportional
        goal: short
        gain: 1
        out: block.w
      w:
        type: program
        run: python3 -c "import json,sys; print(json.load(sys.stdin)['command']['amount'])"
        in: block.size
        out: flow.done
        max: 7
    """
    p = run_for(tmp_path, text, 2)
    cmd = p.events.query(n=None, type="block.commanded", item="w")
    assert cmd and cmd[0]["data"]["amount"] == 7 and cmd[0]["data"]["asked"] == 40
    moved = p.events.query(n=None, type="valve.opened", item="w")
    assert moved and moved[0]["data"]["amount"] == 7


def test_number_in():
    assert number_in("12\n", None) == (12.0, "")
    assert number_in('{"value": 3}\n', None) == (3.0, "")
    assert number_in("cleaned 4 files\n", r"cleaned (\d+)") == (4.0, "")
    assert number_in("nothing\n", None)[0] is None


def test_a_prometheus_query_must_return_one_series():
    answers = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps(answers["now"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        answers["now"] = {"status": "success", "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1, "42"]}]}}
        assert prometheus(url, "sum(x)", 2) == (42.0, "")
        answers["now"] = {"status": "success", "data": {"resultType": "vector", "result": [{}, {}]}}
        v, why = prometheus(url, "x", 2)
        assert v is None and "2 series" in why
    finally:
        srv.shutdown()
