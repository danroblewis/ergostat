"""docs/DASHBOARDS.md's panels are real: every ``chartPanel`` config in it is loaded, its form, options and display
checked against what static/panels.js declares, and its queries asked of the query API (``GET /api/query``) over a
record of the document's own example model, each answering with a value. The rules the document states as checks
hold for every panel not marked bad, and each bad panel breaks exactly the rule it is marked with. The document is one
of ``ergostat help``'s guides, linked from the agent guide and the ergostat-author skill."""

from __future__ import annotations

import base64
import copy
import json
import re
import tomllib
from pathlib import Path

import pytest
import yaml

from ergostat import helpdocs
from ergostat import model as mdl
from ergostat.store import Project
from ergostat.web.server import Live, api

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "DASHBOARDS.md"
MARK = re.compile(r"^<!-- (?:panel: ([\w-]+)(?:, (fix|bad: ([\w-]+)))?|(example model)) -->$")
FENCE = re.compile(r"^```(\w*)")
T = 1_795_400_000.0          # the window's end: the record below is the day before it
DAY = 86400.0
PANEL_KEYS = {"id", "title", "note", "form", "options", "display", "size", "tall", "queries"}
DISPLAY_KEYS = {"unit", "decimals", "legend", "legend_values", "y", "thresholds"}
CLIENT_KEYS = ("label", "hidden")       # a panel's own words for a query, which queryPanels never sends
FORMS = ("line", "bar", "stat", "table")
RULES = ("no-decision", "duration-averaged", "units-apart", "stacked-not-a-whole", "too-many-groups", "flow-as-a-count",
         "threshold-unnamed")


def blocks() -> list[dict]:
    """Each fenced block: its language, text, line, and the mark on the line just before it (if any)."""
    lines, out = DOC.read_text(encoding="utf-8").splitlines(), []
    i = 0
    while i < len(lines):
        if f := FENCE.match(lines[i]):
            start, body = i, []
            i += 1
            while not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            m = MARK.match(lines[start - 1]) if start else None
            out.append({"lang": f[1], "text": "\n".join(body), "at": f"DASHBOARDS.md:{start + 1}",
                        "name": m and m[1], "role": None if not m else "model" if m[4] else "bad" if m[3] else m[2] or "good",
                        "rule": m and m[3]})
        i += 1
    return out


BLOCKS = blocks()
PANELS = [b for b in BLOCKS if b["name"]]


# The options each of the four forms offers, as the old page's panels.js declared them (registerPlotForm): key -> allowed
# values, or (min, max), or ("many", values). Kept here as data since that page was removed (2026-11-25).
REGISTRY: dict[str, dict] = {
    "line": {"style": ["linear", "smooth", "step-after", "step-before", "step-middle"],
             "fill": ["none", "area", "gradient"],
             "stack": ["none", "stacked", "percent"],
             "points": ["auto", "always", "never"],
             "nulls": ["gap", "connect", "zero"],
             "width": (1.0, 4.0)},
    "bar": {"orientation": ["vertical", "horizontal"],
            "stack": ["none", "stacked", "percent"],
            "grouping": ["grouped", "overlaid"],
            "sort": ["none", "value-desc", "value-asc"],
            "values": ["off", "on"]},
    "stat": {"value": ["last", "avg", "min", "max", "sum"],
             "sparkline": ["on", "off"],
             "delta": ["on", "off"],
             "color": ["none", "thresholds"]},
    "table": {"sort": ["none", "name", "last", "avg", "min", "max"],
              "bars_in_cells": ["off", "on"],
              "columns": ("many", ["last", "avg", "min", "max"])},
}


def seeded(tmp_path) -> Project:
    """The example model, and a day of its record: 40 requests, a sixth left working, a sixth in review, a sixth failed,
    the rest done; fifteen requesters, three sizes; the backlog and the busy agents read every five minutes."""
    model = next(b for b in BLOCKS if b["role"] == "model")
    (tmp_path / "ergostat.yaml").write_text(model["text"] + "\n")
    p = Project(mdl.load(tmp_path))
    for n in range(40):
        t0, rid = T - DAY + 600 + n * 2000, f"request/{n}"
        steps = [(0, "request.opened", {"requester": f"person-{n % 15}", "size": "sml"[n % 3], "cost_usd": 0.1}),
                 (300, "request.started", {"cost_usd": 0.4 + n % 3})]
        if n % 6 != 0:
            steps.append((300 + 600 * (1 + n % 4), "request.reviewed", {"cost_usd": 0.2}))
        if n % 6 == 5:
            steps.append((4000, "request.failed", {}))
        elif n % 6 not in (0, 1):
            steps.append((5000, "request.done", {"cost_usd": 0.1}))
        for dt, ty, data in steps:
            if t0 + dt < T:
                p.events.add(ty, item=rid, data=data, at=t0 + dt)
    for i in range(int(DAY // 300)):
        p.measurements.add("sensor/backlog.count", float(5 + i % 11), at=T - DAY + i * 300)
        p.measurements.add("sensor/agents.busy", float(i % 5), at=T - DAY + i * 300)
    return p


def answers(p, cfg: dict) -> list[dict]:
    """The panel's queries asked as the Dashboard asks them, over the day before ``T``."""
    qs = [{k: v for k, v in q.items() if k not in CLIENT_KEYS} for q in cfg["queries"]]
    body = {"since": "1d", "until": T, "points": 120, "queries": qs}
    q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    return api(Live(p), "query", {"q": [q]})["results"]


def checked(cfg: dict, got: list[dict]) -> None:
    """The config is one panels.js draws as written, and every query answered with a value."""
    assert set(cfg) <= PANEL_KEYS, sorted(set(cfg) - PANEL_KEYS)
    assert cfg["form"] in FORMS and cfg.get("size", "m") in ("s", "m", "l", "full")
    assert isinstance(cfg.get("title"), str) and cfg["title"]
    for key, v in (cfg.get("options") or {}).items():
        allowed = REGISTRY[cfg["form"]].get(key)
        assert allowed is not None, f"{cfg['form']} has no option {key!r}"
        if isinstance(allowed, list):
            assert v in allowed, f"{key}: {v!r} is not one of {allowed}"
        elif allowed[0] == "many":
            assert isinstance(v, list) and set(v) <= set(allowed[1]), f"{key}: {v!r}"
        else:
            assert allowed[0] <= v <= allowed[1], f"{key}: {v!r}"
    display = cfg.get("display") or {}
    assert set(display) <= DISPLAY_KEYS, sorted(set(display) - DISPLAY_KEYS)
    for th in display.get("thresholds", []):
        assert set(th) <= {"value", "label"} and isinstance(th["value"], int | float), th
    assert 1 <= len(cfg["queries"]) <= 12 and len({q["id"] for q in cfg["queries"]}) == len(cfg["queries"])
    assert [r["id"] for r in got] == [q["id"] for q in cfg["queries"]]
    for r in got:
        assert "error" not in r, r
        assert any(v for s in r["series"] for v in s["values"] if v is not None), f"query {r['id']} answered nothing"


def breaches(cfg: dict, got: list[dict]) -> set[str]:
    """Which of the document's checkable rules the panel breaks."""
    out, qs, plotted = set(), cfg["queries"], cfg["form"] in ("line", "bar")
    if not (cfg.get("note") or "").strip():
        out.add("no-decision")
    if plotted and any(q.get("measure") == "time_in_state" and q.get("agg") == "avg" for q in qs):
        out.add("duration-averaged")
    if len({r["unit"] for r in got}) > 1:
        out.add("units-apart")
    if (cfg.get("options") or {}).get("stack", "none") != "none" and not (len(qs) == 1 and qs[0].get("group_by")):
        out.add("stacked-not-a-whole")
    if any(r.get("capped") for r in got):
        out.add("too-many-groups")
    flow = lambda q: q.get("measure") in ("entries", "exits") or q["source"] == "events"   # noqa: E731
    fixed = lambda q: q.get("bucket") not in (None, "auto")                               # noqa: E731
    if plotted and any(flow(q) and q.get("transform", "none") == "none" and (cfg["form"] == "line" or not fixed(q)) for q in qs):
        out.add("flow-as-a-count")
    if any(not (t.get("label") or "").strip() for t in (cfg.get("display") or {}).get("thresholds", [])):
        out.add("threshold-unnamed")
    return out


@pytest.fixture(scope="module")
def record(tmp_path_factory):
    return seeded(tmp_path_factory.mktemp("dashboards"))


def test_every_example_config_in_the_document_is_marked_and_loads():
    assert len(PANELS) >= 25, len(PANELS)
    unmarked = [b["at"] for b in BLOCKS if b["lang"] == "json" and not b["name"]]
    assert not unmarked, f"a json block with no panel mark, so no test reads it: {unmarked}"
    assert all(b["lang"] == "json" for b in PANELS) and [b["lang"] for b in BLOCKS if b["role"] == "model"] == ["yaml"]
    assert all(b["lang"] in ("json", "yaml") for b in BLOCKS), [b["at"] for b in BLOCKS]
    ids = [json.loads(b["text"])["id"] for b in PANELS]
    assert len(set(ids)) == len(ids), "two panels with one id"
    bad = {b["name"] for b in PANELS if b["role"] == "bad" and b["rule"] != "no-decision"}   # (its fix is removing it)
    assert len(bad) >= 6 and bad <= {b["name"] for b in PANELS if b["role"] == "fix"}, "a bad panel with no fix"
    assert {b["rule"] for b in PANELS if b["role"] == "bad"} == set(RULES), "a rule no bad panel shows"
    assert isinstance(yaml.safe_load(next(b["text"] for b in BLOCKS if b["role"] == "model")), dict)


@pytest.mark.parametrize("block", PANELS, ids=lambda b: f"{b['name']}-{b['role']}-{b['at'].split(':')[1]}")
def test_each_panel_is_answered_by_the_query_api_and_keeps_its_rules(record, block):
    cfg = json.loads(block["text"])
    got = answers(record, cfg)
    checked(cfg, got)
    if block["role"] == "bad":
        assert breaches(cfg, got) == {block["rule"]}, f"{block['at']}: marked {block['rule']}"
    else:
        assert breaches(cfg, got) == set(), f"{block['at']}: a panel the document recommends breaks its rules"


@pytest.mark.parametrize("break_it", [
    lambda c: c["queries"][0].update(state="finished"),             # a state the model does not have
    lambda c: c["queries"][0].update(source="moves", measure="dwell"),   # a measure the query API does not know
    lambda c: c.update(options={"style": "wavy"}),                  # a choice the form does not offer
    lambda c: c.update(form="pie"),
    lambda c: c.update(display={"colour": "red"}),
    lambda c: c["queries"][0].update(kind="ticket"),
])
def test_the_check_fails_a_broken_panel(record, break_it):
    cfg = copy.deepcopy(json.loads(next(b["text"] for b in PANELS if b["name"] == "flowing")))
    checked(cfg, answers(record, cfg))
    break_it(cfg)
    with pytest.raises((AssertionError, KeyError)):
        checked(cfg, answers(record, cfg))


def test_it_is_a_guide_of_ergostat_help_and_linked_for_agents(capsys):
    assert helpdocs.read("dashboards") == DOC.read_text(encoding="utf-8")
    wheel = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["force-include"]["docs/DASHBOARDS.md"] == "ergostat/help/dashboards.md"
    from ergostat.cli import main
    assert main(["help"]) == 0 and "ergostat help dashboards" in capsys.readouterr().out
    for doc in ("docs/AGENT-GUIDE.md", "docs/skills/ergostat-author/SKILL.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert "DASHBOARDS.md" in text and "ergostat help dashboards" in text, doc
