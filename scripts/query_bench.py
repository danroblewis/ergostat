#!/usr/bin/env python3
"""The query engine's speed (SPEC §5a, *The query engine*): a record of N events from the EC2 simulator
(tests/fixtures/ec2_stream.py, batch mode, several seeds), the index's upkeep per event, and the times of an indexed
query, an indexed but evaluated one, and a scan.

    uv run python scripts/query_bench.py [--events 200000]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ergostat import eventquery                                   # noqa: E402
from ergostat.store import Events                                 # noqa: E402
from tests.fixtures.ec2_stream import Fleet                       # noqa: E402

QUERIES = {
    "indexed (exact)": "data['detail-type'] == 'EC2 Instance State-change Notification' and data.detail.state == 'running'",
    "indexed (exact, not)": "data.source == 'aws.ec2' and not data.detail.eventName.startswith('Describe')",
    "indexed, then evaluated": "data.detail.eventName == 'RunInstances' and "
                               "data.detail.responseElements.instancesSet.items[0].instanceType == 't3.micro'",
    "scan": "data.detail.state + '' == 'running'",
}


def record(n: int, d: Path) -> Events:
    ev = Events(d)
    start = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc).timestamp()
    seed, total, t = 1, 0, 1_700_000_000.0
    while total < n:
        f = Fleet(seed, 200, start)
        got = f.deliver(f.advance(start + 30 * 86400), float("inf"))[: n - total]
        rows = []
        for e in got:
            t += 0.01
            rows.append({"type": "aws.eventbridge", "data": e, "at": t})
        for i in range(0, len(rows), 20_000):
            ev.add_many(rows[i:i + 20_000])
        total += len(got)
        seed += 1
    return ev


def timed(fn, runs: int = 5) -> float:
    ts = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=200_000)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        ev = record(a.events, Path(tmp))
        t0 = time.perf_counter()
        ix = eventquery.index_for(ev)
        build = time.perf_counter() - t0
        out = {"events": ev.count(), "index_build_s": round(build, 2),
               "upkeep_us_per_event": round(1e6 * ix.upkeep["seconds"] / max(1, ix.upkeep["events"]), 1),
               "index_mb": round((Path(tmp) / eventquery.INDEX).stat().st_size / 1e6, 1)}
        more = [{"type": "aws.eventbridge", "data": {"source": "aws.ec2", "detail": {"state": "running"}}, "at": 2e9 + i}
                for i in range(1000)]
        ev.add_many(more)
        before = dict(ix.upkeep)
        t0 = time.perf_counter()
        eventquery.index_for(ev)
        out["catch_up_1000_ms"] = round(1000 * (time.perf_counter() - t0), 1)
        out["upkeep_us_per_event_live"] = round(1e6 * (ix.upkeep["seconds"] - before["seconds"]) /
                                                max(1, ix.upkeep["events"] - before["events"]), 1)
        for name, q in QUERIES.items():
            r = eventquery.run(ev, {"query": q, "limit": 50})
            ms = 1000 * timed(lambda q=q: eventquery.run(ev, {"query": q, "limit": 50}))
            out[name] = {"ms": round(ms, 1), "total": r["total"], "indexed": r["indexed"], "exact": r.get("exact"),
                         "scanned": r["scanned"], "read": r.get("read"), **({"capped": True} if r.get("capped") else {})}
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
