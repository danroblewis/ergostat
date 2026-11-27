"""Reports upstream (SPEC §12m): drafted by an agent (MCP), the owner (CLI), ergostat's own crashes (one a stack
signature) and a block's report line; scrubbed before anyone reads them; moved by the owner; and never sent."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.store import Project

# a model whose names are the owner's secrets, planted to be found in no report
MODEL = """\
name: acme-ledger
systems:
  payments-core: {description: the payments team's system}
sources:
  acmeprom: {type: prometheus, url: "http://prom.acme-internal.corp:9090"}
projections:
  zebraticket:
    id: zebraticket/*
    states: [triage-queue, sorting-hat, done]
    on: {zebraticket.sorted: sorting-hat, zebraticket.closed: done}
stocks:
  invoices-pending:
    unit: invoices
    system: payments-core
    sensor: {projection: zebraticket, state: triage-queue, every: 5s}
flows:
  invoices-arriving: {to: invoices-pending}
  invoices-settled: {from: invoices-pending}
goals:
  ledger-short:
    stock: invoices-pending
    hold: "<= 20"
blocks:
  falcon-settler:
    type: program
    goal: ledger-short
    run: ./settle.sh --host db7.acme-internal.corp
    out: flow.invoices-settled
"""

PLANTED = ["acme-ledger", "payments-core", "acmeprom", "prom.acme-internal.corp", "zebraticket", "triage-queue",
           "sorting-hat", "invoices-pending", "invoices-arriving", "invoices-settled", "ledger-short", "falcon-settler",
           "settle.sh", "db7.acme-internal.corp", "carol.danvers@acme.example.com", "ACME-4411", "10.20.30.40",
           "ghp_0123456789abcdefghijABCDEFGHIJ0123", "hunter2secret", "/Users/carol/acme/ledger", "Carol Danvers",
           "Project Bluebird", "zebraticket/ACME-77", "https://jira.acme-internal.corp/browse/ACME-4411"]


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "acme-ledger"
    d.mkdir()
    (d / "ergostat.yaml").write_text(MODEL)
    p = Project(mdl.load(d))
    assert p.model.spec is not None, p.model.problems
    deny = Path(p.dir) / "reports" / "denylist.txt"     # the owner's own list, in the state directory
    deny.parent.mkdir(parents=True, exist_ok=True)
    deny.write_text("# people and projects\nCarol Danvers\nProject Bluebird\n")
    return p


@pytest.fixture
def offline(monkeypatch):
    """Every way to open a connection fails the test: a report is never sent anywhere."""
    def refuse(*a, **k):
        raise AssertionError(f"a network call was made: {a!r}")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", refuse)


def leaked(text: str) -> list[str]:
    low = text.lower()
    return [s for s in PLANTED if s.lower() in low]


SAYS = ("falcon-settler crashed reading zebraticket/ACME-77 for Carol Danvers (carol.danvers@acme.example.com) on "
        "Project Bluebird")
DETAILS = ("It ran /Users/carol/acme/ledger/settle.sh against db7.acme-internal.corp and 10.20.30.40, token=hunter2secret, "
           "key ghp_0123456789abcdefghijABCDEFGHIJ0123; see https://jira.acme-internal.corp/browse/ACME-4411 and ACME-4411. "
           "invoices-pending stayed above ledger-short in payments-core; acmeprom said so.")


def test_planted_secrets_never_reach_the_text_and_the_log_says_what_went(proj, offline):
    from ergostat.reports import record
    got = record.draft(proj, SAYS, origin="agent", by="work-agent", details=DETAILS,
                       parts=["block.falcon-settler"], findings=["no-modelling-loop"])
    text = Path(got["file"]).read_text()
    assert leaked(text) == []
    assert leaked(got["title"]) == [] and leaked(record.issue_url(got["title"], got["labels"])) == []
    assert text.startswith("Title: ") and "\nLabels: " in text
    assert "## What went wrong" in text and "## The model's shape" in text and "## Reproduction" in text
    assert "block-1" in text and "projection-1/" in text            # stand-ins, the same wherever the same name was
    assert "| stocks | 1 |" in text and "program 1" in text  # counts of parts and kinds stay
    assert "ergostat 0.1.0" in text and "Python" in text
    log = json.loads(Path(got["scrub_file"]).read_text())
    originals = {x["original"].lower() for x in log["removed"]}
    for s in ("falcon-settler", "carol danvers", "project bluebird", "carol.danvers@acme.example.com", "acme-4411",
              "db7.acme-internal.corp", "10.20.30.40"):
        assert any(s in o for o in originals), s
    rules = {x["rule"] for x in log["removed"]}
    assert {"name", "denylist", "email", "host", "ip", "secret", "ticket", "url", "path"} <= rules
    assert all(x["why"] for x in log["removed"])
    rec = record.get(proj, got["id"])                          # the record holds no original either (but where its files are)
    shown = {k: v for k, v in rec.items() if k not in ("file", "scrub_file")}
    assert rec["state"] == "drafted" and leaked(json.dumps(shown, default=str)) == []


def test_the_reproduction_is_a_generic_model_that_checks(proj, tmp_path):
    from ergostat.reports import record
    from ergostat.spec import read
    got = record.draft(proj, "the goal is never met", parts=["block.falcon-settler"])
    text = Path(got["file"]).read_text()
    yml = text.split("```yaml\n", 1)[1].split("```", 1)[0]
    assert leaked(yml) == [] and "echo 0" in yml
    d = tmp_path / "repro"
    d.mkdir()
    (d / "ergostat.yaml").write_text(yml)
    _, problems = read(d / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], [str(x) for x in problems if x.level == "error"]


def boom_a(x):
    return {"a": 1}[x]


def boom_b(x):
    return [][x]


def test_a_crash_is_drafted_once_per_stack_signature(proj, offline):
    from ergostat.reports import crash, record
    crash.forget()
    for _ in range(3):                                     # the same crash again in this process: noted once
        try:
            boom_a("falcon-settler")
        except KeyError as e:
            crash.noted(proj, e, "engine")
    crash.forget()                                         # another process: counted on the same report
    try:
        boom_a("invoices-pending")
    except KeyError as e:
        crash.noted(proj, e, "engine")
    try:
        boom_b(3)
    except IndexError as e:
        crash.noted(proj, e, "web")
    reports = list(record.stored(proj).values())
    assert len(reports) == 2
    a = next(r for r in reports if r["id"].startswith("ergostat.report/crash-") and r.get("occurrences") == 2)
    assert a["origin"] == "crash" and a["state"] == "drafted"
    text = Path(a["file"]).read_text()
    assert 'File "tests/' not in text and "boom_a" in text and "KeyError" in text
    assert leaked(text) == []
    assert crash.noted(proj, OSError("disk full"), "engine") is None      # the machine's trouble, not ergostat's
    assert len(record.stored(proj)) == 2


def test_a_crash_in_check_is_drafted_and_raised(proj, monkeypatch, capsys):
    from ergostat.cli import main, spec_cmds
    from ergostat.reports import crash, record
    crash.forget()

    def broken(*a, **k):
        raise ZeroDivisionError("invoices-pending / 0")
    monkeypatch.setattr(spec_cmds, "check_yaml", broken)
    with pytest.raises(ZeroDivisionError):
        main(["-C", str(proj.model.path.parent), "check"])
    assert "a report is drafted" in capsys.readouterr().err
    (r,) = record.stored(proj).values()
    assert r["origin"] == "crash" and "ZeroDivisionError" in Path(r["file"]).read_text()
    assert "invoices-pending" not in Path(r["file"]).read_text()


def test_mcp_drafts_and_lists(proj, offline):
    from ergostat.mcp import TOOLS, Server
    assert any(t["name"] == "report_upstream" for t in TOOLS)
    s = Server(proj.model.path.parent)
    got = json.loads(s.call("report_upstream", {"says": SAYS, "details": DETAILS, "parts": ["stock.invoices-pending"],
                                                "repro": "stocks:\n  invoices-pending: {unit: x}\n"})["content"][0]["text"])
    assert Path(got["file"]).exists() and "Nothing was sent" in got["tell_the_owner"]
    assert leaked(got["text"]) == [] and "Written by the agent" in got["text"]
    listed = json.loads(s.call("report_upstream", {})["content"][0]["text"])
    assert [x["id"] for x in listed] == [got["id"]]


def test_cli_drafts_lists_shows_and_marks(proj, offline, capsys):
    from ergostat.cli import main
    d = str(proj.model.path.parent)
    assert main(["-C", d, "report", "--draft", SAYS, "--details", DETAILS]) == 0
    out = capsys.readouterr().out
    rid = out.split("drafted ", 1)[1].split(":", 1)[0].strip().replace("\x1b[1m", "").replace("\x1b[0m", "")
    assert main(["-C", d, "report"]) == 0
    assert "drafted" in capsys.readouterr().out
    assert main(["-C", d, "report", rid]) == 0
    shown = capsys.readouterr().out
    assert "Title: " in shown and "github.com/danroblewis/ergostat/issues/new?title=" in shown
    assert "Scrubbed (kept here" in shown and "falcon-settler" in shown     # the log shows the owner the originals
    assert leaked(shown.split("Title: ", 1)[1].split("Scrubbed (kept here", 1)[0]) == []   # the text to paste holds none
    assert main(["-C", d, "report", rid, "--reviewed"]) == 0
    assert main(["-C", d, "report", rid, "--done", "--note", "filed"]) == 0
    assert main(["-C", d, "report", rid, "--dismiss"]) == 2                  # submitted is the end
    from ergostat.reports import record
    r = record.get(proj, rid)
    assert r["state"] == "submitted" and [m["to"] for m in r["moves"]] == ["drafted", "reviewed", "submitted"]
    assert main(["-C", d, "report", "--draft", "another"]) == 0
    rid2 = record.short(sorted(record.stored(proj).values(), key=lambda x: x["time"])[-1]["id"])
    assert main(["-C", d, "report", rid2, "--dismiss"]) == 0
    assert record.get(proj, rid2)["state"] == "dismissed"
    assert main(["-C", d, "report", "--draft", "  "]) == 2


def test_a_drafted_report_needs_attention_in_one_line(proj):
    from ergostat import state as st
    from ergostat.reports import record
    for w in ("one thing", "another thing"):
        record.draft(proj, w)
    att = [a for a in st.attention(st.snapshot(proj), True, proj.model) if a["what"] == "reports upstream"]
    assert len(att) == 1 and "2 drafted" in att[0]["says"]
    for r in record.stored(proj).values():
        record.mark(proj, r["id"], "dismissed")
    assert not [a for a in st.attention(st.snapshot(proj), True, proj.model) if a["what"] == "reports upstream"]


def test_the_kind_is_built_in():
    from ergostat.reports import REPORT, STATES
    assert STATES == ["drafted", "reviewed", "submitted", "dismissed"]
    import ergostat.spec.compile  # noqa: F401
    assert REPORT == "ergostat.report"


def test_the_kind_is_in_every_model(proj):
    assert "ergostat.report" in proj.model.spec.items


class _Run:
    """A block's run, as a report line meets it."""
    def __init__(self, p, name):
        self.e = type("E", (), {"p": p})()
        self.b = type("B", (), {"name": name})()
        self.counts, self.refused = {}, []

    def flush(self):
        pass

    def refuse(self, line, why):
        self.refused.append(why)


def test_a_blocks_report_line_is_drafted_once_and_counted(proj, offline):
    from ergostat.reports import lines, record
    run = _Run(proj, "improver")
    lines.take(run, {"report": "a flow's rate cannot read invoices-pending delayed by a parameter"})
    lines.take(run, {"report": {"says": "a flow's rate cannot read invoices-pending delayed by a parameter"}})
    lines.take(run, {"report": {"says": ""}})
    assert len(run.refused) == 1 and run.counts["reports"] == 2
    (r,) = record.stored(proj).values()
    assert r["origin"] == "modelling" and r["by"] == "improver" and r["occurrences"] == 2
    assert "invoices-pending" not in Path(r["file"]).read_text()
