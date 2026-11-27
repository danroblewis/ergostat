"""Trying a projection before it is written (SPEC §5a, *Trying a projection*; spec/trying.py): the report on a small
stream (matched by handler, not read, no key, unchanged, refused, items, fields, states, duplicates, expected), an
item's trace, the draft's items served to the page's panels, the stream's shape, the CLI's and the MCP tools' output,
and Save writing the definition into the model."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat.numbers import display
from ergostat.spec import trying
from ergostat.store import Project
from tests.test_dashboards import MODEL, write

GADGET = """\
query: type.startswith('gadget.')
key: gid
fields:
  gid: text
  state:
    values: [made, sold]
  colour: {}
  price: {}
events:
  gadget-made:
    when: type == 'gadget.made'
    gid: data.gid
    state: set('made')
    colour: data.colour
    price: data.price
  gadget-sold:
    when: type == 'gadget.sold'
    gid: data.gid
    state: set('sold')
  gadget-repriced:
    when: type == 'gadget.repriced'
    gid: data.gid
    price: add(data.by)
  other:
    when: true
    gid: data.gid
"""


def stream(p) -> None:
    t = time.time() - 600
    for i in range(5):
        p.events.add("gadget.made", data={"gid": f"g{i}", "colour": "red" if i % 2 else "blue", "price": 10 + i}, at=t + i)
    p.events.add("gadget.made", data={"colour": "green"}, at=t + 10)                     # no key
    p.events.add("gadget.sold", data={"gid": "g0"}, at=t + 20)
    p.events.add("gadget.sold", data={"gid": "g0"}, at=t + 21)                           # twice: changes nothing
    p.events.add("gadget.repriced", data={"gid": "g1", "by": "lots"}, at=t + 30)         # refused: add needs numbers
    p.events.add("gadget.polished", data={"gid": "g2"}, at=t + 40)                       # no handler: ignored
    p.events.add("widget.made", data={"wid": "w1"}, at=t + 50)                           # not read


def project(tmp_path) -> Project:
    p = Project(mdl.load(write(tmp_path, MODEL)))
    stream(p)
    return p


def test_the_report_on_a_small_stream(tmp_path):
    p = project(tmp_path)
    r = trying.run(p, "gadget", GADGET, expected={"g0": {"state": "sold", "colour": "blue", "price": 10},
                                                  "g1": {"state": "made", "price": 12}, "g9": {"state": "made"}})
    assert r["ok"] and r["projection"] == "gadget"
    assert r["matched"]["count"] == 9 and r["matched"]["by_handler"] == {
        "gadget-made": 5, "gadget-sold": 2, "gadget-repriced": 1, "other": 1}
    assert r["unmatched"]["no_key"]["count"] == 1 and r["unmatched"]["no_key"]["groups"][0]["shape"] == {"type": "gadget.made"}
    nr = r["unmatched"]["not_read"]
    assert nr["count"] >= 1 and any(g["shape"]["type"] == "widget.made" for g in nr["groups"])
    unchanged = {g["shape"]["type"]: g["count"] for g in r["unchanged"]["groups"]}
    assert unchanged == {"gadget.sold": 1, "gadget.polished": 1}
    assert r["refused"]["count"] == 1 and "add needs numbers" in r["refused"]["groups"][0]["why"]
    assert r["items"]["count"] == 5 and r["items"]["key"] == ["gid"]
    assert r["states"] == {"made": 4, "sold": 1}
    f = {x["field"]: x for x in r["fields"]}
    assert f["colour"]["pct"] == 100.0 and dict(map(tuple, f["colour"]["top"])) == {"blue": 3, "red": 2}
    assert (f["price"]["min"], f["price"]["max"]) == (10, 14)
    assert "repeat an earlier one's type and data" in r["duplicates"]["says"]
    x = r["expected"]
    assert x["items"] == {"expected": 3, "found": 2, "missing": 1, "missing_sample": ["g9"], "extra": 3,
                          "extra_sample": ["g2", "g3", "g4"]}
    price = next(s for s in x["fields"] if s["field"] == "price")
    assert price["match"] == 1 and price["mismatch"] == 1 and price["causes"] == {"fewer": 1}
    assert len(json.dumps(r)) < 12_000                                                  # small by design
    text = trying.text_of(r)
    assert "matched" in text and "refused" in text and "expected   2/3 items found" in text


def test_an_item_s_trace_and_the_refused_events(tmp_path):
    p = project(tmp_path)
    r = trying.run(p, "gadget", GADGET, item="g1", refused="add needs", keep=False)
    t = r["trace"]
    assert t["found"] and t["state"] == "made" and [s["handler"] for s in t["steps"]] == ["gadget-made", "gadget-repriced"]
    assert {c["field"] for c in t["steps"][0]["changes"]} == {"gid", "colour", "price"} and t["steps"][0]["move"] == "None -> made"
    assert "add needs numbers" in t["steps"][1]["refused"]
    assert r["refused_events"]["count"] == 1 and r["refused_events"]["events"][0]["item"] == "g1"
    assert "draft" not in r


def test_check_errors_are_returned_with_their_line_and_nothing_is_folded(tmp_path):
    p = project(tmp_path)
    r = trying.run(p, "gadget", GADGET.replace("state: set('sold')", "state: set('gone')"))
    assert not r["ok"] and "events" not in r
    e = r["errors"][0]
    assert "'gone' is not one of its values" in e["message"] and e["line"] == 19
    bad = trying.run(p, "gadget", "match: {type: [\n")
    assert not bad["ok"] and "does not read" in bad["errors"][0]["message"]
    assert trying.run(p, "gadget", "price: add(\n")["ok"] is False
    assert p.model.path.read_text() == MODEL                                            # nothing written


def test_events_given_and_an_existing_projection_tried_in_place(tmp_path):
    p = project(tmp_path)
    evs = [{"event": "ticket.opened", "item": "ticket/a", "data": {"title": "x"}},
           {"event": "ticket.started", "item": "ticket/a"}, {"event": "ticket.done", "item": "ticket/a"}]
    body = trying.definition_text(p.model.spec, "ticket")
    assert body.startswith("query:") and "'...': data" in body
    r = trying.run(p, "ticket", body, events=evs, keep=False)
    assert r["events"]["source"] == "given" and r["items"]["count"] == 1 and r["states"] == {"done": 1}


def test_the_draft_serves_the_page_s_panels(tmp_path):
    from ergostat.web.server import Live, _answer
    p = project(tmp_path)
    r = trying.run(p, "gadget", GADGET)
    live = Live(p)
    got = _answer(live, "items", {"projection": ["gadget"], "draft": [r["draft"]], "shown": ["1"]})
    assert {i["id"] for i in got["items"]} >= {"g1", "g2", "g3", "g4"}
    assert next(k for k in got["projections"] if k["name"] == "gadget")["counts"] == {"made": 4, "sold": 1}
    fp = _answer(live, "projections/gadget", {"draft": [r["draft"]]})
    assert fp["now"] == {"made": 4, "sold": 1}
    flow = _answer(live, "items-flow", {"projection": ["gadget"], "draft": [r["draft"]]})
    assert flow["projection"] == "gadget"
    assert _answer(live, "projections/gadget", {}) is None                              # the model has none
    assert not (p.dir / "items").exists() or not any("gadget" in f.name for f in (p.dir / "items").iterdir())


def test_the_stream_s_shape(tmp_path):
    p = project(tmp_path)
    s = trying.stream_shape(p, "gadget.*")
    paths = {x["path"]: x for x in s["paths"]}
    assert s["events"] == 10 and paths["data.gid"]["pct"] == 90.0
    assert paths["data.colour"]["distinct"] == 3 and set(paths["data.colour"]["examples"]) == {"blue", "red", "green"}
    assert paths["data.price"]["types"] == {"number": 5}
    assert "data.colour" in trying.shape_text(s)


def test_save_writes_the_definition_and_keeps_its_dashboards(tmp_path):
    p = project(tmp_path)
    x = display.save_projection(p, {"name": "gadget", "yaml": GADGET, "new": True}, {"at": time.time(), "window": 3600})
    assert x["status"] == "accepted" and x["projection"] == "gadget" and x["kind"] != "display"
    p2 = Project(mdl.load(tmp_path))
    assert p2.model.spec.items["gadget"].states == ["made", "sold"]
    assert "  gadget:\n    # updated " in p2.model.path.read_text() and "    query: type.startswith('gadget.')\n" in \
        p2.model.path.read_text()
    display.save(p2, {"projection": "gadget", "role": "list", "panels": [{"panel": "item-list", "projection": "$projection"}]},
                 {"at": time.time(), "window": 3600})
    p3 = Project(mdl.load(tmp_path))
    body = trying.definition_text(p3.model.spec, "gadget")
    assert "dashboards" not in body and "gadget.repriced" in body
    display.save_projection(p3, {"name": "gadget", "yaml": body.replace("[made, sold]", "[made, sold, scrapped]")},
                            {"at": time.time(), "window": 3600})
    p4 = Project(mdl.load(tmp_path))
    assert p4.model.spec.items["gadget"].states == ["made", "sold", "scrapped"] and "gadget.list" in p4.model.spec.dashboards
    import pytest

    from ergostat.numbers import proposals as pr
    with pytest.raises(pr.ProposalError, match="does not pass check"):
        display.save_projection(p4, {"name": "gadget", "yaml": "states: [Bad]\n"}, {"at": time.time(), "window": 3600})


def test_the_cli_and_the_mcp_tools(tmp_path):
    project(tmp_path)
    f = tmp_path / "gadget.yaml"
    f.write_text("projections:\n  gadget:\n" + "".join(f"    {x}\n" for x in GADGET.splitlines()))
    run = lambda *a: subprocess.run([sys.executable, "-m", "ergostat", *a, "-C", str(tmp_path)],   # noqa: E731
                                    capture_output=True, text=True)
    got = run("projection", "try", str(f))
    assert got.returncode == 0, got.stderr
    assert got.stdout.startswith("projection gadget:") and "matched           9" in got.stdout
    js = json.loads(run("projection", "try", str(f), "--item", "g0", "--json").stdout)
    assert js["trace"]["state"] == "sold"
    sh = run("events", "shape", "--type", "gadget.*")
    assert "data.gid" in sh.stdout and sh.returncode == 0
    from ergostat.mcp import TOOLS, Server
    assert {"projection_try", "events_shape"} <= {t["name"] for t in TOOLS}
    srv = Server(Path(tmp_path))
    out = json.loads(srv.call("projection_try", {"name": "gadget", "yaml": GADGET})["content"][0]["text"])
    assert out["matched"]["count"] == 9 and "draft" not in out
    sh = json.loads(srv.call("events_shape", {"type": "gadget.*"})["content"][0]["text"])
    assert sh["events"] == 10


EC2 = """\
query: type == 'aws.eventbridge' and data.source == 'aws.ec2'
key: [account, region, instance_id]
fields:
  state:
    values: [pending, running, stopping, stopped, shutting-down, terminated]
  account: {}
  region: {}
  instance_id: {}
events:
  aws-eventbridge:
    when: type == 'aws.eventbridge'
    state: "data.detail.state if data['detail-type'] == 'EC2 Instance State-change Notification' else current"
    account: data.account
    region: data.region
    instance_id: data.detail['instance-id']
  other:
    when: true
"""


def test_the_ec2_stream(tmp_path):
    here = Path(__file__).parent / "fixtures" / "ec2_stream.py"
    subprocess.run([sys.executable, "-I", str(here), "batch", "--instances", "8", "--days", "1",
                    "--events", str(tmp_path / "events.jsonl"), "--expected", str(tmp_path / "expected.json")],
                   check=True, capture_output=True)
    p = Project(mdl.load(write(tmp_path, MODEL)))
    evs = [json.loads(x) for x in (tmp_path / "events.jsonl").read_text().splitlines()]
    exp = json.loads((tmp_path / "expected.json").read_text())
    r = trying.run(p, "ec2", EC2, events=evs, expected=exp, keep=False)
    assert r["ok"] and r["items"]["count"] == len(exp) and r["expected"]["items"]["found"] == len(exp)
    nk = r["unmatched"]["no_key"]
    assert nk["count"] > 0 and all("detail.eventName" in g["shape"] for g in nk["groups"])   # the CloudTrail calls, by name
    assert "data.id too" in r["duplicates"]["says"]
    state = next(s for s in r["expected"]["fields"] if s["field"] == "state")
    assert state["match"] > state["mismatch"]
    assert len(json.dumps(r)) < 12_000
