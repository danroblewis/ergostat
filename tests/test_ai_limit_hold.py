"""A provider usage-limit stop is a pause, not a failure (dev/bin/aihold.py, dev/records/an-ai-usage-limit-stop-pauses.md):
the session's reset time read, one factory-wide AI hold recorded till then, the run given back uncounted, no AI-role
lease taken while it stands, the queue running on, and the hold lifting by itself at the reset."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from types import SimpleNamespace

from ergostat.leases import ENDED, TAKEN
from ergostat.leases import fold as lease_fold
from ergostat.spec import read
from tests.test_factory import BIN, ROOT, Factory, Slots, module, ready


def reset_text(t: float) -> str:
    """The provider's message, its reset at ``t`` (to the minute, in UTC)."""
    g = time.gmtime(t)
    return f"You've hit your weekly limit · resets {time.strftime('%b', g)} {g.tm_mday}, " \
           f"{(g.tm_hour % 12) or 12}:{g.tm_min:02d}{'pm' if g.tm_hour >= 12 else 'am'} (UTC)"


def nacks(lines: list[dict]) -> list[dict]:
    return [x["nack"] for x in lines if "nack" in x]


def hold_of(f: Factory) -> dict:
    return json.loads((f.model / "run" / "ai_hold.json").read_text())


def sensor(f: Factory) -> str:
    r = subprocess.run([sys.executable, str(BIN / "aihold.py"), "held"], cwd=f.model, env=f.env, capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def patched(f: Factory, program: str, gid: str, patch: str, lease: dict | None = None) -> tuple[list[str], list[dict]]:
    """``program``'s main run in one process with ``patch`` applied first (as tests/test_factory.py's queue_with)."""
    it = f.item(gid)
    given = {"trigger": "item", "item": it, "lease": {"fence": 1, "back": it["state"], **(lease or {})}}
    code = f"import sys; sys.path[:0] = [{str(BIN)!r}]; import fac, {program}\n{patch}\nsys.exit({program}.main())"
    r = subprocess.run([sys.executable, "-c", code], input=json.dumps(given), cwd=f.model, capture_output=True,
                       text=True, timeout=120, env={**f.env, "ERGOSTAT_ITEM": gid, "ERGOSTAT_LEASE": "1"})
    assert r.returncode == 0, r.stderr
    f.stderr = r.stderr
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    return f.fold(lines, gid), lines


def folded(nacked: list[dict], at: float, most: int = 2) -> SimpleNamespace:
    """An item's lease through ergostat's own fold: taken and ended with each nack in turn (``at`` the end's time)."""
    it = SimpleNamespace(id="gap/x", state="ready", fields={}, changes=[])
    for n, nk in enumerate(nacked, 1):
        for e in ({"type": TAKEN, "time": at - 1, "data": {"run": f"r{n}", "fence": n, "ttl": 60, "max": most}},
                  {"type": ENDED, "time": at, "data": {"run": f"r{n}", "fence": n, "how": "nack", "why": nk["why"],
                                                       "count": nk.get("count", True), "after": nk.get("after_s")}}):
            to, refused = lease_fold.apply(it, e, None)
            assert refused is None, refused
            it.state = to or it.state
    return it


def aihold_module(monkeypatch):
    """aihold as the programs import it (fac beside it), in the current folder."""
    monkeypatch.setitem(sys.modules, "fac", module("fac"))
    return module("aihold")


def seconds(after: str) -> float:
    from ergostat.durations import parse_duration
    return parse_duration(after)


def test_a_weekly_limit_stop_holds_ai_leases_until_the_reset(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    reset = (int(time.time()) // 60 + 2 * 24 * 60) * 60                      # two days on, to the minute
    said, lines = f.run("implement.py", gid, FACTORY_STANDIN_IMPLEMENTOR=reset_text(reset))
    assert hold_of(f)["until"] == reset and hold_of(f)["readable"] is True   # the reset read from the message
    assert [n["count"] for n in nacks(lines)] == [False] and "gap.built" not in said
    assert abs(time.time() + seconds(nacks(lines)[0]["after"]) - reset) < 60  # put off till the reset
    assert sensor(f) == "1"
    for program in ("implement.py", "review.py", "research.py", "plan.py"):  # no AI role starts while it stands
        said, lines = f.run(program, gid)
        assert said == [] and [n["count"] for n in nacks(lines)] == [False], program
        assert "the AI is held" in nacks(lines)[0]["why"]
    spec, _ = read(ROOT / "ergostat.yaml")                                    # and the engine's gates take no lease
    for when in ("implement-when", "review-when", "research-when", "ai-stopped"):
        b = spec.blocks[when]
        assert "held" in b.params["expr"] and str(b.inputs["held"]) == "goal.ai-not-held.off", when
    for when in ("plan-when", "plan-review-when"):                           # planning's through one read (ai-stopped)
        b = spec.blocks[when]
        assert "(1 - stop)" in b.params["expr"] and str(b.inputs["stop"]) == "block.ai-stopped", when
    assert spec.blocks["ai-stopped"].params["expr"] == "max(over, held)"
    g = spec.goals["ai-not-held"]
    assert str(g.of) == "auxiliary.ai-held" and g.on_stale == "off"          # a hold not read closes them


def test_a_limit_stop_is_not_an_attempt_and_never_parks(tmp_path, monkeypatch):
    f = Factory(tmp_path)
    gid = ready(f)
    last = {"attempt": 2, "attempts": 1, "max": 2}                           # its last attempt: a failure would park it
    said, lines = f.run("implement.py", gid, lease=last, FACTORY_STANDIN_IMPLEMENTOR=reset_text(time.time() + 3600))
    assert "gap.parked" not in said and f.item(gid)["state"] != "parked"
    assert not {"build_failures", "build_hours"} & set(f.item(gid)["fields"])  # nothing toward the kill rule
    assert [n["count"] for n in nacks(lines)] == [False]
    # a session that fails with the message in Claude Code's own output (no result at all), on its last attempt too
    (f.model / "run" / "ai_hold.json").unlink()
    boom = ("def boom(*a, **k):\n    raise RuntimeError(\"the implementor session answered no result (exit 1): "
            "You've hit your weekly limit · resets 11pm (UTC)\")\nfac.standin = boom")
    said, lines = patched(f, "implement", gid, boom, last)
    assert "gap.parked" not in said and [n["count"] for n in nacks(lines)] == [False]
    assert hold_of(f)["readable"] is True
    # the reviewer's stop the same; and through ergostat's own lease fold, never an attempt nor a dead letter
    (f.model / "run" / "ai_hold.json").unlink()
    assert f.run("implement.py", gid)[0][-1] == "gap.built"
    said, lines = patched(f, "review", gid, boom.replace("implementor", "reviewer"), last)
    assert "gap.parked" not in said and f.item(gid)["state"] != "parked", lines
    nk = nacks(lines)[0]
    it = folded([nk | {"after_s": seconds(nk["after"])}] * 3, time.time())
    assert it.state == "ready" and it.fields["lease"]["attempts"] == 0 and "dead" not in it.fields["lease"]
    # nor a review round: after the reset the real review is round 1, a first pass
    (f.model / "run" / "ai_hold.json").unlink()
    said, lines = f.run("review.py", gid, FACTORY_STANDIN_REVIEWER=reset_text(time.time() + 3600))
    assert "gap.review-started" in said and [n["count"] for n in nacks(lines)] == [False]
    assert int(f.item(gid)["fields"].get("reviews_n") or 0) == 0      # the boom stop and this one, both taken back
    (f.model / "run" / "ai_hold.json").unlink()
    said, lines = f.run("review.py", gid)
    approved = next(x["data"] for x in lines if x.get("event") == "gap.approved")
    assert approved["first_pass"] is True and f.item(gid)["fields"]["reviews_n"] == 1
    assert next(x["data"] for x in lines if x.get("event") == "review.written")["round"] == 1
    # a reviewer's verdict that only quotes the message is not a stop
    aihold = aihold_module(monkeypatch)
    assert not aihold.limited("The branch reads 'You've hit your weekly limit · resets 3pm'.")
    assert aihold.limited("You've hit your weekly limit · resets 3pm")


def test_an_unreadable_reset_time_holds(tmp_path, monkeypatch):
    f = Factory(tmp_path)
    gid = ready(f)
    began = time.time()
    said, lines = f.run("implement.py", gid, FACTORY_STANDIN_IMPLEMENTOR="You've hit your weekly limit · resets soon")
    h = hold_of(f)
    assert h["readable"] is False and began + 3600 <= h["until"] <= time.time() + 3600   # held, never run on
    assert "cannot be read" in f.stderr and "cannot be read" in nacks(lines)[0]["why"]      # and said so
    assert nacks(lines)[0]["count"] is False and sensor(f) == "1"
    aihold = aihold_module(monkeypatch)
    for text in ("You've hit your weekly limit · resets 3pm (Nowhere/Atlantis)",   # an unknown zone
                 "You've hit your weekly limit · resets Feb 31, 3pm (UTC)",       # no such day
                 "You've hit your weekly limit · resets 3",                       # no am/pm, no minutes
                 "You've hit your weekly limit"):
        assert aihold.reset_at(text, began) is None, text
    (f.model / "run" / "ai_hold.json").write_text("{not json")             # a hold file that cannot be read holds
    assert sensor(f) == "1"
    said, lines = f.run("review.py", gid)
    assert said == [] and "cannot be read" in nacks(lines)[0]["why"]


def test_the_queue_runs_while_ai_is_held(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    f.run("implement.py", gid)
    f.run("review.py", gid)
    (f.model / "run" / "ai_hold.json").write_text(json.dumps({"until": time.time() + 86400, "why": "the limit"}))
    assert sensor(f) == "1"
    said, _ = f.run("queue.py", gid)                                         # the merge queue and its suites go on
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"]
    spec, _ = read(ROOT / "ergostat.yaml")
    for b in ("merge-queue", "flake-triage"):
        ins = spec.blocks[b].inputs.values() if spec.blocks[b].inputs else []
        assert "goal.ai-not-held.off" not in {str(x) for x in ins}, b


def test_drain_nacks_are_not_attempts(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    (f.model / "run" / "drain.json").write_text(json.dumps({"sha": "a" * 40, "since": time.time()}))
    said, lines = f.run("implement.py", gid)
    assert said == [] and [n["count"] for n in nacks(lines)] == [False] and "drains" in nacks(lines)[0]["why"]
    item = {"id": gid, "fields": {"lease": {"fence": 1, "holder": "r1"}}}  # a run under way given back by the drain
    code = (f"import sys, json; sys.path[:0] = [{str(BIN)!r}]; import drain; "
            f"print(json.dumps(drain.give_back([json.loads(sys.argv[1])], 'a' * 40)))")
    r = subprocess.run([sys.executable, "-c", code, json.dumps(item)], cwd=f.model, env=f.env, capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stderr
    assert [n["count"] for n in f.db()["nacks"]] == [False]
    nk = nacks(lines)[0]                                                    # never an attempt in ergostat's fold
    it = folded([nk | {"after_s": seconds(nk["after"])}] * 3, time.time())
    assert it.fields["lease"]["attempts"] == 0 and it.state == "ready"
    counted = folded([{"why": "a real failure"}] * 2, time.time())          # (what a counted one does: dead)
    assert counted.state == "dead"


def test_the_hold_lifts_at_the_reset(tmp_path, monkeypatch, capsys):
    f = Factory(tmp_path)
    monkeypatch.chdir(f.model)
    aihold = aihold_module(monkeypatch)
    cfg = {"paths": {"run": str(f.model / "run")}}
    now = 1_800_000_000.0                                                    # 2027-01-15 08:00 UTC
    h = aihold.record(cfg, "You've hit your weekly limit · resets Jan 17, 3pm (UTC)", now)
    assert h["until"] == 1_800_000_000 + 2 * 86400 + 7 * 3600
    assert aihold.record(cfg, "You've hit your limit · resets 9am (UTC)", now)["until"] == h["until"]   # never shortened
    assert aihold.held(cfg, h["until"] - 1) and aihold.held(cfg, h["until"]) is None   # lifts by itself at the reset
    # two items held at different moments are both due again at the reset, so the block's own order takes them
    due = []
    for t in (now, now + 5000.5):
        capsys.readouterr()
        aihold.give_back(h, t)
        nk = json.loads(capsys.readouterr().out)["nack"]
        due.append(folded([nk | {"after_s": seconds(nk["after"])}], t).fields["lease"]["not_before"])
    assert due[0] == h["until"] and h["until"] <= due[1] < h["until"] + 1
    # the real engine's dispatch: the one taken in the sensor's lag given back till the reset, the gate shut while the
    # hold stands, and at the reset the gaps taken again by rank, the first not counted an attempt
    (tmp_path / "engine").mkdir()
    s = Slots(Factory(tmp_path / "engine"), monkeypatch, "implementor", "implement.py", "gap.built")
    try:
        reset = 600.0
        for gid, rank in (("gap/r2", 2), ("gap/r1", 1)):
            s.gap(gid, "gap.defined", rank=rank)
        s.full = lambda: s.at < reset
        capsys.readouterr()
        aihold.give_back({"until": s.t0 + reset, "why": "the limit"}, s.t0)
        nk = json.loads(capsys.readouterr().out)["nack"]
        s.nack = nk | {"after": seconds(nk["after"])}
        s.tick(0)                                                            # open on the last reading: given back
        s.gate = s.gate_of(held=1)                                           # the hold read: shut
        for t in range(5, int(reset), 5):
            s.tick(t)
        s.gate = s.gate_of()                                                 # the reset: open by itself
        for t in range(int(reset), int(reset) + 30, 5):
            s.tick(t)
        assert s.taken[0] == (0, "gap/r1", "given back") and all(t >= reset for t, _, _ in s.taken[1:])
        assert [g for _, g, how in s.taken if how == "ran"] == ["gap/r1", "gap/r2"]
        assert s.lease_of("gap/r1")["attempts"] == 0
    finally:
        s.close()
    gid = ready(f)                                                           # past the reset: built as ever
    (f.model / "run" / "ai_hold.json").write_text(json.dumps({"until": time.time() - 1, "why": "the limit"}))
    assert sensor(f) == "0"
    assert f.run("implement.py", gid)[0] == ["gap.started", "gap.built"]
