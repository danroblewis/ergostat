"""The Guide (``ergostat/guide.py``): every frame's tiny model compiles, is drawn by the real
renderers, and shows what its line says: the loops marked R or B where the storyboard puts them,
the signs on the links, the summing junction's signs, the loop open and then closed, the
disturbance, the cascade's inner block closed and opened; the equations it plots name only what
they define; and a snapshot carries the frames, so the Guide works offline."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from ergostat import guide
from ergostat.guide import FRAMES, frames

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def by_id():
    return {f["id"]: f for f in frames()["frames"]}


def views(f, kind):
    return [v["graph"] for v in f["views"] if v["view"] == kind]


def loop_labels(g) -> list[str]:
    return sorted(c["label"] for c in g.get("causalLoops", []))


def connectors(g) -> dict:
    return {(e["source"], e["target"]): e.get("polarity") for e in g["edges"] if e["kind"] == "connector"}


def test_every_frame_model_compiles_and_draws_something():
    for f in FRAMES:
        for v in f["views"]:
            m = guide._compile(v["model"])
            assert m.stocks, f["id"]
    got = frames()
    assert [f["id"] for f in got["frames"]][-1] == "yours"
    assert len(got["frames"]) == 13
    for f in got["frames"][:-1]:
        assert f["text"] and "\n" not in f["text"], f["id"]                    # one line each
        assert f["part"] in got["parts"], f["id"]
        for v in f["views"]:
            assert v["graph"]["nodes"], (f["id"], v["view"])


def test_the_why_frames_set_the_knob_beside_the_stock_then_both_views_of_what_is_between(by_id):
    (g,) = views(by_id["want"], "dynamics")
    assert sorted(n["kind"] for n in g["nodes"]) == ["auxiliary", "stock"] and not g["edges"]
    between = by_id["between"]
    assert [v["view"] for v in between["views"]] == ["dynamics", "blocks"]          # one model, two perspectives
    (sd,) = views(between, "dynamics")
    assert loop_labels(sd) == ["B1"]
    (bd,) = views(between, "blocks")
    assert any(n["kind"] == "sum" for n in bd["nodes"])


def test_the_system_dynamics_frames_mark_signs_then_b_then_r_and_b(by_id):
    assert all(not views(by_id[k], "blocks") for k in ("fills", "levels", "links", "balancing", "reinforcing"))
    (fills,) = views(by_id["fills"], "dynamics")
    assert {n["kind"] for n in fills["nodes"]} >= {"stock", "disturbance", "cloud"} and not loop_labels(fills)
    (links,) = views(by_id["links"], "dynamics")
    assert not loop_labels(links)                                              # the link first, its loop next
    assert connectors(links)[("stock:customers", "flow:churn")] == "+"
    (bal,) = views(by_id["balancing"], "dynamics")
    assert loop_labels(bal) == ["B1"]
    assert connectors(bal)[("stock:customers", "flow:churn")] == "+"
    (rein,) = views(by_id["reinforcing"], "dynamics")
    assert loop_labels(rein) == ["B1", "R1"]
    names = {c["label"]: c["name"] for c in rein["causalLoops"]}
    assert names == {"R1": "word-of-mouth", "B1": "churn"}
    assert connectors(rein)[("stock:customers", "flow:signups")] == "+"
    for k in ("fills", "levels", "links", "balancing", "reinforcing"):
        assert by_id[k]["plot"], k                                            # behaviour beside each, seen
        (g,) = views(by_id[k], "dynamics")
        assert all(n.get("bare") for n in g["nodes"]), k                       # no readings in a frame


def test_the_control_frames_build_the_loop_up(by_id):
    def ids(g):
        return {n["id"] for n in g["nodes"]}

    def wired(g, a, b):
        return any(e["source"] == a and e["target"] == b for e in g["edges"])

    (block,) = views(by_id["block"], "blocks")
    assert {n["role"] for n in block["nodes"]} == {"input", "process", "output"}
    assert next(n for n in block["nodes"] if n["role"] == "input")["fn"]["sym"] == "u"
    (ctl,) = views(by_id["controller"], "blocks")
    s = next(n for n in ctl["nodes"] if n["kind"] == "sum")
    assert [p["sign"] for p in s["ins"]] == ["+", "−"]                         # e = r − y
    assert "blk:marketing" in ids(ctl) and not wired(ctl, "proc:stock.customers", "sum:enough")
    assert next(n for n in ctl["nodes"] if n["role"] == "input")["fn"]["sym"] == "y"
    (closed,) = views(by_id["closed"], "blocks")
    assert wired(closed, "proc:stock.customers", "sen:stock.customers") and wired(closed, "sen:stock.customers", "sum:enough")
    (dist,) = views(by_id["disturbance"], "blocks")
    assert any(n["role"] == "disturbance" and n["fn"]["sym"] == "d" for n in dist["nodes"])
    (casc_view,) = by_id["cascade"]["views"]
    assert any(n["role"] == "subsystem" for n in casc_view["graph"]["nodes"]) and not casc_view["graph"]["frames"]
    assert {f["frame"] for f in casc_view["opened"]["frames"]} == {"system", "cascade"}
    for k in ("block", "controller", "closed", "disturbance", "cascade"):
        for g in [v["graph"] for v in by_id[k]["views"]] + [v["opened"] for v in by_id[k]["views"] if "opened" in v]:
            ports = {p["id"] for n in g["nodes"] for p in [*n["ins"], *n["outs"]]}
            for e in g["edges"]:
                assert e["sourcePort"] in ports and e["targetPort"] in ports, (k, e["id"])
    assert by_id["closed"]["plot"] and by_id["disturbance"]["plot"]["band"][2] == "d"


def test_every_plot_names_only_what_it_defines():
    for f in FRAMES:
        p = f.get("plot")
        if not p:
            continue
        for run in p["runs"]:
            known = set(run["stocks"]) | set(run["aux"]) | set(run["inputs"])
            for fl in run["flows"].values():
                assert {fl["from"], fl["to"]} - {None} <= set(run["stocks"]), f["id"]
                assert {v for _, vs in fl["terms"] for v in vs} <= known, f["id"]
            for terms in run["aux"].values():
                assert {v for _, vs in terms for v in vs} <= known, f["id"]
            assert {s["of"] for s in run["series"]} <= known, f["id"]


def test_the_page_and_a_snapshot_carry_the_frames(tmp_path, monkeypatch):
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web.server import Live, api
    from ergostat.web.snapshot import build
    d = tmp_path / "first-loop"
    shutil.copytree(ROOT / "examples" / "first-loop", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    monkeypatch.setenv("ERGOSTAT_HOME", tempfile.mkdtemp())
    project = Project(mdl.load(d))
    assert api(Live(project), "guide", {})["frames"][0]["id"] == "want"
    html = build(project)
    assert '"guide": {"parts"' in html and "pageGuide" in html


def test_each_section_is_one_run_of_frames_so_its_name_links_to_one_first_frame():
    """The section names in the Guide's step row (guide.js) link to their section's first frame, and the dots are
    named 'Step n of 13': that holds only while each section's frames sit together, in PARTS order."""
    got = frames()
    order = [f["part"] for f in got["frames"]]
    runs = [p for k, p in enumerate(order) if k == 0 or order[k - 1] != p]
    assert runs == list(got["parts"])                                   # each section once, in order, no gaps
    assert order.index("control") == 7 and got["parts"]["control"] == "Control: what we control"
