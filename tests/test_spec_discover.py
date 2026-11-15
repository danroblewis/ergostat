"""Discovery: a loop acting in the record is found (and named as unwritten when nothing in the
model sets its flow); a Prometheus's series become a draft model that compiles."""

import json
import math
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from ergostat import model as mdl
from ergostat.spec import discover as dc
from ergostat.spec import read
from ergostat.store import Project

MODEL = """
stocks:
  queue:
    unit: jobs
    sensor:
      manual: true
  other:
    unit: jobs
    sensor:
      manual: true
flows:
  arrivals:
    to: queue
  served:
    from: queue
    sensor:
      manual: true
  leak:
    from: other
    sensor:
      manual: true
"""


def test_a_flow_that_follows_its_stock_is_a_loop_nobody_wrote_down(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for k in range(240):                                    # 6h, a reading every 90s
        t = now - 6 * 3600 + k * 90
        level = 50 + 40 * math.sin(k / 12)
        p.measurements.add("sensor/queue.main", level, t)
        lagged = 50 + 40 * math.sin((k - 3) / 12)           # the consumer follows the queue, 3 readings later
        p.measurements.add("sensor/served.main", 2 * lagged, t)
        p.measurements.add("sensor/other.main", 10 + k % 7, t)
        p.measurements.add("sensor/leak.main", 5 + (k * 37) % 11, t)
    found = dc.loops(p, p.model.spec, now=now)
    loop = [f for f in found if f["kind"] == "loop"]
    assert [(f["stock"], f["flow"], f["known"]) for f in loop] == [("queue", "served", False)]
    assert 0 < loop[0]["delay"] <= 900
    assert any(f["kind"] == "unanswered" and f["stock"] == "other" for f in found)
    prop = dc.proposal(found, p.model.spec)
    assert "type: external" in prop and "out: flow.served" in prop


def test_a_draft_from_prometheus_compiles(tmp_path):
    meta = {"jobs_queue_depth": [{"type": "gauge", "help": "jobs waiting"}],
            "jobs_processed_total": [{"type": "counter", "help": "jobs done"}],
            "jobs_enqueued_total": [{"type": "counter", "help": "jobs in"}],
            "go_goroutines": [{"type": "gauge", "help": "not a level we want"}]}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({"status": "success", "data": meta}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        text, notes = dc.from_prometheus(f"http://127.0.0.1:{srv.server_address[1]}")
    finally:
        srv.shutdown()
    assert "jobs-queue-depth" in text and "go-goroutines" not in text
    assert "from: jobs-queue-depth" in text and "to: jobs-queue-depth" in text
    (tmp_path / "ergostat.yaml").write_text(text)
    _, problems = read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], problems
