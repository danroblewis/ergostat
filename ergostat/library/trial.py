"""A short run of a copy of the project, to see what one system does: ``python -m ergostat.library.trial SCRATCH
SECONDS SYSTEM [--blocks]``, with ``ERGOSTAT_HOME`` set to a scratch folder of its own, so nothing reaches the
project's record. It prints one JSON object: what moved in the system, what each block did, what failed and why."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def summarise(p, spec, system: str, began: float) -> dict:
    ev = p.events
    members = {n for n in (*spec.stocks, *spec.flows, *spec.auxiliaries, *spec.goals, *spec.blocks)
               if _system_of(spec, n) and (_system_of(spec, n) == system or system in spec.chain(_system_of(spec, n)))}
    out: dict = {"system": system, "seconds": round(time.time() - began, 1), "stocks": {}, "flows": {}, "auxiliaries": {},
                 "goals": {}, "blocks": {}, "items": {}, "sensor_failures": [], "refused": []}

    def series(s):
        try:
            return [v for _, v in p.measurements.range(s.series, began - 1, time.time() + 1)]
        except Exception:
            return []
    for kind, table in (("stocks", spec.stocks), ("flows", spec.flows), ("auxiliaries", spec.auxiliaries)):
        for n, x in table.items():
            if n not in members:
                continue
            got = {}
            for sn, s in x.sensors.items():
                vals = series(s)
                if vals:
                    got[sn] = {"readings": len(vals), "first": vals[0], "last": vals[-1], "max": max(vals)}
            moved = sum(float((e.get("data") or {}).get("amount") or 0) for e in ev.query(n=None, type="valve.opened")
                        if (e.get("data") or {}).get("flow") == n and e["time"] >= began) if kind == "flows" else None
            out[kind][n] = {"sensors": got, **({"moved_by_blocks": moved} if moved else {})}
    for g in spec.goals:
        if g not in members:
            continue
        crossings = [e["type"].split(".", 1)[1] for e in ev.query(n=None, item=g, type="loop.*") if e["time"] >= began]
        out["goals"][g] = {"hold": str(spec.goals[g].hold), "crossings": crossings, "last": crossings[-1] if crossings else "never off"}
    for b in spec.blocks:
        if b not in members:
            continue
        runs = [e for e in ev.query(n=None, item=b) if e["time"] >= began and e["type"] in ("agent.ran", "agent.failed", "person.asked")]
        info = {"type": spec.blocks[b].type, "runs": sum(1 for e in runs if e["type"] == "agent.ran"),
                "failed": [(e.get("data") or {}).get("note") for e in runs if e["type"] == "agent.failed"][:3],
                "asked_a_person": sum(1 for e in runs if e["type"] == "person.asked"),
                "moved": {}}
        for e in runs:
            for f, v in ((e.get("data") or {}).get("moved") or {}).items():
                info["moved"][f] = info["moved"].get(f, 0) + v
        log = p.dir / "logs" / f"{b}.log"
        if log.is_file():
            tail = [x for x in log.read_text(errors="replace").splitlines() if x.strip() and not x.startswith("---")]
            if tail:
                info["log_tail"] = tail[-6:]
        out["blocks"][b] = info
    for e in ev.query(n=None, type="sensor.*"):
        if e["time"] >= began and e["type"] in ("sensor.failed", "sensor.refused"):
            name = str(e.get("item") or "")
            if name.split(".", 1)[0] in members:
                out["sensor_failures" if e["type"] == "sensor.failed" else "refused"].append(
                    {"sensor": name, "why": (e.get("data") or {}).get("why")})
    from ..spec import items as its
    for k, kind in spec.items.items():
        if k.startswith("ergostat.") or (kind.system and kind.system != system and system not in spec.chain(kind.system)):
            continue
        got = its.project(ev, spec, k)
        if got:
            by: dict = {}
            for i in got:
                by[i.state or "-"] = by.get(i.state or "-", 0) + 1
            out["items"][k] = {"by_state": by, "example": {"id": got[0].id, "state": got[0].state,
                                                           "fields": {f: v for f, v in list(got[0].fields.items())[:6]}}}
    out["sensor_failures"] = out["sensor_failures"][:8]
    out["refused"] = out["refused"][:8]
    return out


def _system_of(spec, name: str) -> str | None:
    for table in (spec.stocks, spec.flows, spec.auxiliaries, spec.goals, spec.blocks):
        if name in table:
            return getattr(table[name], "system", None)
    return None


def main(argv: list[str]) -> int:
    """The trial, and on its way out (done, failed, or stopped with SIGTERM) everything it started stopped: the
    engine's runs, and whatever they started (a Claude session), wherever they put themselves."""
    import os
    import signal

    from .reap import Watch, stop

    def stopped(*_):
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, stopped)
    watch = Watch(os.getpid())                   # what the runs start is known while they live, so none escapes
    try:
        return trial(argv, watch)
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        from .. import runner
        stop(os.getpid(), also=watch.close())
        runner.kill_all()


def trial(argv: list[str], watch=None) -> int:
    scratch, seconds, system = Path(argv[0]), float(argv[1]), argv[2]
    from .. import model as mdl
    from ..spec.engine import Engine
    from ..store import Project
    p = Project(mdl.load(scratch))
    spec = p.model.spec
    said: list[str] = []
    e = Engine(p, say=said.append)
    began = time.time()
    e.start_all()
    try:
        time.sleep(seconds)
    finally:
        if watch is not None:
            watch.look()                         # before the engine kills its runs, and orphans what they started
        e.close()
    if "--blocks" in argv:                       # each block of the system run once more, at once, as --now does
        for b in spec.blocks.values():
            if (b.system == system or (b.system and system in spec.chain(b.system))) and b.type in ("program", "ai"):
                e.run_block(b, "now")
    got = summarise(p, spec, system, began)
    got["engine_said"] = [x for x in said if any(n in x for n in (system,))][:12]
    print(json.dumps(got, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
