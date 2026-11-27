"""scripts/demo_check.py's check that an item folds as it did before changesets (``items_as_before``): it compares an
item's fold with its events' data at the same moment. The page folds an item as it stood at the engine's latest
snapshot (``/api/items/ID`` folds up to ``until=snap["at"]``), while ``/api/events`` reads the record up to now, so a
workspace event written after the snapshot (an acquire, a hold) made the check flake on a running demo."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent


def demo_check():
    spec = importlib.util.spec_from_file_location("demo_check_under_test", ROOT / "scripts" / "demo_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ITEM = "ergostat.workspace/code-3"
ACQUIRED = {"pool": "code", "slot": 3, "dir": "/w/code/3", "item": "ticket/SCRUM-1", "branch": "b", "how": "fresh",
            "run": "r1", "lease": 1, "acquired": 10.0}
HELD = {"pool": "code", "slot": 3, "dir": "/w/code/3", "item": "ticket/SCRUM-1", "branch": "b", "run": "r1", "lease": 1,
        "why": "its lease ended"}


def page(record: list[dict], snap_at: float, fields: dict | None = None):
    """A fake of the page's two endpoints: the item folded up to the snapshot, the record up to now."""
    def get(url: str):
        if "/api/events?" in url:
            return [e for e in record if unquote(url.split("item=")[1].split("&")[0]) == e["item"]]
        if url.endswith("/api/items"):
            return {"items": [{"id": ITEM, "projection": "ergostat.workspace"}]}
        upto = [e for e in record if e["time"] <= snap_at]
        got: dict = {}
        for e in upto:
            got.update(e["data"])
        return {"fields": fields if fields is not None else got, "last": max(e["time"] for e in upto),
                "events": len(upto), "refused": []}
    return get


def record() -> list[dict]:
    return [{"id": "a", "seq": 1, "time": 10.0, "type": "ergostat.workspace.acquired", "item": ITEM, "data": ACQUIRED},
            {"id": "h", "seq": 2, "time": 20.0, "type": "ergostat.workspace.held", "item": ITEM, "data": HELD}]


def test_an_event_after_the_snapshot_is_not_a_difference(monkeypatch):
    """The page's snapshot was taken at 15: the hold at 20 is in the record but not yet in the page's fold. Both sides
    are read as of the fold, so the item folds as before."""
    dc = demo_check()
    monkeypatch.setattr(dc, "get", page(record(), snap_at=15.0))
    assert dc.items_as_before("http://x", None) == []


def test_a_real_difference_is_still_found_and_named_by_its_first_key(monkeypatch):
    dc = demo_check()
    wrong = {**ACQUIRED, **HELD, "branch": "other"}
    monkeypatch.setattr(dc, "get", page(record(), snap_at=25.0, fields=wrong))
    got = dc.items_as_before("http://x", None)
    assert len(got) == 1
    assert got[0].startswith(f"item {ITEM}: folds differently than before: branch: now \"other\", before \"b\"")


def autoscaler(tmp_path, seconds: int = 2400):
    """examples/autoscaler copied, with the record its sensors would have read over ``seconds``: its own cluster.py run
    a second a tick, read every 5 s as the model's sensors read it (replicas, utilisation, load)."""
    import shutil
    import time

    from ergostat import model as mdl
    from ergostat.store import Project
    shutil.copytree(ROOT / "examples" / "autoscaler", tmp_path / "demo")
    spec = importlib.util.spec_from_file_location("autoscaler_cluster", tmp_path / "demo" / "cluster.py")
    cl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cl)
    now = time.time()
    s, rows = cl.fresh(now - seconds), []
    while s["t"] < now - 1:
        cl.tick(s, s["t"] + 1)
        if int(s["t"]) % 5 == 0:
            rows += [("sensor/replicas.main", s["t"], float(s["replicas"])), ("sensor/utilisation.main", s["t"], s["util"]),
                     ("sensor/load.main", s["t"], s["load"])]
    p = Project(mdl.load(tmp_path / "demo"))
    p.measurements.add_many(rows)
    return p, s


def test_the_autoscaler_demo_draws_identifies_and_lists_its_external_controller(tmp_path):
    """examples/autoscaler, after forty minutes of its record (definition of done 1-3): Blocks draws the HPA as an
    external controller in its loop, r and y into it and u (replicas) out, its law identified; /api/loop-control gives
    that law with its fit and judges the loop; the Agents page lists it as not run here, with no runs of its own."""
    import time

    from ergostat.numbers import extlaw as el
    from ergostat.web.server import Live, api
    p, s = autoscaler(tmp_path)
    assert len(s["events"]) >= 10                       # it scaled, often: the record has moves to identify it from
    live = Live(p)
    for _ in range(300):                                 # the law is fitted in a thread, drawn on a later poll
        g = api(live, "graph", {"view": ["blocks"]})
        n = next(x for x in g["nodes"] if x["id"] == "blk:web-hpa")
        if n.get("identified"):
            break
        time.sleep(0.1)
    assert n["role"] == "controller" and n["identified"] and n["fn"]["kind"].startswith("identified ")
    assert ["block", "web-hpa (external, on kubernetes)"] in n["rows"] and "external controller" in n["says"]
    into = {e["signal"]["sym"]: e for e in g["edges"] if e["target"] == "blk:web-hpa"}
    out = [e for e in g["edges"] if e["source"] == "blk:web-hpa"]
    assert into["r"]["source"] == "ref:cpu-at-target" and into["y"]["source"] == "sen:auxiliary.utilisation"
    assert [(e["signal"]["sym"], e["key"]) for e in out] == [("u", "stock.replicas")]

    lc = api(live, "loop-control", {"goal": ["cpu-at-target"]})
    assert (lc["y"], lc["u"], lc["how"]) == ("auxiliary.utilisation", "stock.replicas", "setting")
    c = lc["controller"]
    assert c["block"] == "web-hpa" and c["identified"]["family"] in el.FAMILIES
    assert c["identified"]["skill"] is not None and c["identified"]["r2"] is not None and c["identified"]["points"] >= 40
    assert c["says"].startswith("web-hpa is external: its law identified from the record") and "R²" in c["says"]
    assert "oscillation" in lc["performance"] and "constraint" in lc["performance"]     # the loop judged

    a = api(live, "agents", {})["web-hpa"]               # the page writes "not run here" and no count of runs
    assert a["runs_itself"] is False and a["runs"] == 0 and a["last"] is None and a["kind"] != "person"
    assert {"kind": "controller", "name": "cpu-at-target"} in a["roles"]
    spec = p.model.spec
    assert spec.blocks["web-hpa"].type == "external" and spec.agents["kubernetes"].external
    assert p.events.query(n=None, item="web-hpa", type="agent.*") == []


def test_the_autoscaler_with_too_little_record_says_why_its_law_is_not_identified(tmp_path):
    from ergostat.web.server import Live, api
    p, _ = autoscaler(tmp_path, seconds=120)
    c = api(Live(p), "loop-control", {"goal": ["cpu-at-target"]})["controller"]
    assert c["identified"] is None and c["says"].startswith("web-hpa is external: its law is not identified: ")
    assert "at least 40" in c["says"]


def test_the_autoscaler_demo_checks_and_its_readme_walks_through_it(tmp_path):
    import json
    import os
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")} | {"ERGOSTAT_HOME": str(tmp_path / "h")}
    r = subprocess.run([sys.executable, "-m", "ergostat", "check", "--json"], cwd=ROOT / "examples" / "autoscaler", env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
    got = json.JSONDecoder().raw_decode(r.stdout[r.stdout.index("{"):])[0]
    assert r.returncode == 0 and got["ok"] and got["errors"] == 0, r.stdout[-3000:]
    readme = (ROOT / "examples" / "autoscaler" / "README.md").read_text()
    for said in ("Blocks", "loop-control", "Agents", "not run here", "What ergostat adds"):
        assert said in readme, said


def test_first_diff_names_a_missing_key_and_counts_the_rest():
    dc = demo_check()
    assert dc.first_diff({"a": 1, "b": 2}, {"a": 1}) == "b: now 2, before missing"
    assert dc.first_diff({"a": 1, "c": 3}, {"a": 2, "b": 2}) == "a: now 1, before 2 (and 2 more keys)"
    assert dc.first_diff({"a": 1}, {"a": 1}) == "no key differs"
