"""What each run costs (SPEC §9.1): a run's CPU time and peak memory, from its wait status and one shared sampler; its AI
usage, from Claude Code's result message (an ``ai`` block's own ``claude -p``, or a session inside its program),
reported or estimated from tokens; the series per block; the measures ``ergostat.cost.*``; and the sampler's own cost
staying bounded with many runs at once."""

import json
import shlex
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat.costs import ai, prices
from ergostat.costs import record as cr
from ergostat.costs.sampler import SAMPLER, Measured
from ergostat.numbers import measures
from ergostat.spec import engine as eng
from ergostat.spec.engine import Engine
from ergostat.spec.ir import is_measure
from ergostat.store import Project

PY = shlex.quote(sys.executable)

PROJECT = """
name: costs
stocks:
  done:
    unit: things
flows:
  did:
    to: done
blocks:
{blocks}
"""


def project(tmp_path, blocks: str) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(PROJECT).replace("{blocks}", textwrap.indent(
        textwrap.dedent(blocks).strip(), "  ")))
    return Project(mdl.load(tmp_path))


def run(p, name: str, **kw) -> dict:
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks[name], "schedule", **kw)
    return p.events.query(n=1, item=name, type="agent.ran,agent.failed")[-1]


# ---- prices and usage, without a run

def test_a_price_is_found_by_model_id_or_family():
    assert prices.price_of("claude-haiku-4-5-20251001")[:2] == (1.0, 5.0)
    assert prices.price_of("claude-opus-5-5") == (4.0, 20.0, 0.20)
    assert prices.price_of("claude-opus-5")[:2] == (5.0, 25.0)            # the longest prefix: not 5-5's
    assert prices.price_of("sonnet") == prices.price_of("claude-sonnet-5-5")
    assert prices.price_of("gpt-9") is None and prices.price_of(None) is None
    # a million of each: input 1, output 5, cache reads a tenth of input, cache writes 1.25 times
    got = prices.estimate("claude-haiku-4-5", {"input": 1e6, "output": 1e6, "cache_read": 1e6, "cache_write": 1e6})
    assert got == pytest.approx(1 + 5 + 0.1 + 1.25)


RESULT = {"type": "result", "subtype": "success", "is_error": False, "result": "done", "num_turns": 3,
          "total_cost_usd": 0.0421,
          "usage": {"input_tokens": 10, "output_tokens": 500, "cache_read_input_tokens": 20000,
                    "cache_creation_input_tokens": 3000},
          "modelUsage": {"claude-haiku-4-5-20251001": {"inputTokens": 10, "outputTokens": 500, "cacheReadInputTokens": 20000,
                                                       "cacheCreationInputTokens": 3000, "costUSD": 0.0421}}}


def test_reported_dollars_are_kept_as_claude_code_said_them():
    u = ai.Usage()
    u.add_result(RESULT)
    r = u.record()
    assert r["cost_usd"] == 0.0421 and r["cost"] == "reported"
    assert r["tokens"] == {"input": 10, "output": 500, "cache_read": 20000, "cache_write": 3000, "cache_write_1h": 0,
                           "total": 23510}
    assert r["model"] == "claude-haiku-4-5-20251001" and r["sessions"] == 1 and r["turns"] == 3


def test_tokens_with_no_dollars_are_estimated_and_marked():
    u = ai.Usage()
    u.add_result({**RESULT, "total_cost_usd": None,
                  "modelUsage": {m: {k: v for k, v in x.items() if k != "costUSD"} for m, x in RESULT["modelUsage"].items()}})
    r = u.record()
    want = prices.estimate("claude-haiku-4-5", {"input": 10, "output": 500, "cache_read": 20000, "cache_write": 3000})
    assert r["cost"] == "estimated" and r["cost_usd"] == pytest.approx(want, abs=1e-6)
    u.add_result(RESULT)                                                  # one reported, one estimated
    assert u.record()["cost"] == "partly estimated"
    unknown = ai.Usage()
    unknown.add_result({"type": "result", "usage": {"input_tokens": 5, "output_tokens": 5}}, model="mystery-1")
    assert unknown.record()["cost"] == "unpriced" and unknown.record()["cost_usd"] is None


# a real haiku session's result (claude -p --output-format json, 2026-11-18), its cache writes kept an hour
REAL = {"total_cost_usd": 0.0021383500000000002,
        "usage": {"input_tokens": 2, "cache_creation_input_tokens": 10100, "cache_read_input_tokens": 11615, "output_tokens": 4,
                  "cache_creation": {"ephemeral_1h_input_tokens": 10100, "ephemeral_5m_input_tokens": 0}},
        "modelUsage": {"claude-haiku-5-5": {"inputTokens": 2, "outputTokens": 4, "cacheReadInputTokens": 11615,
                                            "cacheCreationInputTokens": 10100, "costUSD": 0.0021383500000000002,
                                            "cacheCreationEphemeral1hInputTokens": 10100}}}


def test_the_estimate_from_tokens_matches_what_claude_code_reported():
    reported = ai.Usage()
    reported.add_result({"type": "result", **REAL})
    by_tokens = ai.Usage()
    by_tokens.add_result({"type": "result", "usage": REAL["usage"]}, model="haiku")   # no dollars, no model usage
    assert reported.record()["cost"] == "reported" and by_tokens.record()["cost"] == "estimated"
    assert by_tokens.record()["cost_usd"] == pytest.approx(reported.record()["cost_usd"], rel=1e-3)


def test_a_result_message_is_read_in_place_of_its_text():
    u = ai.Usage()
    got = ai.expand(u, [json.dumps({**RESULT, "result": 'thinking aloud\n{"out": "flow.did", "moved": 2}'}) + "\n",
                        "plain\n"])
    assert got == ["thinking aloud\n", '{"out": "flow.did", "moved": 2}\n', "plain\n"]
    assert u.record()["cost_usd"] == 0.0421
    # ergostat's own lines are never taken for one
    assert not ai.is_result({"type": "result", "out": "flow.x", "moved": 1})


# ---- a stand-in run's CPU and memory

def test_a_stand_in_runs_cpu_and_peak_memory_are_recorded(tmp_path):
    work = tmp_path / "work.py"
    work.write_text(textwrap.dedent("""
        import subprocess, sys, time
        child = subprocess.Popen([sys.executable, "-c", "x = sum(range(4 * 10**7))"])   # a child burns CPU
        a = bytearray(150 * 2**20)                                                       # this one holds 150 MB
        a[::4096] = bytes(len(a[::4096]))
        time.sleep(1.5)
        child.wait()
        print(1)
    """))
    p = project(tmp_path, f"""
        worker:
          type: program
          run: {PY} work.py
          out: flow.did
    """)
    e = run(p, "worker")
    r = e["data"]["resources"]
    assert e["type"] == "agent.ran" and e["data"]["exit"] == 0
    assert r["cpu"] >= 0.3 and r["cpu"] == pytest.approx(r["cpu_user"] + r["cpu_system"], abs=0.002)
    assert r["memory_peak"] >= 150 * 2**20
    assert r["processes_peak"] >= 2 and r["samples"] >= 1 and r["method"] == "wait4+sampled"
    assert "ai" not in e["data"]                                          # no AI said anything: none recorded
    # as series of its block, beside the sensors'
    assert p.measurements.range("run/worker/cpu", 0)[-1][1] == pytest.approx(r["cpu"])
    assert p.measurements.range("run/worker/memory", 0)[-1][1] == pytest.approx(r["memory_peak"] / 1e6)
    assert not p.measurements.range("run/worker/cost_usd", 0)


def test_the_wait_status_counts_what_the_run_waited_for_however_short():
    inner = "import time; x = sum(range(2 * 10**7)); print(time.process_time())"
    proc = Measured([sys.executable, "-c", f"import subprocess, sys; subprocess.run([sys.executable, '-c', {inner!r}])"],
                    stdout=subprocess.PIPE, text=True, start_new_session=True)
    said, _ = proc.communicate()
    assert proc.returncode == 0 and proc.rusage is not None
    # the grandchild's CPU (as it measured itself), though it was never sampled and lived well under a second
    assert proc.rusage.ru_utime + proc.rusage.ru_stime >= float(said) * 0.95
    failing = Measured([sys.executable, "-c", "raise SystemExit(3)"])
    while failing.poll() is None:                                     # poll reaps it too, with its exit code
        time.sleep(0.01)
    assert failing.returncode == 3 and failing.rusage is not None


# ---- AI usage through a run

ECHO_RESULT = {"total_cost_usd": 0.0137,
               "usage": {"input_tokens": 12, "output_tokens": 340, "cache_read_input_tokens": 15000,
                         "cache_creation_input_tokens": 2100},
               "modelUsage": {"claude-haiku-4-5-20251001": {"inputTokens": 12, "outputTokens": 340,
                                                            "cacheReadInputTokens": 15000, "cacheCreationInputTokens": 2100,
                                                            "costUSD": 0.0137}}}


@pytest.mark.parametrize("live", [True, False])
def test_an_echo_session_inside_a_run_reports_its_cost_through_the_run(tmp_path, monkeypatch, live):
    monkeypatch.setenv("ERGOSTAT_CLAUDE", "echo")
    monkeypatch.setenv("ERGOSTAT_ECHO_WORK", "0.2")
    monkeypatch.setenv("ERGOSTAT_ECHO_RESULT", json.dumps(ECHO_RESULT))
    p = project(tmp_path, f"""
        dev:
          type: ai
          prompt: "Do the work."
          run: $ERGOSTAT_CMD session dev --model haiku{'' if live else ' --no-live'}
          timeout: 1m
          out: flow.did
    """)
    e = run(p, "dev")
    a = e["data"]["ai"]
    assert a["cost_usd"] == pytest.approx(0.0137) and a["cost"] == "reported"
    assert a["tokens"]["total"] == 12 + 340 + 15000 + 2100 and a["model"] == "claude-haiku-4-5-20251001"
    assert a["sessions"] == 1
    ran = p.events.query(n=1, type="session.ran")[-1]                   # the session's own record says the same
    assert ran["data"]["ai"]["cost_usd"] == pytest.approx(0.0137) and ran["data"]["cost_usd"] == pytest.approx(0.0137)
    assert e["data"]["resources"]["cpu"] > 0                            # and its process tree, the session's helper in it
    assert p.measurements.range("run/dev/cost_usd", 0)[-1][1] == pytest.approx(0.0137)


def test_an_echo_session_that_says_only_tokens_is_estimated(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_CLAUDE", "echo")
    monkeypatch.setenv("ERGOSTAT_ECHO_WORK", "0.1")
    fixture = tmp_path / "result.json"
    fixture.write_text(json.dumps({"total_cost_usd": None, "usage": {"input_tokens": 1000, "output_tokens": 2000},
                                   "modelUsage": {}}))
    monkeypatch.setenv("ERGOSTAT_ECHO_RESULT", str(fixture))
    p = project(tmp_path, """
        dev:
          type: ai
          prompt: "Do the work."
          run: $ERGOSTAT_CMD session dev --model claude-sonnet-5-5 --no-live
          timeout: 1m
          out: flow.did
    """)
    a = run(p, "dev")["data"]["ai"]
    assert a["cost"] == "estimated" and a["cost_usd"] == pytest.approx((1000 * 2 + 2000 * 10) / 1e6)
    assert a["model"] == "claude-sonnet-5-5"


def test_an_ai_blocks_own_claude_is_asked_for_json_and_its_text_still_acts(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "claude"                     # a stand-in named claude: what the engine runs for an ai block
    fake.write_text(f"""#!{sys.executable}
import json, sys
sys.stdin.read()
args = sys.argv[1:]
text = 'moving two\\n{{"out": "flow.did", "moved": 2}}'
if "--output-format" in args and args[args.index("--output-format") + 1] == "json":
    print(json.dumps({{**json.loads({json.dumps(RESULT)!r}), "result": text}}))
else:
    print(text)
""")
    fake.chmod(0o755)
    monkeypatch.setattr(eng, "AI_COMMAND", f"{fake} -p")
    p = project(tmp_path, """
        dev:
          type: ai
          prompt: "Move what is waiting."
          model: haiku
          out: flow.did
    """)
    e = run(p, "dev")
    assert e["data"]["moved"] == {"did": 2.0}                           # its text was taken as it would have been
    assert e["data"]["ai"]["cost_usd"] == pytest.approx(0.0421) and e["data"]["ai"]["cost"] == "reported"
    from ergostat.runner import log_path
    assert "moving two" in log_path(p, "dev").read_text()                # its words still go to its log


# ---- the measures

def test_the_cost_measures_read_the_runs(tmp_path):
    p = project(tmp_path, "w:\n  type: program\n  run: 'true'\n  out: flow.did\n")
    now = time.time()

    def ended(block, t, usd=None, cpu=0.5, mem=100e6, model="claude-haiku-4-5", toks=1000):
        data = {"exit": 0, "seconds": 1.0, "resources": {"cpu": cpu, "memory_peak": mem}}
        if usd is not None:
            data["ai"] = {"cost_usd": usd, "cost": "reported", "tokens": {"total": toks}, "model": model}
        p.events.add("agent.ran", item=block, source="ergostat", data=data, at=t)

    ended("dev", now - 7200, usd=2.0)                          # two hours ago: in the day, not the hour
    ended("dev", now - 600, usd=1.5, mem=300e6)
    ended("review", now - 300, usd=0.25, model="claude-opus-5-5")
    ended("w", now - 60)                                         # a program: CPU and memory, no dollars
    ended("dev", now - 3 * 86400, usd=50.0)                      # days ago: in neither
    m = lambda n: measures.measure(p, n)                         # noqa: E731
    assert m("ergostat.cost.usd") == pytest.approx(3.75)
    assert m("ergostat.cost.usd-hour") == pytest.approx(1.75)
    assert m("ergostat.cost.usd@dev") == pytest.approx(3.5) and m("cost.usd-hour@dev") == pytest.approx(1.5)
    assert m("ergostat.cost.usd@model:claude-opus-5-5") == pytest.approx(0.25)
    assert m("ergostat.cost.usd@model:haiku") == pytest.approx(3.5)
    assert m("ergostat.cost.tokens") == 3000 and m("ergostat.cost.runs") == 4
    assert m("ergostat.cost.cpu@w") == pytest.approx(0.5) and m("ergostat.cost.memory") == pytest.approx(300)
    assert all(is_measure(n) for n in ("ergostat.cost.usd", "ergostat.cost.cpu-hour@dev", "ergostat.cost.usd@model:haiku"))
    assert not is_measure("ergostat.cost.dollars")
    with pytest.raises(measures.MeasureError):
        measures.measure(p, "ergostat.cost.watts")
    use = cr.of_block(p, "dev", now - 86400, now)
    assert use["totals"]["runs"] == 2 and use["totals"]["cost_usd"] == pytest.approx(3.5)
    assert sum(v for _, v in use["hourly"]) == pytest.approx(3.5)
    assert cr.per_block(p, now - 86400, now)["w"]["cost_usd"] is None


def test_a_goal_on_ai_spend_checks_and_reads(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        name: budget
        stocks:
          ai-spend:
            unit: USD
            sensor:
              builtin: ergostat.cost.usd
              every: 5m
        goals:
          spend-capped:
            stock: ai-spend
            hold: "<= 5"
    """))
    from ergostat.spec import read
    _, problems = read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], problems
    p = Project(mdl.load(tmp_path))
    p.events.add("agent.ran", item="dev", source="ergostat", data={"ai": {"cost_usd": 6.0, "cost": "reported"}})
    assert measures.measure(p, "ergostat.cost.usd") == 6.0


# ---- the sampler's own cost

def test_fifty_short_runs_at_once_share_one_sampler_and_its_cost_stays_small(tmp_path):
    flows = "".join(f"  d{i}:\n    to: done\n" for i in range(50))
    blocks = "".join(f"  w{i}:\n    type: program\n    run: sleep 2.5; echo 1\n    out: flow.d{i}\n" for i in range(50))
    (tmp_path / "ergostat.yaml").write_text(f"name: many\nstocks:\n  done:\n    unit: things\nflows:\n{flows}blocks:\n{blocks}")
    p = Project(mdl.load(tmp_path))
    before = threading.active_count()
    cpu0, n0 = SAMPLER.cpu, SAMPLER.taken
    e = Engine(p, say=lambda s: None)
    peak = {"threads": 0, "samplers": 0}
    stop = threading.Event()

    def watch():
        while not stop.wait(0.05):
            peak["threads"] = max(peak["threads"], threading.active_count())
            peak["samplers"] = max(peak["samplers"], sum(1 for t in threading.enumerate() if t.name == "ergostat-sampler"))
    w = threading.Thread(target=watch, daemon=True)
    w.start()
    runs = [threading.Thread(target=e.run_block, args=(p.model.spec.blocks[f"w{i}"], "schedule")) for i in range(50)]
    for t in runs:
        t.start()
    for t in runs:
        t.join(60)
    stop.set()
    w.join()
    assert peak["samplers"] == 1                                         # one sampler for all of them, never one each
    # each run: its own thread, its reader and its writer (stream.pump); the sampler adds one, not one per run
    assert peak["threads"] <= before + 50 * 3 + 3
    ended = p.events.query(n=None, type="agent.ran")
    assert len(ended) == 50 and all(x["data"]["resources"]["samples"] >= 1 for x in ended)
    samples, cpu = SAMPLER.taken - n0, SAMPLER.cpu - cpu0
    assert samples >= 1
    assert cpu / samples < 0.25                                          # a sample of 50 trees: well under a second
    assert cpu < 0.2 * 2.5 * 2                                           # at most a fifth of one core while they ran
    shared = sum(x["data"]["resources"]["sampler_cpu"] for x in ended)
    assert shared == pytest.approx(cpu, rel=0.35, abs=0.05)              # its cost, shared out among the runs
    for _ in range(40):                                                  # and it stops once nothing is tracked
        if not SAMPLER.stats()["running"]:
            break
        time.sleep(0.1)
    assert not SAMPLER.stats()["running"]


# ---- an item's cost: the runs that took it (the item header, SPEC §9.5)

def test_an_items_cost_is_the_sum_of_the_runs_that_took_it_and_none_when_none_did():
    from types import SimpleNamespace as NS

    from ergostat.web.server import _item_cost
    ends = [{"type": "agent.ran", "time": 5.0, "causedby": "r1", "data": {"cost_usd": 0.25}},
            {"type": "agent.failed", "time": 6.0, "causedby": "r2", "data": {"cost_usd": 0.5}},
            {"type": "agent.ran", "time": 7.0, "causedby": "other", "data": {"cost_usd": 9.0}}]   # not this item's
    tidy = [{"type": "agent.failed", "time": 4.0, "causedby": "t1", "data": {"exit": 1}}]       # a program's failure

    class Events:
        def query(self, item=None, since=0, until=0, **kw):
            return [e for e in {"worker": ends, "tidy": tidy}.get(item, []) if since <= e["time"] <= until]

    def lease(*takes):                         # an item's folded lease field: its history names every take
        return {"lease": {"history": [{"run": x[0], "block": x[2] if len(x) > 2 else "worker", "taken": x[1]}
                                      for x in takes]}}
    p, m = NS(events=Events()), NS(agents={"worker": NS(rung=1), "tidy": NS(rung=4)})   # rungs as the model has them
    got = _item_cost(p, m, lease(("r1", 1.0), ("r2", 2.0), ("r3", 3.0)), 10.0)
    assert got["cost_usd"] == 0.75 and got["runs"] == 2 and got["failed"] == 1
    assert got["taken"] == 3 and got["ai"] and got["unknown"] == 0   # r3 has not ended: counted as taken, not as $0
    assert not _item_cost(p, m, lease(("t1", 1.0, "tidy")), 10.0)["ai"]   # a program alone: no AI
    assert _item_cost(p, m, lease(("t1", 1.0, "tidy")), 10.0)["unknown"] == 0   # its failure had no session to spend
    ends.append({"type": "agent.failed", "time": 8.0, "causedby": "r4", "data": {"exit": -9, "note": "killed"}})
    mixed = _item_cost(p, m, lease(("r4", 1.0), ("t1", 2.0, "tidy")), 10.0)   # an AI block and a program
    assert mixed["ai"] and mixed["unknown"] == 1 and mixed["runs"] == 2   # the killed AI run is not known, the program's not
    gone = _item_cost(p, m, lease(("x1", 1.0, "removed")), 10.0)
    assert gone["ai"]                                              # a block the model no longer has: maybe AI
    assert _item_cost(p, m, {"title": "never leased"}, 10.0) is None


def test_an_items_cost_counts_every_take_past_its_records_latest_events_and_rolled_up(tmp_path):
    """The takes are read from the lease's folded history, not the record's latest events: takes older than the
    detail's last 500 events, and takes rolled up into a snapshot, are all still counted."""
    import textwrap
    from types import SimpleNamespace as NS

    from ergostat import model as mdl
    from ergostat.rollup import compact
    from ergostat.spec import items as its
    from ergostat.store import Project
    from ergostat.web.server import _item_cost
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        projections:
          ticket: {match: {key: ticket/*}, states: [open, done], events: {ticket.done: {state: set('done')}}, otherwise: rest}
        storage: {rollup: {after: 1h, projections: {ticket: 2h}}}
        """))
    p = Project(mdl.load(tmp_path))
    t0, m = 1_700_000_000.0, NS(agents={"worker": NS(rung=1)})
    p.events.add("ticket.opened", item="ticket/1", source="test", at=t0)
    for i, run in enumerate(("r1", "r2", "r3")):                  # three takes, each ended, the first three hours
        t = t0 + 10 + i * 60
        p.events.add("ergostat.lease.taken", item="ticket/1", source="ergostat", at=t,
                     data={"run": run, "block": "worker", "fence": i + 1, "ttl": 600, "max": 9})
        p.events.add("agent.ran", item="worker", source="ergostat", causedby=run, at=t + 20,
                     data={"exit": 0, "ai": {"cost_usd": 0.5}})
        p.events.add("ergostat.lease.ended", item="ticket/1", source="ergostat", at=t + 30,
                     data={"run": run, "fence": i + 1, "how": "ack"})
    for i in range(600):                                          # then more events than the record shows
        p.events.add("ticket.noted", item="ticket/1", source="test", data={"note": i}, at=t0 + 3600 + i)
    d = its.detail(p.events, p.model.spec, "ticket/1")
    assert not [e for e in d["record"] if e["type"] == "ergostat.lease.taken"]   # the takes are past the record shown
    got = _item_cost(p, m, d["fields"], t0 + 10 ** 5)
    assert got["taken"] == 3 and got["runs"] == 3 and got["cost_usd"] == 1.5
    assert compact(p, now=t0 + 4 * 3600)["items"] == 1            # the takes rolled up into the item's snapshot
    d = its.detail(p.events, p.model.spec, "ticket/1")
    assert not [e for e in p.events.query(n=None, item="ticket/1") if e["type"] == "ergostat.lease.taken"]
    got = _item_cost(p, m, d["fields"], t0 + 10 ** 5)
    assert got["taken"] == 3 and got["runs"] == 3 and got["cost_usd"] == 1.5


def test_a_run_with_no_cost_that_failed_or_was_stopped_is_counted_as_not_known():
    """A session killed by a timeout or the cap may have spent with nothing recorded: its cost is not known, not $0."""
    from ergostat.costs.record import numbers, totals

    def end(kind, **data):
        return numbers({"type": kind, "time": 1.0, "data": {"exit": 0, **data}})
    rows = [end("agent.ran"), end("agent.failed", exit=1, note="killed (a timeout?)"),
            end("agent.ran", note="stopped with us"), end("agent.ran", exit=None),
            end("agent.failed", exit=1, ai={"cost_usd": 0.5})]                    # a failed run whose cost is known
    t = totals(rows)
    assert t["unknown"] == 3 and t["failed"] == 2 and t["cost_usd"] == 0.5
    assert totals(rows[:1])["unknown"] == 0                                  # a run that ended well: none
    full = "workspace pool code has none free for ticket/1: 1 in use, 0 held for review, 0 quarantined (of 1)"
    back = [end("agent.ran", exit=None, note=full), end("agent.ran", note=full)]  # given back unrun: no session began
    assert totals(back)["unknown"] == 0
    assert totals([end("agent.failed", exit=None, note=full)])["unknown"] == 1     # (failed with that note: still unknown)
