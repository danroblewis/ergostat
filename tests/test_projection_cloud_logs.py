"""What three agents modelling AWS, GCP and Azure activity logs asked of the workbench's tools (SPEC §5a): the whole
record by default and a window said when it leaves events out; kinds split by the operation, not a caller's IP or a
result, and paged; the shape's every path, under a prefix, with more examples; int/float/str/json/lower/upper; a
projection's defaults: for every kind; the review's values whole, objects listed by state or an expression, the
timeline in event-time order with the late ones marked; unset by event time; names with _, states in any case, a
when:'s paths read, and no verb-past note for an outside log's kinds."""

from __future__ import annotations

import json
import random
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat.spec import trying, workbench
from ergostat.store import Project

DAY = 86400.0


def project(tmp_path, body: str = "name: logs\n") -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(body))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [x.message for x in m.problems]
    return Project(m)


def problems(tmp_path, body: str):
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(body))
    _, ps = read(tmp_path / "ergostat.yaml", extremes=False)
    return ps


OPS = ["RunInstances", "StopInstances", "StartInstances", "TerminateInstances", "CreateTags", "DescribeInstances",
       "ModifyInstanceAttribute", "RebootInstances", "CreateVolume", "AttachVolume", "DeleteVolume", "CreateSnapshot",
       "PutObject", "GetObject", "DeleteObject", "AssumeRole", "CreateUser", "DeleteUser", "ListBuckets", "GetCallerIdentity",
       "CreateRole", "AttachRolePolicy", "UpdateFunctionCode", "Invoke", "CreateLogGroup"]


def cloudtrail(p, n: int = 1500, ago: float = 3 * DAY) -> None:
    """CloudTrail-like records, days old: 25 operations, four caller IPs, a result each (every op shaped alike)."""
    rng = random.Random(1)
    t = time.time() - ago
    evs = []
    for i in range(n):
        op = OPS[i % len(OPS)]
        evs.append({"type": "aws.cloudtrail", "at": t + i, "data": {
            "eventName": op, "eventSource": "ec2.amazonaws.com", "sourceIPAddress": f"10.0.0.{rng.randint(1, 4)}",
            "errorCode": rng.choice(["", "AccessDenied"]), "eventTime": t + i, "awsRegion": "us-east-1",
            "requestParameters": {"instanceId": f"i-{i % 40:04d}"}}})
    p.events.add_many(evs)


def azure(p, n: int = 600) -> None:
    t = time.time() - 2 * DAY
    ops = ["Microsoft.Compute/virtualMachines/write", "Microsoft.Compute/virtualMachines/delete",
           "Microsoft.Compute/virtualMachines/start/action", "Microsoft.Compute/virtualMachines/deallocate/action",
           "Microsoft.Storage/storageAccounts/write", "Microsoft.Network/networkInterfaces/write"]
    p.events.add_many([{"type": "azure.activity", "at": t + i, "data": {
        "operationName": {"value": ops[i % len(ops)], "localizedValue": ops[i % len(ops)].split("/")[-1]},
        "resultType": ["Start", "Success", "Failure"][i % 3], "callerIpAddress": f"52.1.1.{i % 3}",
        "resourceId": f"/subscriptions/s/vm{i % 30}", "status": {"value": ["Started", "Succeeded"][i % 2]},
        "properties": {"responseBody": json.dumps({"id": f"vm{i % 30}", "sku": "Standard_B2s"})}}}
        for i in range(n)])


def gcp(p, n: int = 400) -> None:
    t = time.time() - DAY
    ops = ["v1.compute.instances.insert", "v1.compute.instances.delete", "v1.compute.instances.start",
           "v1.compute.instances.stop", "storage.buckets.create"]
    p.events.add_many([{"type": "gcp.audit", "at": t + i, "data": {"protoPayload": {
        "methodName": ops[i % len(ops)], "requestMetadata": {"callerIp": f"34.0.0.{i % 2}"},
        "resourceName": f"projects/p/zones/z/instances/vm-{i % 20}"}, "severity": ["NOTICE", "ERROR"][i % 2],
        "timestamp": t + i}} for i in range(n)])


# ---- 1: the whole record by default; a window that leaves events out says so

VM = """\
query: type == 'aws.cloudtrail'
key: instance
fields:
  instance: text
  op: text
events:
  call:
    when: true
    instance: data.requestParameters.instanceId
    op: data.eventName
"""


def test_try_and_review_read_the_whole_record_and_say_a_window(tmp_path):
    p = project(tmp_path)
    cloudtrail(p, 300)
    r = workbench.review(p, {"name": "vm", "yaml": VM})
    assert r["read"]["events"] == 300 and "window" not in r["read"]
    t = trying.run(p, "vm", VM, keep=False)
    assert t["events"]["read"] == 300 and "window" not in t["events"]
    r = workbench.review(p, {"name": "vm", "yaml": VM, "since": time.time() - 3600})
    w = r["read"]["window"]
    assert r["read"]["events"] == 0 and w["of"] == 300 and w["left_out"] == 300
    assert w["says"].startswith("read 0 of 300 events: since 1h ago; the record spans")
    t = trying.run(p, "vm", VM, since=time.time() - 3600, keep=False)
    assert t["events"]["window"]["of"] == 300 and "window" in trying.text_of(t)
    from ergostat.eventquery import run
    q = run(p.events, {"query": "type == 'aws.cloudtrail'", "since": time.time() - 3600})
    assert q["total"] == 0 and q["window"]["of"] == 300


# ---- 2: kinds split by the operation, and paged

def test_kinds_split_by_the_operation_not_an_ip_or_a_result(tmp_path):
    p = project(tmp_path)
    cloudtrail(p)
    azure(p)
    gcp(p)
    k = workbench.suggest(p, {"query": "type == 'aws.cloudtrail'", "all": True})
    assert k["kinds_total"] == len(OPS) and all("data.eventName ==" in x["when"] for x in k["kinds"])
    assert not any("sourceIPAddress" in x["when"] or "errorCode" in x["when"] for x in k["kinds"])
    a = workbench.suggest(p, {"query": "type == 'azure.activity'", "all": True})
    assert a["kinds"] and all("data.operationName.value ==" in x["when"] for x in a["kinds"]), [x["when"] for x in a["kinds"]]
    assert not any("resultType" in x["when"] or "callerIpAddress" in x["when"] for x in a["kinds"])
    g = workbench.suggest(p, {"query": "type == 'gcp.audit'", "all": True})
    assert len(g["kinds"]) == 5 and all("data.protoPayload.methodName ==" in x["when"] for x in g["kinds"])
    assert not any("severity" in x["when"] for x in g["kinds"])


def test_kinds_are_paged(tmp_path):
    p = project(tmp_path)
    cloudtrail(p, 500)
    first = workbench.suggest(p, {"query": "type == 'aws.cloudtrail'"})
    assert len(first["kinds"]) == 10 and first["kinds_left"] == len(OPS) - 10 and first["kinds_total"] == len(OPS)
    nxt = workbench.suggest(p, {"query": "type == 'aws.cloudtrail'", "offset": 10, "limit": 10})
    assert len(nxt["kinds"]) == 10 and nxt["offset"] == 10
    assert not {x["when"] for x in first["kinds"]} & {x["when"] for x in nxt["kinds"]}
    last = workbench.suggest(p, {"query": "type == 'aws.cloudtrail'", "offset": 20})
    assert len(last["kinds"]) == len(OPS) - 20 and "kinds_left" not in last
    from ergostat.cli.trying import kinds_text
    assert "--offset 10" in kinds_text(first) and "kinds 1-10 of 25" in kinds_text(first)


# ---- 3: the shape, whole

def test_the_shape_whole_under_a_prefix_with_more_examples(tmp_path):
    p = project(tmp_path)
    p.events.add_many([{"type": "wide", "data": {f"k{j}": {"v": j, "w": f"x{i}"} for j in range(60)}}
                       for i in range(10)])
    sh = trying.stream_shape(p, "wide")
    assert len(sh["paths"]) == 80 and sh["paths_left"] == sh["paths_total"] - 80
    assert "--all" in trying.shape_text(sh)
    every = trying.stream_shape(p, "wide", most=None)
    assert len(every["paths"]) == every["paths_total"] and "paths_left" not in every
    pre = trying.stream_shape(p, "wide", prefix="data.k3", examples=8)
    assert {x["path"] for x in pre["paths"]} == {"data.k3", "data.k3.v", "data.k3.w"}
    assert len(next(x for x in pre["paths"] if x["path"] == "data.k3.w")["examples"]) == 8


# ---- 4: the expressions' conversions

def test_conversions_are_null_safe():
    from ergostat.spec.handlers import BadExpr, compile_value, evaluate
    env = {"data": {"n": "42", "f": "2.5", "j": '{"sku": "B2s", "tags": {"env": "prod"}}', "s": "Running", "x": 7,
                    "bad": "{nope"}}
    got = {t: evaluate(compile_value(t), env) for t in (
        "int(data.n)", "float(data.f)", "str(data.x)", "json(data.j).sku", "json(data.j)['tags'].env", "lower(data.s)",
        "upper(data.s)", "data.s.lower()", "int(data.missing)", "json(data.bad)", "float('x')", "data.x.lower()",
        "str(data.missing)", "lower(data.x)", "int(data.x) + 1")}
    assert got == {"int(data.n)": 42, "float(data.f)": 2.5, "str(data.x)": "7", "json(data.j).sku": "B2s",
                   "json(data.j)['tags'].env": "prod", "lower(data.s)": "running", "upper(data.s)": "RUNNING",
                   "data.s.lower()": "running", "int(data.missing)": None, "json(data.bad)": None, "float('x')": None,
                   "data.x.lower()": None, "str(data.missing)": None, "lower(data.x)": None, "int(data.x) + 1": 8}
    import pytest
    with pytest.raises(BadExpr):
        compile_value("int(data.n, 2)")


# ---- 5: defaults for every kind

DEFAULTED = """\
projections:
  vm_instance:
    query: type == 'aws.cloudtrail'
    key: [region, instance]
    fields:
      region: text
      instance: text
      state: {values: [Running, Stopped, terminated]}
      last_op: text
    defaults:
      region: data.awsRegion
      instance: data.requestParameters.instanceId
      last_op: data.eventName
    events:
      run:
        when: data.eventName == 'RunInstances'
        state: "'Running'"
      stop:
        when: data.eventName == 'StopInstances'
        state: "'Stopped'"
        last_op: "'stopped by ' + data.sourceIPAddress"
      other:
        when: true
"""


def test_defaults_apply_to_every_kind_unless_it_gives_its_own(tmp_path):
    p = project(tmp_path, DEFAULTED)
    k = p.model.spec.items["vm_instance"]
    by = {x.name: x for x in k.kinds}
    assert all(x.key is not None and not x.untold for x in k.kinds)            # the key solved from the defaults
    assert by["stop"].fields["last_op"].text.startswith("'stopped by'") or "stopped by" in by["stop"].fields["last_op"].text
    assert by["run"].fields["last_op"].text == "data.eventName"
    assert not [x for x in p.model.problems if x.code == "key-not-told"]
    cloudtrail(p, 100)
    r = workbench.review(p, {"name": "vm_instance", "yaml": DEFAULTED})
    assert r["ok"] and r["objects"]["count"] == 40 and r["residual"]["no_key"]["count"] == 0
    assert "data.eventName" not in {x["path"] for x in r["unmapped"]["paths"]}


def test_a_default_s_error_is_said_once(tmp_path):
    bad = DEFAULTED.replace("      last_op: data.eventName\n", "      colour: data.c\n")
    ps = [x for x in problems(tmp_path, bad) if x.level == "error"]
    assert [x.code for x in ps] == ["undeclared-field"], [x.message for x in ps]
    ps = [x for x in problems(tmp_path, DEFAULTED.replace("    defaults:\n", "    defaults:\n      when: true\n"))
          if x.level == "error"]
    assert [x.code for x in ps] == ["bad-defaults"]


# ---- 6: the review's values whole, objects listed, the timeline in event-time order

LONG = """\
query: type == 'job'
key: id
time: data.t
fields:
  id: text
  state: {values: [Queued, Running, Done]}
  note: text
events:
  ev:
    when: true
    id: data.id
    state: data.s
    note: data.note
"""


def test_the_review_lists_objects_says_values_whole_and_marks_late_events(tmp_path):
    p = project(tmp_path)
    long_id = "arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef0-with-a-long-tail"
    t = time.time() - 100
    p.events.add_many([
        {"type": "job", "at": t + 1, "data": {"id": long_id, "s": "Queued", "t": t + 1}},
        {"type": "job", "at": t + 2, "data": {"id": long_id, "s": "Done", "t": t + 30}},
        {"type": "job", "at": t + 3, "data": {"id": long_id, "s": "Running", "t": t + 10}},     # late: before Done
        {"type": "job", "at": t + 4, "data": {"id": "j2", "s": "Running", "t": t + 4, "note": "x" * 90}},
        {"type": "job", "at": t + 5, "data": {"id": "j3", "s": "Queued", "t": t + 5}}])
    r = workbench.review(p, {"name": "job", "yaml": LONG, "item": long_id, "state": "Running,Queued"})
    assert r["listed"]["count"] == 2 and [o["key"] for o in r["listed"]["objects"]] == ["j2", "j3"]
    tl = r["timeline"]
    assert tl["state"] == "Done" and tl["order"] == "event time" and tl["late"] == 1
    assert [s["time"] for s in tl["steps"]] == sorted(s["time"] for s in tl["steps"])
    assert [bool(s.get("late")) for s in tl["steps"]] == [False, True, False]
    note = next(f for f in r["fields"] if f["field"] == "note")
    assert note["top"][0][0] == "x" * 90                                        # whole, not cut
    assert long_id in r["objects"]["keys"]
    cut = workbench.review(p, {"name": "job", "yaml": LONG, "width": 20})
    assert next(f for f in cut["fields"] if f["field"] == "note")["top"][0][0].endswith("...")
    w = workbench.review(p, {"name": "job", "yaml": LONG, "where": "state == 'Done' or fields.id == 'j2'"})
    assert {o["key"] for o in w["listed"]["objects"]} == {long_id, "j2"}
    from ergostat.cli.trying import review_text
    text = review_text(r)
    assert long_id in text and " LATE" in text and "listed            2" in text
    assert "x" * 90 in review_text(workbench.review(p, {"name": "job", "yaml": LONG}))


def test_the_cli_and_mcp_take_the_new_options(tmp_path):
    p = project(tmp_path)
    cloudtrail(p, 300)
    f = tmp_path / "vm.yaml"
    f.write_text(VM)
    run = lambda *a: subprocess.run([sys.executable, "-m", "ergostat", *a, "-C", str(tmp_path)],   # noqa: E731
                                    capture_output=True, text=True)
    got = run("projection", "review", str(f), "--where", "events > 1", "--list-limit", "3")
    assert got.returncode == 0, got.stderr
    assert "listed           40  objects where events > 1" in got.stdout and "... 37 more" in got.stdout, got.stdout
    got = run("projection", "review", str(f), "--since", "1h")
    assert "window     read 0 of 300 events" in got.stdout, got.stdout
    got = run("events", "kinds", "type == 'aws.cloudtrail'", "--offset", "20")
    assert got.returncode == 0 and "kinds 21-25 of 25" in got.stdout, got.stdout
    got = run("events", "shape", "--prefix", "data.requestParameters", "--examples", "2")
    assert "data.requestParameters.instanceId" in got.stdout and "data.eventName" not in got.stdout
    from ergostat.mcp import Server
    srv = Server(Path(tmp_path))
    k = json.loads(srv.call("events_kinds", {"query": "type == 'aws.cloudtrail'", "all": True})["content"][0]["text"])
    assert len(k["kinds"]) == len(OPS)
    sh = json.loads(srv.call("events_shape", {"prefix": "data.requestParameters"})["content"][0]["text"])
    assert {x["path"] for x in sh["paths"]} == {"data.requestParameters", "data.requestParameters.instanceId"}
    r = json.loads(srv.call("projection_review", {"name": "vm", "yaml": VM, "state": "x", "since": "1h"})
                   ["content"][0]["text"])
    assert r["listed"]["count"] == 0 and r["read"]["window"]["of"] == 300


# ---- 7: the smaller ones

def test_unset_respects_event_time(tmp_path):
    body = """\
    query: type == 'tag'
    key: id
    time: data.t
    fields:
      id: text
      owner: text
    events:
      set:
        when: data.op == 'set'
        id: data.id
        owner: data.owner
      clear:
        when: data.op == 'clear'
        id: data.id
        owner: unset()
    """
    p = project(tmp_path)
    t = time.time() - 100
    p.events.add_many([{"type": "tag", "at": t + 1, "data": {"id": "a", "op": "clear", "t": t + 20}},
                       {"type": "tag", "at": t + 2, "data": {"id": "a", "op": "set", "owner": "old", "t": t + 10}},
                       {"type": "tag", "at": t + 3, "data": {"id": "b", "op": "set", "owner": "x", "t": t + 1}},
                       {"type": "tag", "at": t + 4, "data": {"id": "b", "op": "clear", "t": t + 2}}])
    r = trying.run(p, "tag", textwrap.dedent(body), keep=False)
    assert r["ok"]
    from ergostat.spec.items import fold
    from ergostat.spec import trying as tr
    spec, _, errs = tr.compiled(p, "tag", textwrap.dedent(body), "")
    assert not errs
    k = spec.items["tag"]
    evs = p.events.query(n=None, type="tag")
    a = fold("a", [e for e in evs if e["data"]["id"] == "a"], k)
    b = fold("b", [e for e in evs if e["data"]["id"] == "b"], k)
    assert "owner" not in a.fields and "owner" not in b.fields                  # the late, older set does not return


def test_names_with_underscores_states_in_any_case_and_no_verb_past_note(tmp_path):
    ps = problems(tmp_path, """\
    projections:
      vm_instance:
        query: type == 'aws.cloudtrail'
        key: id
        fields:
          id: text
          state: {values: [RUNNING, Stopped, shutting-down]}
        events:
          run:
            when: data.eventName == 'RunInstances'
            id: data.id
            state: "'RUNNING'"
          stopped:
            when: data.eventName == 'StopInstances'
            id: data.id
            state: "'Stopped'"
    """)
    assert not [x for x in ps if x.level == "error"], [x.message for x in ps if x.level == "error"]
    assert not [x for x in ps if x.code == "event-names-mixed"]
    ps = problems(tmp_path, """\
    projections:
      thing:
        query: type == 'x'
        key: id
        fields:
          id: text
          state: {values: [Open]}
        events:
          a:
            when: true
            id: data.id
            state: "'open'"
    """)
    assert "unknown-state" in [x.code for x in ps]                              # compared exactly
