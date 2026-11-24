"""Gates and thresholds scheduled by the operating state (SPEC §12k): an action's gate and act-risk threshold are
chosen by the state and the owner's presence in force, at the request and read again inside the run lock at the act;
an unwritten cell is never looser than normal's; a state that cannot be read is deny, whatever is written."""

import itertools
import textwrap

import pytest

from ergostat import model as mdl
from ergostat import spec as spec_mod
from ergostat.actions import gate, operating, risk
from ergostat.claims import record as claims
from ergostat.spec.ir import Action
from ergostat.store import Project


def model(acts: dict) -> str:
    body = "".join(f"""
          {n}:
            run: "echo {n} >> ran.txt"
            gate: {g}
            in: .
            {"risk: " + r if r else ""}""" for n, (g, r) in acts.items())
    return textwrap.dedent(f"""
        name: t
        actions:{body}
        blocks:
          dev: {{type: program, run: "true", actions: [{", ".join(acts)}], every: 1h}}
    """)


def project(tmp_path, acts) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(model(acts))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [x.message for x in m.problems]
    return Project(m)


def ask(p, tmp_path, name="act"):
    return gate.request(p, p.model.spec, name, {}, {"block": "dev", "run": "r1", "workdir": str(tmp_path)})


def ran(tmp_path) -> list[str]:
    f = tmp_path / "ran.txt"
    return f.read_text().split() if f.exists() else []


def between(monkeypatch, then):
    """Do ``then`` at the run lock's first check (``fenced`` inside ``run_once``), after the request and its approval:
    the step between the approval and the act (lesson-1)."""
    real, calls = gate.fenced, []

    def fenced(p, spec, a):
        calls.append(1)
        if len(calls) == 2:                         # the 1st is the request's own; the 2nd is inside the run lock
            then(p)
        return real(p, spec, a)
    monkeypatch.setattr(gate, "fenced", fenced)


def test_cell_chosen_by_state(tmp_path):
    p = project(tmp_path, {"act": ("{normal: auto, freeze: deny}", None)})
    operating.enter(p, "normal")                    # the owner present
    a = ask(p, tmp_path)
    assert a["state"] == "ran" and ran(tmp_path) == ["act"]
    assert a["operating"]["state"] == "normal" and a["operating"]["presence"] == "present"
    assert a["operating"]["column"] == "normal" and isinstance(a["operating"]["seq"], int) and a["operating"]["why"]
    operating.enter(p, "freeze", note="release week")
    b = ask(p, tmp_path)
    assert b["state"] == "denied" and b["denied_by"] == "gate" and b["gate"] == "deny" and ran(tmp_path) == ["act"]
    assert b["operating"]["state"] == "freeze" and "under freeze" in b["note"]


@pytest.mark.parametrize("how", ["auto, approved by the gate", "approve, approved by the owner"])
def test_freeze_entered_between_approval_and_act_denies(tmp_path, monkeypatch, how):
    base = how.split(",")[0]
    p = project(tmp_path, {"act": (base, None)})
    operating.enter(p, "normal")
    between(monkeypatch, lambda p: operating.enter(p, "freeze"))
    a = ask(p, tmp_path)
    if base == "approve":
        assert a["state"] == "requested" and a["operating"]["state"] == "normal"
        a = gate.approve(p, p.model.spec, a["id"])
    assert ran(tmp_path) == [], "the command never runs"
    at = a["risk_at_act"]
    assert at["operating"]["state"] == "freeze" and at["operating"]["column"] == "freeze"
    if base == "approve":                           # freeze's default for approve is deny: the owner's approval undone
        assert a["state"] == "denied" and a["denied_by"] == "gate" and at["effective"] == "deny"
    else:                                           # freeze's default for auto is approve: held for the owner again
        assert a["state"] == "requested" and a["approved_by"] is None and at["effective"] == "approve"


def test_unwritten_cells_never_looser():
    strict = risk.ORDER.index
    for base in risk.ORDER:
        cells = risk.schedule(base)
        assert set(cells) == set(risk.COLUMNS) and cells["normal"] == base
        for col in risk.COLUMNS:
            assert strict(cells[col]) >= strict(base), (base, col)
        assert strict(cells["freeze"]) == min(strict(base) + 1, 2) and cells["incident"] == "deny"
    # and through the state read, every state and presence, named by the lease or not, for a plain gate and a plain T
    for base, st, pr, named in itertools.product(risk.ORDER, operating.STATES, ("present", "away"), (True, False)):
        a = Action("a", "x", gate=base, severity=3, threshold=8.0, gates=risk.schedule(base),
                   thresholds=dict.fromkeys(risk.COLUMNS, 8.0))
        o = operating.Operating(st, pr, 1, "", actions=("a",) if named else ())
        g, t, _ = risk.cell(a, o)
        assert strict(g) >= strict(base) and t <= 8.0, (base, st, pr, named)
    # as compiled: every unwritten cell of a gate map, and every unwritten threshold, takes at least normal's
    acts = {f"a{i}": (f"{{normal: {b}}}", "{severity: 2, threshold: {normal: 6}}") for i, b in enumerate(risk.ORDER)}
    p = project_spec(acts)
    for i, b in enumerate(risk.ORDER):
        x = p.actions[f"a{i}"]
        assert x.gate == b and all(strict(x.gates[c]) >= strict(b) for c in risk.COLUMNS)
        assert x.thresholds == dict.fromkeys(risk.COLUMNS, 6.0) and x.threshold == 6.0


def project_spec(acts):
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    (d / "ergostat.yaml").write_text(model(acts))
    compiled, problems = spec_mod.read(d / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], [x.message for x in problems]
    return compiled


def test_unsure_state_is_deny_whatever_is_written(tmp_path, monkeypatch):
    p = project(tmp_path, {"act": ("{normal: auto, incident: auto}", None)})
    operating.enter(p, "incident")                  # an incident the owner entered: the written cell, as written
    assert ask(p, tmp_path)["state"] == "ran" and ran(tmp_path) == ["act"]

    def broken(*a, **k):
        raise OSError("record gone")
    monkeypatch.setattr(operating, "fold", broken)  # read() catches it: incident, and unsure
    a = ask(p, tmp_path)
    assert a["state"] == "denied" and a["operating"]["column"] == "unsure" and ran(tmp_path) == ["act"]
    monkeypatch.setattr(operating, "read", broken)  # the read itself raises
    b = ask(p, tmp_path)
    assert b["state"] == "denied" and b["operating"]["state"] == "incident" and ran(tmp_path) == ["act"]
    for st in ("holiday", "normal"):                # a state name not known, or unsure: never normal's column
        o = operating.Operating(st, "present", 1, "", unsure=st == "normal")
        written = {**risk.schedule("auto"), "incident": "auto"}
        assert risk.cell(Action("a", "x", gate="auto", gates=written), o)[0] == "deny"


def test_unreadable_state_at_the_act_denies(tmp_path, monkeypatch):
    p = project(tmp_path, {"act": ("{normal: approve, incident: auto}", None)})
    operating.enter(p, "normal")

    def broken(*a, **k):
        raise OSError("record gone")
    between(monkeypatch, lambda p: monkeypatch.setattr(operating, "read", broken))
    a = ask(p, tmp_path)
    assert a["state"] == "requested"
    a = gate.approve(p, p.model.spec, a["id"])
    assert a["state"] == "denied" and a["risk_at_act"]["operating"]["column"] == "unsure" and ran(tmp_path) == []


def test_maintenance_opens_only_named_actions(tmp_path, monkeypatch):
    p = project(tmp_path, {"named": ("{normal: approve, maintenance: auto}", None),
                           "other": ("{normal: approve, maintenance: auto, away: deny}", None)})
    operating.enter(p, "maintenance", lease=3600, actions=["named"])
    a, b = ask(p, tmp_path, "named"), ask(p, tmp_path, "other")
    assert a["state"] == "ran" and a["operating"]["column"] == "maintenance"
    assert b["state"] == "requested" and b["operating"]["column"] == "normal" and b["gate"] == "approve"
    assert ran(tmp_path) == ["named"]
    monkeypatch.setattr(operating, "presence", lambda *a: ("away", "test"))
    c, d = ask(p, tmp_path, "named"), ask(p, tmp_path, "other")
    assert c["state"] == "ran" and c["operating"]["column"] == "maintenance"
    assert d["state"] == "denied" and d["operating"]["column"] == "away" and ran(tmp_path) == ["named", "named"]


def test_threshold_by_state_steps_the_gate(tmp_path):
    p = project(tmp_path, {"act": ("auto", "{severity: 3, threshold: {normal: 8, away: 4}}")})
    c = claims.made(p, p.model.spec, "dev", {"says": "did it"}, run="r0", n=0)
    claims.verdict(p, c, "verified", {}, "test")    # c = 0, and never run: n = 1, so the score is 3 × 1 × 2 = 6
    a = ask(p, tmp_path)                            # no event from the owner: away, T 4
    assert a["operating"]["presence"] == "away" and a["risk"]["score"] == 6.0 and a["risk"]["threshold"] == 4.0
    assert a["state"] == "requested" and a["risk"]["gate"] == "approve" and ran(tmp_path) == []
    operating.enter(p, "normal")                    # the owner present: normal, T 8
    b = ask(p, tmp_path)
    assert b["risk"]["score"] == 6.0 and b["risk"]["threshold"] == 8.0 and b["state"] == "ran" and ran(tmp_path)


def test_bad_gate_map_refused(tmp_path):
    lines = ["name: t", "actions:",
             "  k:", "    run: x", "    gate:", "      normal: auto", "      holiday: deny",
             "  v:", "    run: x", "    gate:", "      normal: auto", "      freeze: never",
             "  t:", "    run: x", "    risk:", "      severity: 2", "      threshold:", "        away: 51",
             "  ok:", "    run: x", "    gate: {normal: auto, away: approve}", "    risk: {severity: 2, threshold: {away: 3}}"]
    (tmp_path / "ergostat.yaml").write_text("\n".join(lines) + "\n")
    compiled, problems = spec_mod.read(tmp_path / "ergostat.yaml")
    errs = [x for x in problems if x.level == "error"]
    for name, line in (("k", 7), ("v", 12), ("t", 18)):
        hit = [x for x in errs if f"action {name}." in x.message]
        assert len(hit) == 1 and hit[0].code == "bad-value" and hit[0].where.line == line, (name, hit)
    assert len(errs) == 3, [x.message for x in errs]
    ok = compiled.actions["ok"]
    assert ok.gates["away"] == "approve" and ok.gates["freeze"] == "approve" and ok.thresholds["away"] == 3.0
    assert compiled.actions["v"].gates["freeze"] == "approve"     # the refused cell left unwritten: its default


@pytest.mark.parametrize("how", ["an entered incident", "an unreadable record"])
def test_an_auto_notify_channel_is_not_scheduled(tmp_path, monkeypatch, how):
    """A notify channel's action (no cells compiled from ``actions:``) keeps its gate as written whatever the state,
    so what arises during an incident or an unreadable record is sent, not denied and then counted as told."""
    import time

    from ergostat.inbox import deliver

    from .test_inbox import project as inbox_project
    from .test_inbox import sent
    p, _ = inbox_project(tmp_path)
    spec, now = p.model.spec, time.time()
    assert not spec.actions["notify.log"].gates and spec.actions["notify.log"].gate == "auto"
    operating.enter(p, "incident")
    if how == "an unreadable record":
        def broken(*a, **k):
            raise OSError("record gone")
        monkeypatch.setattr(operating, "read", broken)
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3}, at=now - 300)
    assert deliver.sweep(p, spec, now) == 1
    told = p.events.query(n=None, type=deliver.SENT)
    assert len(told) == 1 and told[0]["data"]["state"] == "ran" and told[0]["data"]["entries"][0] in sent(tmp_path)
    from ergostat.actions import record
    assert record.get(p, told[0]["data"]["action"])["operating"]["column"] == "unscheduled"


def test_keyed_program_ask_takes_the_looser_cell_once_in_force(tmp_path):
    """A gate denial is reused for the same keyed ask only while the cell in force is still deny (program.known)."""
    from ergostat.actions import program
    p = project(tmp_path, {"act": ("{normal: deny, maintenance: auto}", None)})
    operating.enter(p, "normal")

    def keyed(run):
        c = {"block": "dev", "run": run, "item": None, "workdir": str(tmp_path), "actions": ["act"]}
        return program.ask(p, p.model.spec, c, "act", {}, key="day-1")
    a = keyed("r1")
    assert a["state"] == "denied" and a["denied_by"] == "gate" and ran(tmp_path) == []
    assert keyed("r2")["id"] == a["id"]             # still deny in force: the earlier denial stands
    operating.enter(p, "maintenance", lease=3600, actions=["act"])
    b = keyed("r3")
    assert b["id"] != a["id"] and b["state"] == "ran" and b["operating"]["column"] == "maintenance"
    assert ran(tmp_path) == ["act"]
