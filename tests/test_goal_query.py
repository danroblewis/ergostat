"""A goal on a query: its PromQL is its process variable, made an auxiliary named for the goal (drawn, read by blocks),
read through the built-in source ergostat, which answers this project's own series from VictoriaMetrics."""
import json
import textwrap

from ergostat import model as mdl
from ergostat.spec import engine, read

VM = 'storage:\n  measurements: {url: "http://127.0.0.1:1"}\n'
GOAL = """
goals:
  fast:
    query: histogram_quantile(0.9, sum by (le) (rate(ticket_lead_seconds_bucket{to="done"}[1h])))
    unit: s
    hold: "<= 30"
"""


def model(tmp_path, body):
    head = "name: t\nprojections:\n  ticket:\n    query: key.startswith('ticket/')\n    fields:\n      state:\n        type: one of [open, done]\n"
    (tmp_path / "ergostat.yaml").write_text(head + textwrap.dedent(body))
    return read(tmp_path / "ergostat.yaml")


def test_a_goals_query_is_its_process_variable_an_auxiliary_named_for_it(tmp_path):
    spec, ps = model(tmp_path, VM + GOAL)
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps if p.level == "error"]
    a = spec.auxiliaries["fast"]
    assert a.unit == "s" and (s := a.sensors["main"]).query == {"source": "ergostat", "promql": s.query["promql"]}
    assert "ticket_lead_seconds_bucket" in s.query["promql"] and s.every == 15
    assert spec.goals["fast"].of.kind == "auxiliary" and spec.goals["fast"].of.name == "fast"


def test_the_built_in_source_needs_no_storage_declared(tmp_path):
    _, ps = model(tmp_path, GOAL)                    # (the readings are in VictoriaMetrics, wherever storage: says)
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps if p.level == "error"]


def test_a_goal_query_whose_name_is_taken_is_refused(tmp_path):
    _, ps = model(tmp_path, VM + "auxiliaries:\n  fast: {unit: s}\n" + GOAL)
    assert any(p.level == "error" and "already a part of the model" in str(p) for p in ps)


def test_the_engine_reads_it_for_this_project_only(tmp_path, monkeypatch):
    head = "name: t\nprojections:\n  ticket:\n    query: key.startswith('ticket/')\n    fields:\n      state:\n        type: one of [open, done]\n"
    (tmp_path / "ergostat.yaml").write_text(head + VM + textwrap.dedent(GOAL))
    spec = mdl.load(tmp_path).spec
    asked = []

    class R:
        def __init__(self, url): asked.append(url)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            data = {"resultType": "vector", "result": [{"value": [0, "12.5"]}]}
            return json.dumps({"status": "success", "data": data}).encode()

    monkeypatch.setattr(engine.urllib.request, "urlopen", lambda url, timeout=None: R(url))
    s = spec.auxiliaries["fast"].sensors["main"]
    v, why = engine.prometheus(spec.storage.url, s.query["promql"], 5, extra_label="project=x")
    assert v == 12.5 and "extra_label=project%3Dx" in asked[0]
