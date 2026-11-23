"""Known controller laws declared on an external block (control/laws.py, numbers/extlaw.py's ratio step, SPEC §12d):
each kind compiles and steps as its rule says on a sequence worked by hand, each refusal is bad-law at its key, and a
model with no law compiles as it did."""

from __future__ import annotations

import hashlib
import io
import json
import textwrap

from ergostat.control import laws
from ergostat.numbers import extlaw as el
from ergostat.spec import load, read

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
