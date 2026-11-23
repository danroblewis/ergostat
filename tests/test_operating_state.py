"""The operating state (normal, maintenance, freeze, incident) and the owner's presence (present, away), folded from the
record in seq order (SPEC §12k, *The operating state*)."""

import json
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import spec as spec_mod
from ergostat.actions import operating as ops
from ergostat.cli import main
from ergostat.store import Project

MODEL = """
name: op
actions:
  deploy: {run: "echo deployed", gate: approve}
  restart: {run: "echo restarted", gate: approve}
"""


def _repo(tmp_path, extra: str = ""):
    d = tmp_path / "op"
    d.mkdir(exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL) + textwrap.dedent(extra))
    return d, Project(mdl.load(d))


def _cli(d, capsys, *argv) -> tuple[int, str]:
    rc = main(["-C", str(d), "operating", *argv])
    return rc, capsys.readouterr().out


def test_precedence_incident_over_freeze_over_maintenance(tmp_path, capsys):
    d, p = _repo(tmp_path)
    assert _cli(d, capsys, "--json")[0] == 0
    assert _cli(d, capsys, "maintenance", "--for", "1h", "--actions", "deploy", "--note", "upgrade")[0] == 0
    assert ops.read(p).state == "maintenance"
    assert _cli(d, capsys, "freeze", "--note", "release week")[0] == 0
    o = ops.read(p)
    assert (o.state, o.note) == ("freeze", "release week")
    assert ops.read(p, now=time.time() + 2 * 3600).state == "freeze"     # maintenance ended (lapsed) under freeze
    assert _cli(d, capsys, "incident", "--note", "outage")[0] == 0
    assert ops.read(p).state == "incident"
    assert _cli(d, capsys, "normal")[0] == 0                             # ends the one in force: incident
    assert ops.read(p).state == "freeze"                                 # freeze is ended only by its own act
    assert _cli(d, capsys, "normal")[0] == 0
    o = ops.read(p)
    assert (o.state, o.actions, o.note) == ("maintenance", ("deploy",), "upgrade")   # still within its lease
    assert ops.read(p, now=time.time() + 2 * 3600).state == "normal"
    rc, out = _cli(d, capsys, "normal", "--json")
    assert rc == 0 and json.loads(out)["state"] == "normal"
    assert {e["source"] for e in p.events.query(n=None, type="ergostat.operating.*")} == {"owner"}


def test_order_is_by_seq_not_time(tmp_path):
    _, p = _repo(tmp_path)
    t = 1_000_000.0
    add = lambda st, at, **d: p.events.add(f"ergostat.operating.{st}", item=ops.KIND, source="owner", data=d, at=at)  # noqa: E731
    add("freeze", t, note="a")
    add("incident", t)                                   # the same second
    assert ops.read(p, now=t).state == "incident"
    add("normal", t - 60)                                # a clock set back: still after, by seq
    o = ops.read(p, now=t)
    assert (o.state, o.note) == ("freeze", "a")
    last = add("normal", t - 120)
    o = ops.read(p, now=t)
    assert (o.state, o.seq) == ("normal", last["seq"])


def test_maintenance_lapses_and_is_capped(tmp_path, capsys):
    d, p = _repo(tmp_path)
    rc, out = _cli(d, capsys, "maintenance", "--for", "25h")
    assert rc == 2 and "at most" in out
    assert p.events.query(n=None, type="ergostat.operating.*") == []
    with pytest.raises(ops.OperatingError):
        ops.enter(p, "maintenance", lease=float("inf"))
    assert _cli(d, capsys, "maintenance", "--actions", "nope", "--for", "1h")[0] == 2     # not one of actions:
    assert _cli(d, capsys, "freeze", "--for", "1h")[0] == 2                              # a lease is maintenance's
    assert _cli(d, capsys, "maintenance", "--for", "1h")[0] == 0
    o = ops.read(p)
    assert o.state == "maintenance" and o.until is not None
    later = ops.read(p, now=o.until + 1)
    assert later.state == "normal" and "lapsed" in later.reason and later.seq == o.seq
    e = p.events.add("ergostat.operating.maintenance", item=ops.KIND, source="owner", data={"until": "soon"})
    o = ops.read(p)                                      # an end that is not a number: the strictest case
    assert (o.state, o.seq) == ("incident", e["seq"])


def test_reentry_starts_clean(tmp_path, capsys):
    d, p = _repo(tmp_path)
    assert _cli(d, capsys, "freeze", "--note", "release")[0] == 0
    assert _cli(d, capsys, "normal")[0] == 0
    assert _cli(d, capsys, "freeze")[0] == 0
    o = ops.read(p)
    assert (o.state, o.note) == ("freeze", None)
    ops.enter(p, "maintenance", note="m1", lease=3600, actions=["deploy"])
    ops.enter(p, "maintenance", lease=60)                # entered again: no note, its own end and no actions
    assert ops.read(p).state == "freeze"
    ops.enter(p, "normal")
    o = ops.read(p)
    assert (o.state, o.note, o.actions) == ("maintenance", None, ())
    assert o.until is not None and o.until - time.time() <= 60


def test_unreadable_record_reads_incident_and_away(tmp_path, monkeypatch):
    _, p = _repo(tmp_path)
    ops.enter(p, "normal")

    def broken(*a, **k):
        raise OSError("disk gone")

    monkeypatch.setattr(p.events, "query", broken)
    o = ops.read(p)
    assert (o.state, o.presence, o.seq) == ("incident", "away", None)
    assert "cannot be read" in o.reason and "disk gone" in o.reason


def test_presence_away_after(tmp_path):
    _, p = _repo(tmp_path, "operating: {away-after: 1h}\n")
    assert p.model.spec.away_after == 3600
    assert ops.read(p).presence == "away"                # nothing from the owner yet
    t = 2_000_000.0
    p.events.add("ticket.moved", source="owner", at=t)
    p.events.add("ticket.moved", source="ergostat", at=t + 3000)        # not the owner's
    assert ops.read(p, now=t + 3500).presence == "present"
    o = ops.read(p, now=t + 3700)
    assert o.presence == "away" and "away after 1h" in o.reason
    for bad in ("0s", "8d", "4m", "soon", "9" * 400):
        (tmp_path / "ergostat.yaml").write_text(f"name: op\n\noperating:\n  away-after: {bad}\n")
        _, problems = spec_mod.read(tmp_path / "ergostat.yaml")
        hit = [x for x in problems if x.level == "error" and "operating.away-after" in x.message]
        assert hit and hit[0].code == "bad-value" and hit[0].where.line == 4, bad
    (tmp_path / "ergostat.yaml").write_text("name: op\noperating: {away-after: 7d}\n")
    compiled, problems = spec_mod.read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"] and compiled.away_after == 7 * 86400


def test_setting_a_state_is_refused_on_the_last_good_model(tmp_path, capsys):
    from ergostat.goodmodel import keep
    d, p = _repo(tmp_path)
    assert keep(p) is None
    with open(d / "ergostat.yaml", "a") as f:
        f.write("\nbroken: [\n")
    with pytest.raises(SystemExit) as e:
        main(["-C", str(d), "operating", "freeze", "--note", "x"])
    assert e.value.code == 2 and "acts, so it never runs on the last good model" in capsys.readouterr().err
    assert p.events.query(n=None, type="ergostat.operating.*") == []
