"""The day's AI budget (SPEC §9.9): ``budget:`` compiled and bounded, which runs are charged (an allowlist), the trailing
day's spend folded by run id, failing closed, and ``ergostat.budget.left``."""

import math
import time

import pytest

from ergostat import model as mdl
from ergostat.costs import budget as bg
from ergostat.numbers import measures
from ergostat.spec import read
from ergostat.spec.ir import Agent, Block, Budget, Spec
from ergostat.store import Project

H, D = 3600.0, 86400.0
B = Budget(daily=10.0, max_cost=2.0)
MODEL = "name: here\nstocks:\n  queue: {}\n"


def errors(tmp_path, budget: str | None, local: str | None = None) -> list[str]:
    (tmp_path / "ergostat.yaml").write_text(MODEL + (budget or ""))
    if local is not None:
        (tmp_path / "ergostat.local.yaml").write_text(local)
    spec, problems = read(tmp_path / "ergostat.yaml")
    return [p.message for p in problems if p.level == "error"]


def test_check_budget_keys(tmp_path):
    assert not errors(tmp_path, "budget: {daily: 25, max-cost: 2.5}\n")
    spec, _ = read(tmp_path / "ergostat.yaml")
    assert spec.budget == Budget(25.0, 2.5)
    assert not errors(tmp_path, None) and read(tmp_path / "ergostat.yaml")[0].budget is None   # none: nothing changes
    bad = {
        "budget: {daily: 25, max-cost: 2, cap: 3}\n": "unknown key 'cap'",
        "budget: {daily: 25}\n": "max-cost: is required",
        "budget: {max-cost: 2}\n": "daily: is required",
        "budget: {daily: lots, max-cost: 2}\n": "budget.daily: a number",
        "budget: {daily: true, max-cost: 2}\n": "budget.daily: a number",
        "budget: {daily: 25, max-cost: '2'}\n": "budget.max-cost: a number",
        "budget: {daily: 0, max-cost: 2}\n": "budget.daily: more than 0",
        "budget: {daily: -1, max-cost: 2}\n": "budget.daily: more than 0",
        "budget: {daily: 10001, max-cost: 2}\n": "budget.daily: more than 0 and at most 10000",
        "budget: {daily: .inf, max-cost: 2}\n": "budget.daily: more than 0",
        "budget: {daily: .nan, max-cost: 2}\n": "budget.daily: more than 0",
        "budget: {daily: 25, max-cost: 0}\n": "budget.max-cost: more than 0",
        "budget: {daily: 25, max-cost: 26}\n": "at most budget.daily",
        "budget: {daily: 25, max-cost: .nan}\n": "budget.max-cost: more than 0",
        "budget: [25, 2]\n": "budget: a map",
    }
    for text, said in bad.items():
        got = errors(tmp_path, text)
        assert len(got) == 1 and said in got[0], (text, got)
    assert len(errors(tmp_path, "budget: {daily: x, max-cost: y, z: 1}\n")) == 3      # each its own error
    assert len(errors(tmp_path, "budget:\n")) == 2                                     # written empty: never no budget
    bad_one = [x for x in read(tmp_path / "ergostat.yaml")[1] if x.code == "bad-budget"]
    assert bad_one and all(str(x.where) == "ergostat.yaml:4" for x in bad_one)        # each error says where
    got = errors(tmp_path, "budget: {daily: 25, max-cost: 2}\n", local="budget: {daily: 9000, max-cost: 9000}\n")
    assert len(got) == 1 and "'budget' is not a per-machine setting" in got[0]
    (tmp_path / "ergostat.local.yaml").unlink()
    (tmp_path / "more.yaml").write_text("budget: {daily: 25, max-cost: 2}\n")
    got = errors(tmp_path, "include: more.yaml\n")
    assert len(got) == 1 and "budget: belongs in the main file only" in got[0]
    assert bg.check(25, 2) == [] and len(bg.check(25, 30)) == 1 and len(bg.check(1e9, 1e9)) == 2   # again at run time


def test_free_run_allowlist():
    spec = Spec("m", None, [], agents={k: Agent(k, kind=k if k not in ("bare", "ai-kit") else None)
                                       for k in ("program", "person", "decision", "rule", "ai", "narrow-ai", "bare")})
    spec.agents["ai-kit"] = Agent("ai-kit", kind="ai")
    for k in ("program", "person", "decision", "rule"):
        assert bg.free(spec, Block(name="b", type="program", agent=k)), k
    assert not bg.free(spec, Block(name="b", type="program", agent=None))          # no agent
    assert not bg.free(spec, Block(name="b", type="program", agent="nobody"))      # not declared
    assert not bg.free(spec, Block(name="b", type="program", agent="bare"))        # no kind
    for k in ("ai", "narrow-ai", "ai-kit"):
        assert not bg.free(spec, Block(name="b", type="program", agent=k)), k      # a kind not on the allowlist
    assert not bg.free(spec, Block(name="b", type="ai", agent="program"))          # an ai block, whatever its agent
    assert not bg.free(spec, Block(name="b", type="script", agent="unknown-kind"))


def test_free_block_runs_fold_to_nothing(p):
    """The fold applies the allowlist: a program block's runs (ends with no cost) are charged 0, an ai block's and an
    unknown block's max-cost; with no spec every run is charged."""
    now = time.time()
    spec = Spec("m", None, [], agents={"tool": Agent("tool", kind="program"), "claude": Agent("claude", kind="ai")},
                blocks={"tidy": Block(name="tidy", type="program", agent="tool"),
                        "think": Block(name="think", type="ai", agent="claude")})
    for i, name in enumerate(("tidy", "think", "gone")):
        p.events.add("agent.started", item=name, source="ergostat", at=now - 2 * H, id=f"r{i}", data={})
        p.events.add("agent.ran", item=name, source="ergostat", at=now - H, causedby=f"r{i}", data={})
    p.events.add("ergostat.lease.taken", item="ticket/1", source="ergostat", at=now - H,
                 data={"run": "leased", "block": "tidy", "fence": 1, "ttl": 60})       # a free block's lease: no reserve
    f = bg.fold(p, B, now, spec)
    assert f["runs"] == {"r1": 2.0, "r2": 2.0} and (f["spent"], f["reserved"]) == (4.0, 0.0)
    assert bg.fold(p, B, now)["runs"] == {"r0": 2.0, "r1": 2.0, "r2": 2.0, "leased": 2.0}   # no spec: all charged


@pytest.fixture
def p(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(MODEL + "budget: {daily: 10, max-cost: 2}\n")
    return Project(mdl.load(tmp_path))


def take(p, run, at, reserve=1.0, item="ticket/1"):
    p.events.add("ergostat.lease.taken", item=item, source="ergostat", at=at,
                 data={"item": item, "run": run, "block": "w", "fence": 1, "ttl": 60, "reserve": reserve})


def end(p, run, at, cost="none", type="agent.ran"):
    data = {} if cost == "none" else {"cost_usd": cost}
    if type == "budget.closed":
        p.events.add(type, item="w", source="ergostat", at=at, data={"run": run, **data})
    else:
        p.events.add(type, item="w", source="ergostat", at=at, causedby=run, data=data)


def test_reserve_held_until_end_with_cost(p):
    now = time.time()
    take(p, "r1", now - 3 * H, reserve=1.5)
    p.events.add("ergostat.lease.expired", item="ticket/1", source="ergostat", at=now - 2 * H, data={"run": "r1"})
    f = bg.fold(p, B, now)
    assert (f["spent"], f["reserved"], f["runs"]) == (0.0, 1.5, {"r1": 1.5})   # expired, no end: still its reserve
    end(p, "r1", now - H, 0.1)
    f = bg.fold(p, B, now)
    assert (f["spent"], f["reserved"], f["runs"]) == (0.1, 0.0, {"r1": 0.1})
    end(p, "r2", now - H, 0.0, type="agent.failed")                  # a known 0 is 0
    end(p, "r3", now - H, {"x": 1})                                   # not a number, nothing reserved: max-cost
    p.events.add("agent.ran", item="w", source="ergostat", at=now - H, causedby="r4", data={"ai": {"cost_usd": 0.25}})
    f = bg.fold(p, B, now)
    assert f["runs"]["r2"] == 0.0 and f["runs"]["r3"] == 2.0 and f["runs"]["r4"] == 0.25
    take(p, "r5", now - H, reserve=1.75, item="ticket/5")
    for src in ("w", "record", "intake"):                             # forged by a block, `ergostat record`, a push
        p.events.add("budget.closed", item="w", source=src, at=now - 0.5 * H, data={"run": "r5", "cost_usd": 0})
    f = bg.fold(p, B, now)
    assert f["runs"]["r5"] == 1.75 and f["reserved"] == 1.75          # still held: nothing released


def test_forged_close_as_ergostat_is_refused(p, tmp_path, monkeypatch):
    """A run may not release a reserve by saying it is ergostat: budget.* is ergostat's own type, refused by `ergostat
    event --add` (and so the engine's calls socket, which records through the envelope), by a push and by block output."""
    from ergostat.cli import main
    from ergostat.intake import envelope
    from ergostat.runner import OWN_TYPES
    now = time.time()
    take(p, "r9", now - H, reserve=1.75)
    monkeypatch.delenv("ERGOSTAT_SOCKET", raising=False)
    monkeypatch.setenv("ERGOSTAT_RUN", "r9")
    forged = '{"run": "r9", "cost_usd": 0}'
    assert main(["-C", str(tmp_path), "event", "--add", "budget.closed", "--as", "ergostat", "--data", forged]) == 2
    with pytest.raises(envelope.Refused, match="not ergostat's own"):
        envelope.record(p, [{"event": "budget.closed", "source": "ergostat", "data": {"run": "r9", "cost_usd": 0}}])
    assert "budget." in OWN_TYPES                                         # a block's output is refused by the same list
    assert not p.events.query(n=None, type="budget.closed")
    f = bg.fold(p, B, now)
    assert f["runs"]["r9"] == 1.75 and f["reserved"] == 1.75          # still held: nothing released


def test_malformed_cost_counts_unknown(p):
    now = time.time()
    for i, c in enumerate(["none", math.nan, -5, math.inf, -math.inf, "0.1", True]):
        take(p, f"lease-{i}", now - 2 * H, reserve=1.25, item=f"ticket/{i}")
        end(p, f"lease-{i}", now - H, c)
        p.events.add("agent.started", item="w", source="ergostat", at=now - 2 * H, id=f"free-{i}", data={})   # reserved 0
        end(p, f"free-{i}", now - H, c, type="budget.closed" if i % 2 else "agent.ran")
    p.events.add("agent.started", item="w", source="ergostat", at=now - 2 * H, id="bad-reserve", data={"reserve": math.nan})
    runs = bg.fold(p, B, now)["runs"]
    for i in range(7):
        assert runs[f"lease-{i}"] == 1.25, i                          # its reserve
        assert runs[f"free-{i}"] == 2.0, i                            # nothing reserved: max-cost
    assert runs["bad-reserve"] == 2.0                                 # a malformed reserve holds max-cost


def test_window_by_run_id(p):
    now = time.time()
    take(p, "old", now - 3 * D)
    end(p, "old", now - 2 * D, 0.5)                                   # ended more than a day ago: 0
    take(p, "going", now - 2 * D, reserve=1.75)                       # started 2 d ago, no end: its reserve
    take(p, "long", now - 8 * D, reserve=1.0)                         # start before the 7 days read
    end(p, "long", now - H, 0.3)
    f = bg.fold(p, B, now)
    assert f["runs"] == {"old": 0.0, "going": 1.75, "long": 0.3}
    assert (f["spent"], f["reserved"]) == (0.3, 1.75)
    end(p, "several", now - 2 * H, 0.2)
    end(p, "several", now - H, 0.9)
    end(p, "several", now - 30 * H, 5.0)                              # outside the day: counts 0
    assert bg.fold(p, B, now)["runs"]["several"] == 0.9               # the largest charge


def test_retaken_item_keeps_old_reserve(p):
    now = time.time()
    take(p, "first", now - 3 * H, reserve=1.0, item="ticket/9")
    p.events.add("ergostat.lease.expired", item="ticket/9", source="ergostat", at=now - 2 * H, data={"run": "first"})
    take(p, "second", now - H, reserve=1.5, item="ticket/9")          # the same item, retaken: a new run
    f = bg.fold(p, B, now)
    assert f["runs"] == {"first": 1.0, "second": 1.5} and f["reserved"] == 2.5
    end(p, "second", now - 0.5 * H, 0.2)
    f = bg.fold(p, B, now)
    assert f["runs"] == {"first": 1.0, "second": 0.2} and (f["spent"], f["reserved"]) == (0.2, 1.0)


def test_budget_left_fails_closed(p, tmp_path, monkeypatch):
    now = time.time()
    take(p, "a", now - 2 * H, reserve=1.5, item="ticket/a")          # held: 1.5
    take(p, "b", now - 2 * H, reserve=1.0, item="ticket/b")
    end(p, "b", now - H, 0.4)                                          # spent: 0.4
    end(p, "c", now - H, math.nan)                                     # no start: max-cost, 2
    take(p, "d", now - 3 * D, item="ticket/d")
    end(p, "d", now - 2 * D, 3.0)                                      # out of the day: 0
    assert measures.measure(p, "ergostat.budget.left") == pytest.approx(10 - 1.5 - 0.4 - 2.0)
    assert measures.measure(p, "budget.left") == pytest.approx(6.1)
    assert measures.all_of(p)["ergostat.budget.left"] == pytest.approx(6.1)

    def broken(**kw):
        raise OSError("disk gone")
    monkeypatch.setattr(p.events, "query", broken)
    with pytest.raises(measures.MeasureError, match="cannot be read"):
        measures.measure(p, "ergostat.budget.left")
    got = measures.all_of(p)
    assert got["ergostat.budget.left"] is None and "disk gone" in got["ergostat.budget.left_error"]
    monkeypatch.undo()
    (tmp_path / "ergostat.yaml").write_text(MODEL)
    q = Project(mdl.load(tmp_path))
    with pytest.raises(measures.MeasureError, match="no budget"):
        measures.measure(q, "ergostat.budget.left")
    got = measures.all_of(q)
    assert got["ergostat.budget.left"] is None and "no budget" in got["ergostat.budget.left_error"]
