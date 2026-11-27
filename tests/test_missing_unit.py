"""A missing unit is a check finding (SPEC §12, ``no-unit``), drawn ``unit ?`` on the stock, not a request of the owner
per stock: no attention entry asks for a unit, requests-handled does not count them, and ``ergostat check`` names each
unitless stock once with its file and line (the dev record missing-unit-is-a-check-finding)."""

from __future__ import annotations

import io
import subprocess
import sys
import textwrap
from pathlib import Path

from ergostat import model as mdl
from ergostat.inbox.entries import entries
from ergostat.library.run import modelling as run
from ergostat.numbers import requests as rq
from ergostat.store import Project

UNITLESS = """\
name: units
stocks:
  backlog:
    description: work waiting
    sensor: {manual: true}
  done:
    description: work finished so far
    cumulative: true
    sensor: {manual: true}
  parked:
    description: work set aside
    sensor: {manual: true}
  tickets-open:
    unit: tickets
    description: tickets open
    sensor: {manual: true}
flows:
  finishing:
    from: backlog
    to: done
    description: work finished
    driven-by: +stock.backlog
  parking:
    from: backlog
    to: parked
    description: work set aside
    driven-by: +stock.backlog
uses:
  modelling: {use: modelling}
"""
LINES = {"stock.backlog": 4, "stock.done": 7, "stock.parked": 11}      # each stock's own lines begin in UNITLESS


def project(tmp_path: Path) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(UNITLESS))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
    return Project(m)


def test_each_unitless_stock_is_one_check_finding_with_its_file_and_line(tmp_path):
    p = project(tmp_path)
    mine = [x for x in p.model.problems if x.code == "no-unit"]
    assert {x.about: (x.level, str(x.where)) for x in mine} == {a: ("finding", f"ergostat.yaml:{n}") for a, n in LINES.items()}
    assert len(mine) == 3                                       # once each; the stock with a unit not at all
    said = [(lv, msg.split(" Give")[0]) for lv, msg in mdl.check(p.model) if ": no unit." in msg]   # /api/status's list
    assert sorted(said) == sorted(("warn", f"ergostat.yaml:{n}: stock {a.split('.', 1)[1]}: no unit.") for a, n in LINES.items())


def test_no_attention_entry_asks_for_a_unit_and_requests_handled_does_not_count_them(tmp_path, monkeypatch):
    p = project(tmp_path)
    old = rq.rid("craft", "no-unit", "stock.backlog")              # one raised before, when it was a request
    rq.event(p, old, "raised", {"source": "craft", "code": "no-unit", "about": "stock.backlog", "says": "no unit",
                                "tier": "rule", "raised": 1.0, "since": 1.0})
    got = rq.sync(p, coherence=False, extremes=False)
    assert got["answered"] == 1 and rq.stored(p)[old]["state"] == "answered"
    assert rq.stored(p)[old]["why"] == "a check finding now, not a request"
    assert not [r for r in rq.current(p) if r["code"] == "no-unit"]
    assert got["open"] == len(rq.current(p, ("open", "proposed")))  # what unanswered-requests reads: no unit in it
    monkeypatch.chdir(tmp_path)                                  # the fixer runs: nothing it can infer is held for anyone
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert run.rules([]) == 0
    assert not [r for r in rq.current(p) if r["code"] == "no-unit"]
    assert not [e for e in entries(p) if "unit" in f"{e.get('class')} {e.get('summary')} {e.get('why')}"]


def test_the_fixer_proposes_a_unit_it_can_infer_from_the_sensor(tmp_path, monkeypatch):
    text = textwrap.dedent(UNITLESS).replace("  backlog:\n    description: work waiting\n    sensor: {manual: true}\n",
                                             "  backlog:\n    description: work waiting\n"
                                             "    sensor: {projection: ticket, state: open, every: 2s}\n")
    text += "projections:\n  ticket:\n    id: ticket/*\n    description: a ticket\n    states: [open, closed]\n" \
            "    on: {ticket.opened: open, ticket.closed: closed}\n"
    (tmp_path / "ergostat.yaml").write_text(text)
    p = Project(mdl.load(tmp_path))
    from ergostat.numbers import proposals as pr
    from ergostat.numbers import rules as ru
    assert [r["about"] for r in ru.unitless(p)] == ["stock.backlog", "stock.done", "stock.parked"]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert run.rules([]) == 0
    made = [f for _, f in pr.changes(p).values() if f.get("kind") == "unit"]
    assert any("unit: tickets" in str(f.get("edit")) for f in made), made     # the kind its sensor counts
    assert "stock.backlog" not in [r["about"] for r in ru.unitless(p)]         # its change waits: not made again


def test_a_change_adding_a_unitless_stock_is_judged_as_before_a_craft_note_not_a_new_finding(tmp_path):
    from ergostat.numbers import improve as im
    from ergostat.numbers import scorecard as sc
    p = project(tmp_path)               # tickets-open has no flow: a change gives it one, into a new stock with no unit
    add = "    sensor: {manual: true}\nflows:\n"
    r = im.trial(p, {"kind": "structure", "parts": ["stock.tickets-open", "stock.closed"], "title": "tickets close",
                     "edit": {"file": "ergostat.yaml", "replace": add,
                              "with": "    sensor: {manual: true}\n  closed:\n    description: tickets closed so far\n"
                                      "    cumulative: true\n    sensor: {manual: true}\nflows:\n  closing:\n"
                                      "    from: tickets-open\n    to: closed\n    description: tickets closed\n"
                                      "    driven-by: +stock.tickets-open\n"},
                     "reasons": [{"says": "tickets are closed", "evidence": "finding:stock-without-flows@stock.tickets-open"}]})
    assert r["would"] == "be proposed", r
    f = r["findings"]
    assert "stock-without-flows@stock.tickets-open" in f["answered"]
    assert "no-unit@stock.closed" in f["notes_new"] and not [x for x in f["new"] if x.startswith("no-unit")], f
    assert sc.findings(p.model.problems) & {"no-unit@stock.backlog"} == set()     # the scorecard: a note, as before
    assert "no-unit@stock.backlog" in sc.notes(p.model.problems)


def test_ergostat_check_warns_naming_the_file_and_line(tmp_path):
    project(tmp_path)
    got = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "check"], capture_output=True, text=True,
                         timeout=120)
    assert got.returncode == 0, got.stdout + got.stderr                      # a warning, not an error
    lines = [x for x in got.stdout.splitlines() if "no unit" in x]
    assert len(lines) == 3, got.stdout
    for a, n in LINES.items():
        assert any("no-unit" in x and f"ergostat.yaml:{n}: stock {a.split('.', 1)[1]}: no unit" in x for x in lines), lines
