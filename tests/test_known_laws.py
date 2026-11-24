"""Known controller laws declared on an external block (control/laws.py, numbers/extlaw.py's ratio step, SPEC §12d):
each kind compiles and steps as its rule says on a sequence worked by hand, each refusal is bad-law at its key, and a
model with no law compiles as it did."""

from __future__ import annotations

import hashlib
import io
import json
import math
import random
import textwrap
import time

from ergostat import model as mdl
from ergostat.control import laws
from ergostat.numbers import external as ex
from ergostat.numbers import extlaw as el
from ergostat.spec import load, read
from ergostat.store import Project

KUBE = """\
name: k
stocks:
  replicas:
    unit: pods
    sensor: {manual: true}
auxiliaries:
  load:
    unit: pods
    sensor: {manual: true}
  utilisation:
    unit: pods/pods
    sensor: {manual: true}
    equation: auxiliary.load / stock.replicas
flows:
  scale: {to: replicas, two-way: true}
goals:
  headroom: {auxiliary: utilisation, hold: "<= 0.7"}
blocks:
  hpa:
    type: external
    in: auxiliary.utilisation
    out: flow.scale
    identify: {input: auxiliary.utilisation, output: stock.replicas}
"""


def model(tmp_path, law: str = "", text: str = KUBE):
    p = tmp_path / "ergostat.yaml"
    p.write_text(textwrap.dedent(text) + textwrap.indent(textwrap.dedent(law), "    "))
    return p


def steps(law, u0, xs):
    st, out = el.start(law, u0, xs[0]), []
    for x in xs:
        out.append(el.step(law, st, x))
    return out


def test_a_declared_hpa_compiles_and_steps_as_its_rule(tmp_path):
    b = load(model(tmp_path, "law: {kind: kubernetes-hpa, target: 0.5, min: 2, max: 10}\n")).blocks["hpa"]
    assert b.law.kind == "kubernetes-hpa"
    assert b.law.params == {"target": 0.5, "min": 2, "max": 10, "tolerance": 0.1, "stabilize-down": 300.0,
                            "stabilize-up": 0.0, "every": 15.0}
    b = load(model(tmp_path, "law:\n  kind: kubernetes-hpa\n  target: 0.5\n  min: 2\n  max: 10\n  stabilize-down: 1m\n"
                             )).blocks["hpa"]
    law = laws.law(b.law)
    assert law.family == "ratio" and law.dt == 15.0
    # by hand, from 4 replicas, a 60s window down (4 samples of 15s, now's included):
    xs = [0.52,  # 0.52/0.5 = 1.04, within 10%: holds 4
          1.0,   # ⌈4 × 2⌉ = 8: up at once
          0.5,   # on target: holds 8
          0.1, 0.1, 0.1,   # ⌈8 × 0.2⌉ = 2, but 8 is still desired within the window: holds 8
          0.1,   # every desired in the window is 2: down to 2
          0.01, 0.01, 0.01, 0.01, 0.01,   # ⌈2 × 0.02⌉ = 1: clamped at min 2
          5.0]   # ⌈2 × 10⌉ = 20: clamped at max 10
    assert steps(law, 4.0, xs) == [4, 8, 8, 8, 8, 8, 2, 2, 2, 2, 2, 2, 10]
    # a window up (30s: 2 samples): one sample's spike does not scale up; two do, to the lesser
    up = laws.law(laws.check({"kind": "kubernetes-hpa", "target": 0.5, "min": 1, "max": 10, "stabilize-up": "30s"})[0])
    assert steps(up, 4.0, [0.5, 1.0, 0.5, 1.0, 0.75]) == [4, 4, 4, 4, 6]


def test_a_declared_alert_rule_compiles_and_fires_after_for(tmp_path):
    b = load(model(tmp_path, "law: {kind: alert-rule, threshold: 300, side: above, for: 45s}\n")).blocks["hpa"]
    assert b.law.kind == "alert-rule" and b.law.params == {"threshold": 300.0, "side": "above", "for": 45.0}
    law = laws.law(b.law)                       # on 15s evaluations: past 300 at 15s, 30s, 45s, fires at the next
    assert law.family == "onoff" and (law.p["lo"], law.p["hi"]) == (0.0, 1.0)
    assert steps(law, 0.0, [100, 310, 320, 330, 340, 350, 200, 310]) == [0, 0, 0, 0, 1, 1, 0, 0]
    below = laws.law(laws.check({"kind": "alert-rule", "threshold": 5, "side": "below", "for": 0})[0], dt=60.0)
    assert steps(below, 0.0, [9, 4, 4, 6]) == [0, 1, 1, 0]


def test_each_refusal_is_bad_law_at_its_key(tmp_path):
    head = len(KUBE.splitlines())               # the law: line is the next
    cases = [
        ("law:\n  kind: kubernetes-autoscaler\n  target: 1\n", 2, "kind: one of"),
        ("law:\n  kind: [kubernetes-hpa]\n  target: 1\n", 2, "kind: one of"),
        ("law:\n  kind: {name: alert-rule}\n", 2, "kind: one of"),
        ("law:\n  kind: alert-rule\n  threshold: 1\n  side: above\n  for: 1m\n  hysteresis: 2\n", 6, "takes no hysteresis"),
        ("law:\n  kind: kubernetes-hpa\n  target: 0.7\n  min: 1\n", 1, "needs max"),
        ("law:\n  kind: kubernetes-hpa\n  target: 0.7\n  min: 1\n  max: 5\n  tolerance: 2\n", 6, "tolerance: a number from 0"),
        ("law:\n  kind: kubernetes-hpa\n  target: 0\n  min: 1\n  max: 5\n", 3, "target: a number above 0"),
        ("law:\n  kind: kubernetes-hpa\n  target: .nan\n  min: 1\n  max: 5\n", 3, "target: a number"),
        ("law:\n  kind: kubernetes-hpa\n  target: 1\n  min: 6\n  max: 5\n", 5, "max: at least min"),
        ("law:\n  kind: kubernetes-hpa\n  target: 1\n  min: 1.5\n  max: 5\n", 4, "a whole number"),
        ("law:\n  kind: kubernetes-hpa\n  target: 1\n  min: 1\n  max: 5\n  stabilize-down: 2h\n", 6, "stabilize-down: a duration"),
        ("law:\n  kind: alert-rule\n  threshold: 1\n  side: sideways\n  for: 1m\n", 4, "side: above or below"),
        ("law: kubernetes-hpa\n", 1, "a map"),
    ]
    alert = "law:\n  kind: alert-rule\n  threshold: 1\n  side: above\n  for: 1m\n  {}: x\n"
    cases += [(alert.format(k), 6, f"law.{s}: alert-rule takes no {s}")     # keys YAML types: int, 0, float, bool
              for k, s in (("2", "2"), ("0", "0"), ("1.5", "1.5"), ("true", "True"))]
    huge = "9" * 400                            # PyYAML reads it as an unbounded int; float() of it overflows
    hpa = "law:\n  kind: kubernetes-hpa\n  target: {}\n  min: {}\n  max: {}\n  tolerance: {}\n  every: {}\n"
    for i, said in enumerate(["target: a number above", "min: a number from", "max: a number from",
                              "tolerance: a number from", "every: a duration from"]):
        vals = ["1", "1", "5", "0.1", "15s"]
        vals[i] = huge
        cases.append((hpa.format(*vals), 3 + i, said))
    cases += [("law:\n  kind: alert-rule\n  threshold: -" + huge + "\n  side: above\n  for: 1m\n", 3, "threshold: a number"),
              ("law:\n  kind: alert-rule\n  threshold: 1\n  side: above\n  for: " + huge + "\n", 5, "for: a duration"),
              (hpa.format(1, 1, 5, 0.1, huge + "s"), 7, "every: a duration from")]   # a string: float() gives inf
    for law, line, said in cases:
        _, problems = read(model(tmp_path, law))
        bad = [p for p in problems if p.code == "bad-law"]
        assert len(bad) == 1 and said in bad[0].message and bad[0].where.line == head + line, (law, bad)
    no_identify = KUBE.replace("    identify: {input: auxiliary.utilisation, output: stock.replicas}\n", "")
    _, problems = read(model(tmp_path, "law: {kind: alert-rule, threshold: 1, side: above, for: 1m}\n", no_identify))
    bad = [p for p in problems if p.code == "bad-law"]
    assert len(bad) == 1 and "identify" in bad[0].message and bad[0].where.line == head, bad
    spec, problems = read(model(tmp_path, "law: {kind: alert-rule}\n"))
    bad = sorted(p.message.rsplit(" needs ", 1)[-1] for p in problems if p.code == "bad-law")
    assert bad == ["for:", "side:", "threshold:"] and spec.blocks["hpa"].law is None, problems


def test_a_model_with_no_law_compiles_to_an_identical_ir(tmp_path):
    plain = load(model(tmp_path))
    assert plain.blocks["hpa"].law is None and "law" not in plain.blocks["hpa"].params
    declared = load(model(tmp_path, "law: {kind: alert-rule, threshold: 1, side: above, for: 1m}\n"))
    assert declared.blocks["hpa"].law is not None and "law" not in declared.blocks["hpa"].params
    declared.blocks["hpa"].law = None
    assert declared == plain and repr(declared) == repr(plain)


# the whole Blocks answer of KUBE with no law, as main drew it before declared laws were drawn: sha256 of its JSON
GOLDEN = "f36112a7505b7c091f36011e0100178e52468ce49e8722c8be6b8410607dbebe"
HPA = "law: {kind: kubernetes-hpa, target: 0.6, min: 2, max: 10}\n"
SAID = "scales to ceil(replicas x utilisation / 0.6), within 2..10, down only after 5m"


def blocks(tmp_path, law: str = "", snap: dict | None = None) -> dict:
    from types import SimpleNamespace

    from ergostat import blockdiagram as bd
    return bd.diagram(SimpleNamespace(spec=load(model(tmp_path, law))), snap or {})


def hpa_node(g: dict) -> dict:
    return next(n for n in g["nodes"] if n["id"] == "blk:hpa")


def said_row(n: dict) -> bool:
    return any(k == "declared" and v.startswith(f"kubernetes-hpa: {SAID}") for k, v in n["rows"])


def test_a_declared_law_is_drawn_as_its_blocks_function_and_a_block_without_one_as_before(tmp_path):
    plain = blocks(tmp_path)
    assert hashlib.sha256(json.dumps(plain, sort_keys=True, default=str).encode()).hexdigest() == GOLDEN
    assert "declared" not in hpa_node(plain) and hpa_node(plain)["fn"].get("law") is None
    n = hpa_node(blocks(tmp_path, HPA))
    assert n["declared"] == "declared kubernetes-hpa" and not n.get("identified"), n
    assert n["fn"]["law"] == "⌈u x / 0.6⌉" and n["fn"]["kind"] == "declared kubernetes-hpa" and SAID in n["says"], n
    assert said_row(n), n["rows"]
    a = hpa_node(blocks(tmp_path, "law: {kind: alert-rule, threshold: 300, side: above, for: 45s}\n"))
    assert a["declared"] == "declared alert-rule" and a["fn"]["law"] == "on > 300, off < 300", a
    assert "fires once utilisation is above 300 for 45s" in a["says"], a
    # a law identified from the record (evidence) is drawn over the declared one (an assumption), still said in its rows
    law = {"family": "ratio", "params": {"lo": 2, "hi": 10}, "said": "ratio: found", "short": "⌈u x / 0.58⌉"}
    m = hpa_node(blocks(tmp_path, HPA, {"laws": {"hpa": law}}))
    assert m["identified"] and "declared" not in m and m["fn"]["law"] == "⌈u x / 0.58⌉" and said_row(m), m


def recorded(tmp_path, made: float, declared: float, n: int = 480, seed: int = 0, text: str = KUBE):
    """A project whose HPA record was made by an HPA of target ``made`` (from 4 replicas, a load swinging 1 to 4 pods'
    worth every 30 minutes, with noise, on 15s samples) and whose model declares target ``declared``."""
    tmp_path.mkdir(exist_ok=True)
    model(tmp_path, f"law: {{kind: kubernetes-hpa, target: {declared}, min: 2, max: 10}}\n", text)
    p = Project(mdl.load(tmp_path))
    law = laws.law(laws.check({"kind": "kubernetes-hpa", "target": made, "min": 2, "max": 10})[0])
    rng, u, now = random.Random(seed), 4.0, time.time()
    st, rows = el.start(law, u, 0.5), []
    for k in range(n):
        x = (2.5 + 1.5 * math.sin(2 * math.pi * k / 120) + rng.gauss(0, 0.1)) / u
        u = el.step(law, st, x)
        t = now - (n - k) * 15.0
        rows += [("sensor/utilisation.main", t, x), ("sensor/replicas.main", t, u), ("sensor/load.main", t, x * u)]
    p.measurements.add_many(rows)
    return p, now


def said(p, now) -> list[tuple[str, str]]:
    out = []
    ex.findings(p, p.model.spec, now, lambda code, msg, where, about: out.append((code, msg)))
    return out


def test_declared_law_that_matches_holds(tmp_path):
    p, now = recorded(tmp_path, 0.5, 0.5)
    d = ex.declared(p, p.model.spec, "hpa", now - 86400, now)
    w = d["law"]
    assert d["kind"] == "kubernetes-hpa" and w.family == "ratio" and w.skill > 0.5 and w.r2 > 0.5, (d, w)
    assert w.points == len(ex.identify(p, p.model.spec, "hpa", now - 86400, now)["ts"]) == 481   # held to until
    assert d["beaten"] is None and not ex.disagrees(d)
    assert not [c for c, _ in said(p, now) if c.startswith("external-law")], said(p, now)


def test_declared_law_with_wrong_target_disagrees(tmp_path):
    p, now = recorded(tmp_path, 0.5, 0.8)
    (msg,) = [m for c, m in said(p, now) if c == "external-law-disagrees"]
    assert msg.startswith("block hpa: declared kubernetes-hpa (⌈u x / 0.8⌉) fits its record worse than "), msg
    assert msg.split(": it does not behave as configured (")[1].count("on the last quarter of 481 points held out"), msg
    start = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(now - 480 * 15.0))
    assert f"the record from {start} to " in msg, msg
    assert ex.disagrees(ex.declared(p, p.model.spec, "hpa", now - 86400, now))


def test_too_little_record_says_why(tmp_path):
    p, now = recorded(tmp_path, 0.5, 0.5, n=20)
    d = ex.declared(p, p.model.spec, "hpa", now - 86400, now)
    assert d["law"] is None and "21 points of record" in d["why"] and "at least 40" in d["why"], d
    assert d["why"] == ex.identify(p, p.model.spec, "hpa", now - 86400, now)["why"]
    assert not [c for c, _ in said(p, now) if c.startswith("external-law")]
    empty = recorded(tmp_path / "none", 0.5, 0.5, n=0)
    assert "no readings" in ex.declared(empty[0], empty[0].model.spec, "hpa", empty[1] - 60, empty[1])["why"]
    plain = load(model(tmp_path))                  # no law: nothing declared, nothing said of one
    assert ex.declared(p, plain, "hpa", now - 86400, now) is None


def test_loop_control_carries_declared(tmp_path):
    from ergostat.control import loop
    closed = KUBE.replace("    equation: auxiliary.load / stock.replicas\n",
                          "    equation: auxiliary.load / stock.replicas\n    driven-by: [+auxiliary.load, -stock.replicas]\n")
    p, now = recorded(tmp_path, 0.5, 0.8, text=closed)
    c = loop.analyse(p, "headroom", now)["controller"]
    d = c["declared"]
    assert set(d) == {"kind", "short", "skill", "r2", "points", "worse"} and d["kind"] == "kubernetes-hpa", c
    assert d["short"] == "⌈u x / 0.8⌉" and d["points"] == 481 and d["worse"] and d["skill"] < 0, d
    assert c["block"] == "hpa" and c["identified"]["family"] == "ratio", c      # an HPA's record: the ratio family
    from ergostat.web.server import Live, api
    assert api(Live(p), "loop-control", {"goal": ["headroom"]})["controller"]["declared"] == d
    model(tmp_path, "", closed)                    # with no law, the controller's answer has no declared
    assert "declared" not in loop.analyse(Project(mdl.load(tmp_path)), "headroom", now)["controller"]


def test_explain_says_a_declared_law_in_words_and_the_mcp_tool_says_the_same(tmp_path):
    from ergostat.mcp import serve
    from ergostat.spec.explain import explain
    text = explain(load(model(tmp_path, HPA)), "hpa")
    assert f"declared kubernetes-hpa: {SAID}" in text and "an assumption until tested against the record" in text, text
    assert "declared" not in explain(load(model(tmp_path)), "hpa")
    model(tmp_path, HPA)
    out = io.StringIO()
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "explain", "arguments": {"part": "hpa"}}}
    serve(tmp_path, io.StringIO(json.dumps(call) + "\n"), out)
    got = json.loads(out.getvalue().splitlines()[0])["result"]["content"][0]["text"]
    assert got == text, got
    alert = explain(load(model(tmp_path, "law: {kind: alert-rule, threshold: 5, side: below, for: 0}\n")), "hpa")
    assert "declared alert-rule: fires as soon as utilisation is below 5, resolves as soon as it is back" in alert, alert
