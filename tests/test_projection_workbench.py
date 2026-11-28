"""The projection workbench (SPEC §5a; docs/roadmap/projection-workbench.md), the server half: the syntax and its check
errors, the fold (types, folds, overrides, each(), event time, duplicates), Save's dated comments with the rest kept
byte for byte, the query engine (indexed and scanned answers equal; what a change adds and drops), and the workbench's
answers on the EC2 simulator's stream, an instance definition scored against the simulator's truth."""

from __future__ import annotations

import json
import re
import textwrap
import time
from datetime import datetime, timezone

import pytest

from ergostat import eventquery
from ergostat import model as mdl
from ergostat.spec import items as its
from ergostat.spec import workbench
from ergostat.store import Project
from tests.fixtures.ec2_stream import Fleet

T0 = 1_700_000_000.0

INSTANCE = """\
query: type == 'aws.eventbridge' and data.source == 'aws.ec2' and not data.detail.eventName.startswith('Describe')
key: [account, region, instance_id]
time: data.time
fields:
  state: {values: [pending, running, stopping, stopped, shutting-down, terminated]}
  account: text
  region: text
  instance_id: text
  type: {type: text, description: the instance type (the latest by event time)}
  image: text
  launched_by: {type: text, fold: first}
  launched_at: {type: time, fold: first}
  tags: {type: map, fold: merge}
  starts: {type: integer, fold: add}
  reboots: {type: integer, fold: add}
events:
  state-change:
    when: data['detail-type'] == 'EC2 Instance State-change Notification'
    state: data.detail.state
    account: data.account
    region: data.region
    instance_id: data.detail['instance-id']
  launch:
    when: data.detail.eventName == 'RunInstances'
    account: data.account
    region: data.region
    instance_id: "each(data.detail.responseElements.instancesSet.items, 'instanceId')"
    type: data.detail.requestParameters.instanceType
    image: data.detail.requestParameters.imageId
    launched_by: data.detail.userIdentity.arn.split('/')[-1]
    launched_at: data.time
    starts: 1
  start:
    when: data.detail.eventName == 'StartInstances'
    account: data.account
    region: data.region
    instance_id: "each(data.detail.requestParameters.instancesSet.items, 'instanceId')"
    starts: 1
  restart:
    when: data.detail.eventName == 'RebootInstances'
    account: data.account
    region: data.region
    instance_id: "each(data.detail.requestParameters.instancesSet.items, 'instanceId')"
    reboots: 1
  resize:
    when: data.detail.eventName == 'ModifyInstanceAttribute'
    account: data.account
    region: data.region
    instance_id: data.detail.requestParameters.instanceId
    type: data.detail.requestParameters.instanceType.value
  tagged:
    when: data.detail.eventName == 'CreateTags'
    account: data.account
    region: data.region
    instance_id: "each(data.detail.requestParameters.resourcesSet.items, 'resourceId')"
    tags: pairs(data.detail.requestParameters.tagSet.items, 'key', 'value')
  stop-or-end:
    when: data.detail.eventName in ['StopInstances', 'TerminateInstances']
    account: data.account
    region: data.region
    instance_id: "each(data.detail.requestParameters.instancesSet.items, 'instanceId')"
"""


def ec2(seed: int = 7, instances: int = 20, days: float = 3) -> tuple[list[dict], dict]:
    """The simulator's stream as delivered (late, a few twice) and its truth, batch mode."""
    start = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc).timestamp()
    f = Fleet(seed, instances, start)
    evs = f.advance(start + days * 86400)
    return f.deliver(evs, float("inf")), f.truth()


def recorded(p, delivered: list[dict]) -> None:
    t = T0
    p.events.add_many([{"type": "aws.eventbridge", "data": e, "at": (t := t + 1)} for e in delivered])


def project(tmp_path, body: str = "", extra: dict | None = None) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(body) or "name: wb\n")
    for n, t in (extra or {}).items():
        (tmp_path / n).write_text(textwrap.dedent(t))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [x.message for x in m.problems]
    return Project(m)


def as_model(name: str, body: str) -> str:
    return "projections:\n  " + name + ":\n" + textwrap.indent(body, "    ")


def errors(tmp_path, body: str) -> list[tuple[str, str]]:
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(body)
    _, problems = read(tmp_path / "ergostat.yaml", extremes=False)
    return [(x.code, x.message) for x in problems if x.level == "error"]


# ---- the syntax

def test_the_instance_definition_checks_and_reads_as_written(tmp_path):
    p = project(tmp_path, as_model("instance", INSTANCE))
    k = p.model.spec.items["instance"]
    assert k.states[0] == "pending" and k.open and not k.by_item
    assert [x.name for x in k.kinds] == ["state-change", "launch", "start", "restart", "resize", "tagged", "stop-or-end"]
    d = k.definition()
    assert d["fields"]["launched_by"] == {"type": "text", "fold": "first"}
    assert d["fields"]["state"]["values"][0] == "pending"
    assert d["events"]["launch"]["key"][2].startswith("each(")
    assert k.show[:3] == ["account", "region", "instance_id"]            # show: the declared fields by default


@pytest.mark.parametrize("bad, code", [
    ("    events:\n      a:\n        when: type == 'x'\n        colour: data.c\n", "undeclared-field"),
    ("    fields:\n      n: {type: text, fold: add}\n", "bad-fold"),
    ("    fields:\n      n: text\n    events:\n      a:\n        when: type == 'x'\n        n: add(1)\n", "bad-fold"),
    ("    fields:\n      state: {values: [a, b]}\n    events:\n      a:\n        when: type == 'x'\n"
     "        state: set('c')\n", "unknown-state"),
    ("    fields:\n      s: {values: [a, b]}\n    events:\n      a:\n        when: type == 'x'\n"
     "        s: \"'c'\"\n", "not-one-of"),
    ("    fields:\n      n: {fold: blend}\n", "unknown-function"),
    ("    fields:\n      n: number\n    events:\n      a:\n        when: type == 'x'\n        n: blend(1)\n",
     "unknown-function"),
    ("    fields:\n      n: number\n    events:\n      a:\n        when: type == 'x'\n        n: data.(\n", "bad-expression"),
    ("    query: type == \n", "bad-expression"),
    ("    fields:\n      n: number\n    events:\n      a:\n        n: data.n\n", "missing-when"),
    ("    fields:\n      n: {type: colour}\n", "bad-type"),
])
def test_check_errors(tmp_path, bad, code):
    got = errors(tmp_path, "projections:\n  thing:\n" + bad)
    assert code in [c for c, _ in got], got


# ---- the fold

FOLD = """\
projections:
  job:
    query: type.startswith('job.')
    key: job
    time: data.at
    fields:
      job: text
      state: {values: [new, running, done]}
      name: text
      first_seen: {type: time, fold: first}
      runs: {type: integer, fold: add}
      notes: {type: list of text, fold: append(2)}
      labels: {type: list of text, fold: union}
      cost: {type: number, fold: max}
      size: integer
    events:
      made:
        when: type == 'job.made'
        job: data.job
        state: "'new'"
        name: data.name
        first_seen: data.at
        size: data.size
      ran:
        when: type == 'job.ran'
        job: data.job
        state: "'running'"
        runs: 1
        notes: data.note
        labels: data.label
        cost: data.cost
      renamed:
        when: type == 'job.renamed'
        job: data.job
        name: set(data.name)
        runs: set(0)
      finished:
        when: type == 'job.finished'
        job: data.job
        state: "'done'"
"""


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_types_folds_and_overrides(tmp_path):
    p = project(tmp_path, FOLD)
    a = lambda t, d, at: p.events.add(t, data={"job": "j1", "at": iso(T0 + at), **d}, at=T0 + at)   # noqa: E731
    a("job.made", {"name": "build", "size": 3}, 0)
    for i in range(3):
        a("job.ran", {"note": f"n{i}", "label": "x" if i else "y", "cost": [5, 9, 2][i]}, 10 + i)
    it = its.one(p.events, p.model.spec, "j1", "job")
    assert it.state == "running" and it.fields["runs"] == 3 and it.fields["notes"] == ["n1", "n2"]
    assert it.fields["labels"] == ["x", "y"] and it.fields["cost"] == 9 and it.fields["size"] == 3
    a("job.renamed", {"name": "ship"}, 20)                                     # set(...): the kind's own rule
    it = its.one(p.events, p.model.spec, "j1", "job")
    assert it.fields["name"] == "ship" and it.fields["runs"] == 0
    a("job.made", {"name": "x", "size": "big"}, 30)                            # a value not of its type: refused
    it = its.one(p.events, p.model.spec, "j1", "job")
    assert it.fields["size"] == 3 and any("size" in r["why"] and "is not integer" in r["why"] for r in it.refused)


def test_the_fold_is_by_event_time_and_a_duplicate_counts_once(tmp_path):
    p = project(tmp_path, FOLD)
    a = lambda t, d, at, rec: p.events.add(t, data={"job": "j2", "at": iso(T0 + at), **d}, at=T0 + rec)   # noqa: E731
    a("job.made", {"name": "b", "size": 1}, 5, 0)
    a("job.finished", {}, 50, 1)
    a("job.ran", {"cost": 1}, 20, 2)                       # delivered late: older than the state it would replace
    a("job.made", {"name": "a", "size": 1}, 1, 3)          # an earlier birth, late: first takes the earliest
    a("job.ran", {"cost": 1}, 20, 4)                       # delivered twice: the same type and data whole
    it = its.one(p.events, p.model.spec, "j2", "job")
    assert it.state == "done"                              # newest by event time wins
    assert it.fields["first_seen"] == iso(T0 + 1) and it.fields["name"] == "b"   # replace: the newest (at 5)
    assert it.fields["runs"] == 1                          # the duplicate counted once


def test_each_applies_one_event_to_several_objects(tmp_path):
    p = project(tmp_path, as_model("instance", INSTANCE))
    p.events.add("aws.eventbridge", data={"source": "aws.ec2", "account": "1", "region": "r", "time": iso(T0), "detail": {
        "eventName": "RunInstances", "userIdentity": {"arn": "arn:aws:iam::1:user/ana"},
        "requestParameters": {"instanceType": "t3.micro", "imageId": "ami-1"},
        "responseElements": {"instancesSet": {"items": [{"instanceId": "i-a"}, {"instanceId": "i-b"}]}}}}, at=T0)
    got = its.listed(p.events, p.model.spec, "instance") if hasattr(its, "listed") else None
    a = its.one(p.events, p.model.spec, "1/r/i-a", "instance")
    b = its.one(p.events, p.model.spec, "1/r/i-b", "instance")
    assert a.fields["launched_by"] == "ana" and b.fields["type"] == "t3.micro" and a.fields["starts"] == 1
    assert (a.fields["instance_id"], b.fields["instance_id"], a.fields["account"]) == ("i-a", "i-b", "1")   # each its own
    del got


# ---- Save: dated, the rest kept byte for byte

SAVED = """\
name: wb
# the fleet, as the cloud tells it
projections:
  job:
    # who asked for it: ops
    query: type.startswith('job.')   # every job event
    key: job
    fields:
      job: text
      state: {values: [new, done]}   # its lifecycle
      name: text
    events:
      # updated 2026-01-01
      made:
        when: type == 'job.made'   # born
        job: data.job
        name: data.name
      done:
        when: type == 'job.done'
        job: data.job
        state: "'done'"
stocks:
  jobs: {unit: jobs}
"""


def test_save_dates_what_changed_and_keeps_the_rest_byte_for_byte(tmp_path):
    from ergostat.numbers import display
    from ergostat.spec import trying
    p = project(tmp_path, SAVED)
    body = trying.definition_text(p.model.spec, "job")
    assert body.startswith("# who asked for it: ops\nquery:")
    new = body.replace("    state: \"'done'\"\n", "    state: \"'done'\"\n    name: data.name\n")
    got = display.save_projection(p, {"name": "job", "yaml": new}, {"at": time.time(), "window": 3600})
    assert got["projection"] == "job"
    text = (tmp_path / "ergostat.yaml").read_text()
    today = datetime.now().date().isoformat()
    want = SAVED.replace("  job:\n", f"  # updated {today}\n  job:\n").replace(
        "      done:\n", f"      # updated {today}\n      done:\n").replace(
        "        state: \"'done'\"\n", "        state: \"'done'\"\n        name: data.name\n")
    assert text == want                                    # only the done entry (and the projection) dated
    p2 = project(tmp_path, text)
    body2 = trying.definition_text(p2.model.spec, "job")
    display.save_projection(p2, {"name": "job", "yaml": body2.replace("type.startswith('job.')", "type.startswith('jobs.')")},
                            {"at": time.time(), "window": 3600})
    text2 = (tmp_path / "ergostat.yaml").read_text()
    assert f"    # updated {today}\n    query: type.startswith('jobs.')" in text2
    assert "# who asked for it: ops" in text2 and text2.count(f"# updated {today}") == 3   # the projection's replaced
    assert "      # updated 2026-01-01\n      made:\n        when: type == 'job.made'   # born\n        job: data.job\n" in text2


# ---- the query engine

def test_indexed_and_scanned_answers_are_the_same(tmp_path):
    p = project(tmp_path)
    delivered, _ = ec2(seed=3, instances=10, days=2)
    recorded(p, delivered)
    q = "data['detail-type'] == 'EC2 Instance State-change Notification' and data.detail.state == 'running'"
    a = eventquery.run(p.events, {"query": q, "limit": 500})
    assert a["indexed"] and a["exact"] and not a["scanned"] and a["read"] == 0
    scan = "(data['detail-type'] == 'EC2 Instance State-change Notification') == true and " \
           "len_free(data.detail.state) == 'running'".replace("len_free(data.detail.state)", "data.detail.state + ''")
    b = eventquery.run(p.events, {"query": scan, "limit": 500})
    assert b["scanned"] and b["total"] == a["total"] > 0
    assert [e["id"] for e in a["events"]] == [e["id"] for e in b["events"]]
    assert a["events"][0]["seq"] > a["events"][-1]["seq"]                         # newest first
    deep = eventquery.run(p.events, {"query": "data.source == 'aws.ec2' and "
                                              "data.detail.requestParameters.instanceType.value == 't3.large'"})
    assert deep["indexed"] and not deep["exact"] and deep["total"] > 0           # a path past the index: evaluated
    c = eventquery.run(p.events, {"query": q + " or data.detail.state == 'stopped'", "compare": q})
    assert c["compare"]["added"] == c["total"] - a["total"] and c["compare"]["dropped"] == 0
    d = eventquery.run(p.events, {"query": "not data.detail.eventName.startswith('Run')", "limit": 1})
    runs = eventquery.run(p.events, {"query": "data.detail.eventName == 'RunInstances'", "limit": 1})
    assert d["exact"] and d["total"] + runs["total"] == d["record"]
    since = eventquery.run(p.events, {"query": q, "since": T0 + 100})
    assert since["total"] == sum(1 for e in a["events"] if e["time"] >= T0 + 100)


def test_has_finds_the_events_containing_a_text_anywhere(tmp_path):
    p = project(tmp_path)
    p.events.add("x.made", data={"a": {"b": ["zz I-ABC1 q"]}, "n": 1}, at=T0)        # nested in a list, upper case
    p.events.add("y.seen", item="i-abc1", data={}, at=T0 + 1)                        # in the key
    p.events.add("z.other", source="i-abc1-src", data={"note": "nothing"}, at=T0 + 2)  # in the source
    p.events.add("w.none", data={"i-abc1": 5, "x": 12345}, at=T0 + 3)                # a name, a number: never searched

    def ask(q):
        return eventquery.run(p.events, {"query": q, "limit": 500})
    a = ask("has('i-abc1')")
    assert sorted(e["type"] for e in a["events"]) == ["x.made", "y.seen", "z.other"]
    assert a["indexed"] and a["exact"] and a["read"] == 0 and a["paths"] == ["text"]
    assert ask("has('I-aBc1')")["total"] == 3                                        # whatever the case
    both = ask("has('i-abc1') and type == 'y.seen'")
    assert both["total"] == 1 and both["exact"]
    assert ask("not has('abc1')")["total"] == 1
    assert ask("has(data.a, 'abc')")["total"] == 1                                    # in one value: evaluated
    assert ask("has('i-')")["scanned"] and ask("has('i-')")["total"] == 3            # under three letters: a scan
    assert ask("has('zz i-abc1 q')")["total"] == 1 and ask("has('q\x1fi')")["total"] == 0
    with pytest.raises(eventquery.QueryError):
        ask("has()")


def test_has_from_the_index_equals_a_scan(tmp_path):
    p = project(tmp_path)
    delivered, _ = ec2(seed=4, instances=8, days=2)
    recorded(p, delivered)
    some = re.search(r"i-[0-9a-f]{8,}", json.dumps(delivered[len(delivered) // 2])).group(0)
    for text in (some, some.upper()[:6], "running", "RunInst", "us-east"):
        a = eventquery.run(p.events, {"query": f"has('{text}')", "limit": 500})
        b = eventquery.run(p.events, {"query": f"has('{text}') == (1 == 1)", "limit": 500})   # no part indexed: a scan
        assert a["exact"] and b["scanned"] and not b.get("capped")
        assert a["total"] == b["total"] > 0 and [e["id"] for e in a["events"]] == [e["id"] for e in b["events"]], text


def test_the_index_follows_the_record(tmp_path):
    p = project(tmp_path)
    p.events.add("x.made", data={"a": {"b": 1}}, at=T0)
    assert eventquery.run(p.events, {"query": "data.a.b == 1"})["total"] == 1
    p.events.add("x.made", data={"a": {"b": 1}}, at=T0 + 1)
    assert eventquery.run(p.events, {"query": "data.a.b == 1.0"})["total"] == 2
    with pytest.raises(eventquery.QueryError):
        eventquery.run(p.events, {"query": "data.("})


# ---- the workbench on the EC2 simulator's stream

def test_kinds_are_suggested_from_the_query_result(tmp_path):
    p = project(tmp_path)
    delivered, _ = ec2(seed=5, instances=15, days=2)
    recorded(p, delivered)
    r = workbench.suggest(p, {"query": "type == 'aws.eventbridge'"})
    names = {k["name"] for k in r["kinds"]}
    assert "ec2-instance-state-change-notification" in names or any("state" in n for n in names)
    by = {k["when"]: k for k in r["kinds"]}
    run = next(k for w, k in by.items() if "RunInstances" in w)
    assert run["when"].startswith("data['detail-type'] == 'AWS API Call via CloudTrail' and data.detail.eventName ==")
    assert run["count"] > 0 and len(run["samples"]) == 2 and "data.detail.responseElements" in run["paths"]
    assert sum(k["count"] for k in r["kinds"]) + 0 <= r["count"] and len(json.dumps(r)) < 20_000


@pytest.mark.parametrize("seed", [7, 11])
def test_the_review_of_an_instance_definition_scores_against_the_truth(tmp_path, seed):
    p = project(tmp_path)
    delivered, truth = ec2(seed=seed, instances=20, days=3)
    recorded(p, delivered)
    expected = {k: {f: v[f] for f in ("state", "type", "image", "launched_by", "launched_at", "tags", "starts", "reboots")
                    if v[f] not in (0, {})}             # an add never added, a merge never merged: not there
                for k, v in truth.items()}
    one = next(iter(truth))
    r = workbench.review(p, {"name": "instance", "yaml": INSTANCE, "expected": expected, "item": one})
    assert r["ok"], r.get("errors")
    x = r["expected"]
    assert x["items"]["found"] == x["items"]["expected"] == len(truth) and x["items"]["extra"] == 0
    assert x["fields_matched_pct"] > 97, x["fields"]
    by = {f["field"]: f for f in x["fields"]}
    for f in ("state", "type", "image", "launched_at", "tags", "starts", "reboots"):
        assert by[f]["mismatch"] == 0, (f, by[f])
    assert by["launched_by"]["mismatch"] <= 0.1 * len(truth)                      # the arn some CloudTrail events lack
    kinds = {k["name"]: k for k in r["kinds"]}
    assert kinds["state-change"]["count"] > 0 and kinds["launch"]["count"] > 0
    assert r["residual"]["remainder"]["count"] == 0 and r["residual"]["no_key"]["count"] == 0
    assert r["residual"]["refused"]["count"] == 0 and r["residual"]["splits"]["count"] == 0
    lc = r["lifecycles"]["state"]
    trans = {(t["from"], t["to"]) for t in lc["transitions"]}
    assert ("pending", "running") in trans and ("stopping", "stopped") in trans
    assert r["duplicates"]["same_data"]["repeats"] > 0                            # delivered twice: counted once
    f = {x["field"]: x for x in r["fields"]}
    assert f["starts"]["min"] >= 1 and len(f["starts"]["histogram"]) >= 1 and f["launched_at"]["min"].startswith("2026-11-2")
    assert f["state"]["top"]
    t = r["timeline"]
    assert t["found"] and t["steps"][0]["kind"] in ("launch", "state-change")
    assert any(s.get("move") for s in t["steps"])
    assert len(json.dumps(r)) < 60_000


def test_the_residual_shows_a_remainder_a_merge_and_a_split(tmp_path):
    p = project(tmp_path)
    delivered, _ = ec2(seed=9, instances=10, days=2)
    recorded(p, delivered)
    draft = INSTANCE.replace("""  restart:
    when: data.detail.eventName == 'RebootInstances'
    account: data.account
    region: data.region
    instance_id: "each(data.detail.requestParameters.instancesSet.items, 'instanceId')"
    reboots: 1
""", "")                                               # reboots no longer taken: the remainder
    draft = draft.replace("    region: data.region\n    instance_id: data.detail['instance-id']\n",
                          "    region: \"'unknown'\"\n    instance_id: data.detail['instance-id']\n")   # state changes keyed otherwise
    r = workbench.review(p, {"name": "instance", "yaml": draft})
    assert r["ok"], r.get("errors")
    rem = r["residual"]["remainder"]
    assert rem["count"] > 0 and any("RebootInstances" in k["when"] for k in rem["kinds"])
    assert r["residual"]["splits"]["count"] > 0                                   # launches under another key
    merged = re.sub(r"\n    instance_id: \"each\(.*", "", INSTANCE.replace("key: [account, region, instance_id]",
                                                                     "key: region"))      # too coarse a key
    r2 = workbench.review(p, {"name": "instance", "yaml": merged})
    assert r2["residual"]["merges"]["count"] > 0 and r2["residual"]["merges"]["fields"][0]["field"] in (
        "launched_by", "launched_at")


def test_each_residual_group_gives_its_events_whole_to_open_in_the_mapping(tmp_path):
    p = project(tmp_path)
    delivered, _ = ec2(seed=9, instances=10, days=2)
    recorded(p, delivered)
    draft = INSTANCE.replace("pending, running, stopping, stopped", "pending, running, stopped")      # stopping refused
    draft = draft.replace("""  restart:
    when: data.detail.eventName == 'RebootInstances'
    account: data.account
    region: data.region
""", """  restart:
    when: data.detail.eventName == 'RebootInstances'
    account: data.account
    region: data.detail.eventSource
""")                                                                                                   # reboots keyed otherwise
    draft = draft.replace("""    when: data.detail.eventName == 'StartInstances'
    account: data.account
    region: data.region
    instance_id: "each(data.detail.requestParameters.instancesSet.items, 'instanceId')"
""", """    when: data.detail.eventName == 'StartInstances'
    account: data.account
    region: data.region
    instance_id: data.detail.nothing
""")                                                                                                   # starts: no key read
    s = workbench.review(p, {"name": "instance", "yaml": draft, "compare": False})["residual"]
    g = next(x for x in s["no_key"]["groups"] if x["kind"] == "start")
    assert g["count"] > 0 and g["lacks"] == [] and g["no_value"] == ["instance_id"]
    assert 0 < len(g["events"]) <= workbench.OPEN_MOST
    assert {e["kind"] for e in g["events"]} == {"start"} and g["events"][0]["data"]["detail"]["eventName"] == "StartInstances"
    ref = next(x for x in s["refused"]["groups"] if x.get("value") == "stopping")
    assert ref["field"] == "state" and ref["kinds"] == ["state-change"]
    assert all(e["data"]["detail"]["state"] == "stopping" for e in ref["samples"]) and ref["samples"]
    sp = next(x for x in s["splits"]["groups"] if x["kinds"] == ["restart"])
    assert sp["differ"] == ["region"] and sp["twin"].split("/")[2] == sp["samples"][0].split("/")[2]
    assert {e["kind"] for e in sp["events"]} >= {"restart"} and {e["object"] for e in sp["events"]} <= {sp["samples"][0], sp["twin"]}


def test_the_review_compares_with_the_saved_definition(tmp_path):
    p = project(tmp_path, as_model("instance", INSTANCE))
    delivered, _ = ec2(seed=4, instances=10, days=2)
    recorded(p, delivered)
    draft = INSTANCE.replace("  resize:\n", "  resize-off:\n").replace(
        "when: data.detail.eventName == 'ModifyInstanceAttribute'", "when: false")
    r = workbench.review(p, {"name": "instance", "yaml": draft})
    c = r["compared"]
    assert c["saved"] == c["draft"] and c["appear"] == c["disappear"] == 0
    assert c["change"] >= 0 and all(f["field"] == "type" for f in c["fields"])


def test_the_api_answers(tmp_path):
    from ergostat.web.projection_api import post

    class Live:
        def __init__(self, p):
            self.p = p

        def get(self):
            return self.p

        def reloaded(self):
            pass

    p = project(tmp_path)
    delivered, _ = ec2(seed=2, instances=5, days=1)
    recorded(p, delivered)
    live = Live(p)
    code, q = post(live, "events/query", json.dumps({"query": "data.source == 'aws.ec2'", "limit": 3}).encode(), 3600)
    assert code == 200 and q["shown"] == 3 and q["total"] == len(delivered)
    code, k = post(live, "events/kinds", json.dumps({"query": "data.source == 'aws.ec2'"}).encode(), 3600)
    assert code == 200 and k["kinds"]
    code, r = post(live, "projections/review", json.dumps({"name": "instance", "yaml": INSTANCE}).encode(), 3600)
    assert code == 200 and r["ok"] and r["objects"]["count"] > 0
    code, e = post(live, "events/query", json.dumps({"query": "data.("}).encode(), 3600)
    assert code == 400 and "query" in e["error"]
    code, f = post(live, "projections/fold", json.dumps({"name": "instance", "yaml": INSTANCE,
                                                          "events": q["events"][:1]}).encode(), 3600)
    assert code == 200 and f["ok"]


def test_ignore_is_accepted_by_check_and_not_read_by_the_fold(tmp_path):
    body = INSTANCE.replace("time: data.time\n", "time: data.time\nignore: [type, source, data.version, \"data['detail-type']\"]\n")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    p = project(tmp_path / "a", as_model("instance", body))
    k = p.model.spec.items["instance"]
    assert k.ignore == ("type", "source", "data.version", "data['detail-type']")
    assert "ignore" not in k.definition()            # what the item index is rebuilt by: ignore: changes no object
    assert [c for c, _ in errors(tmp_path, as_model("x", "ignore: data.version\n"))] == ["bad-ignore"]
    p2 = project(tmp_path / "b", as_model("instance", INSTANCE))
    delivered, _ = ec2(seed=3, instances=5, days=1)
    recorded(p, delivered)
    recorded(p2, delivered)
    a = workbench.review(p, {"name": "instance", "yaml": body, "compare": False})
    b = workbench.review(p2, {"name": "instance", "yaml": INSTANCE, "compare": False})
    assert a["objects"]["count"] == b["objects"]["count"] and a["fields"] == b["fields"]   # the fold never reads it


def test_the_review_reports_the_unmapped_paths(tmp_path):
    p = project(tmp_path)
    delivered, _ = ec2(seed=3, instances=5, days=1)
    recorded(p, delivered)
    r = workbench.review(p, {"name": "instance", "yaml": INSTANCE, "compare": False})
    u = {x["path"]: x for x in r["unmapped"]["paths"]}
    assert r["unmapped"]["count"] > 0 and "type" in u and u["type"]["events"] > 0
    assert "data.detail.state" not in u and "data.account" not in u          # read by a field, by the key
    assert not any(x.startswith("data.detail.requestParameters.instancesSet") for x in u)   # each() reads it
    ign = INSTANCE.replace("time: data.time\n", "time: data.time\nignore: [type, data.detail.userAgent]\n")
    r2 = workbench.review(p, {"name": "instance", "yaml": ign, "compare": False})
    u2 = {x["path"] for x in r2["unmapped"]["paths"]}
    assert "type" not in u2 and not any(x.startswith("data.detail.userAgent") for x in u2)
    assert r2["unmapped"]["ignored"] == 2


def test_suggestions_leave_out_what_the_kinds_accepted_take(tmp_path):
    p = project(tmp_path)
    delivered, _ = ec2(seed=5, instances=10, days=2)
    recorded(p, delivered)
    q = "data.source == 'aws.ec2'"
    first = workbench.suggest(p, {"query": q})
    assert first["kinds"] and all(k["count"] > 0 for k in first["kinds"])
    after = workbench.suggest(p, {"query": q, "taken": [k["when"] for k in first["kinds"]]})
    assert after["untaken"] == first["count"] - sum(k["count"] for k in first["kinds"])
    assert all(k["count"] > 0 for k in after["kinds"])
    if not first.get("kinds_left"):
        assert after["kinds"] == [] and after["untaken"] == 0


def test_one_event_folded_by_a_draft(tmp_path):
    p = project(tmp_path)
    delivered, _ = ec2(seed=3, instances=5, days=1)
    recorded(p, delivered)
    e = eventquery.run(p.events, {"query": "data['detail-type'] == 'EC2 Instance State-change Notification'",
                                  "limit": 1})["events"][0]
    r = workbench.folded(p, {"name": "instance", "yaml": INSTANCE, "events": [e]})
    assert r["ok"] and r["took"][e["id"]] == "state-change"
    o = r["objects"][0]
    assert o["state"] == e["data"]["detail"]["state"] and o["fields"]["account"] == e["data"]["account"]


# ---- the key: named by its fields, solved per kind of event

def findings(tmp_path, body: str) -> list[tuple[str, str]]:
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(body)
    _, problems = read(tmp_path / "ergostat.yaml", extremes=False)
    return [(x.code, x.message) for x in problems if x.level == "finding"]


@pytest.mark.parametrize("bad, says", [
    ("    key: [gid, colour]\n    fields:\n      gid: text\n", "colour is not one of its fields"),
    ("    key: data.gid\n    fields:\n      gid: text\n", "data.gid is not one of its fields"),
    ("    key: gid\n    fields:\n      gid: text\n    events:\n      a:\n        when: true\n        gid: set(data.g)\n",
     "not a fold call like set(...)"),
    ("    key: gid\n    fields:\n      gid: text\n    events:\n      a:\n        when: true\n        gid: data.g\n"
     "        key: data.h\n", "has no key of its own"),
])
def test_the_key_names_declared_fields_each_a_plain_expression(tmp_path, bad, says):
    got = errors(tmp_path, "projections:\n  thing:\n" + bad)
    assert any(c == "bad-key" and says in m for c, m in got), got


def test_a_kind_that_does_not_tell_a_key_field_is_a_finding_and_its_events_have_no_key(tmp_path):
    body = INSTANCE.replace("    region: data.region\n    instance_id: \"each(data.detail.requestParameters.resourcesSet",
                            "    instance_id: \"each(data.detail.requestParameters.resourcesSet")   # tagged: no region
    assert not errors(tmp_path, as_model("instance", body))
    got = findings(tmp_path, as_model("instance", body))
    got = [m for c, m in got if c == "key-not-told"]
    assert len(got) == 1 and "events.tagged: tells no region of the key" in got[0]
    p = project(tmp_path, as_model("instance", body))
    k = p.model.spec.items["instance"]
    by = {x.name: x for x in k.kinds}
    assert by["tagged"].key is None and by["tagged"].untold == ["region"]
    assert [v.text for v in by["state-change"].key] == ["data.account", "data.region", "data.detail['instance-id']"]
    assert by["launch"].key[2].text.startswith("each(")
    delivered, _ = ec2(seed=3, instances=5, days=1)
    recorded(p, delivered)
    r = workbench.review(p, {"name": "instance", "yaml": body, "compare": False})
    nk = r["residual"]["no_key"]
    assert nk["count"] > 0 and set(nk["by_kind"]) == {"tagged"} and nk["lacks"] == {"tagged": ["region"]}
    assert r["objects"]["key"] == ["account", "region", "instance_id"]


def test_a_key_field_told_by_a_spread_is_that_path_s_field_and_no_key_is_the_envelope_s_item(tmp_path):
    p = project(tmp_path, as_model("gadget", """\
query: type.startswith('gadget.')
key: gid
fields:
  gid: text
  colour: text
events:
  made:
    when: type == 'gadget.made'
    "...": data
  painted:
    when: type == 'gadget.painted'
    "...": pick(data, 'colour')
"""))
    k = p.model.spec.items["gadget"]
    by = {x.name: x for x in k.kinds}
    assert [v.text for v in by["made"].key] == ["data.gid"] and by["painted"].untold == ["gid"]
    p.events.add("gadget.made", item="x/1", data={"gid": "g1", "colour": "red"}, at=T0)
    assert its.one(p.events, p.model.spec, "g1", "gadget").fields == {"gid": "g1", "colour": "red"}
    (tmp_path / "b").mkdir()
    k2 = project(tmp_path / "b", as_model("note", "query: type.startswith('note.')\n")).model.spec.items["note"]
    assert k2.key is None and k2.by_item and k2.key_of({"type": "note.x", "item": "note/1", "data": {}}) == "note/1"
