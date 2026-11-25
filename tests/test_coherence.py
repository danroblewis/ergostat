"""Coherence (coherence.py, SPEC §12l): the Process, Dynamics and Blocks views held against each other. A synthetic
model and record per finding, both directions of each pair; a coherent one agrees everywhere; too little record
says how much more it needs; the owner's thirteen disconnected stocks with a block whose events never appear give
the findings expected; and check, the MCP tool and the API say it."""

from __future__ import annotations

import json
import textwrap
import time
from pathlib import Path

import pytest

from ergostat import coherence as co
from ergostat import model as mdl
from ergostat.spec import chains
from ergostat.store import Project

BASE = """
name: coh
items:
  ticket:
    id: ticket/*
    states: [new, doing, review, done]
    on: {ticket.started: doing, ticket.submitted: review, ticket.merged: done, ticket.reopened: doing}
stocks:
  new: {unit: tickets, sensor: {items: ticket, state: new}}
  doing: {unit: tickets, sensor: {items: ticket, state: doing}}
  review: {unit: tickets, sensor: {items: ticket, state: review}}
flows:
  arriving: {to: new, sensor: {items: ticket, entering: new}}
  start: {from: new, to: doing, sensor: {items: ticket, entering: doing}}
  submit: {from: doing, to: review, sensor: {items: ticket, entering: review}}
  merge: {from: review, sensor: {items: ticket, entering: done}}
goals:
  new-clear: {stock: new, hold: "<= 0"}
  doing-clear: {stock: doing, hold: "<= 0"}
  review-clear: {stock: review, hold: "<= 0"}
blocks:
  starter: {type: program, run: 'true', goal: new-clear, takes: {kind: ticket, at: new, to: [doing]}, out: flow.start}
  worker: {type: program, run: 'true', goal: doing-clear, takes: {kind: ticket, at: doing, to: [review]}, out: flow.submit}
  merger: {type: program, run: 'true', goal: review-clear, takes: {kind: ticket, at: review, to: [done]}, out: flow.merge}
"""

PATH = (("ticket.started", "starter"), ("ticket.submitted", "worker"), ("ticket.merged", "merger"))


def project(tmp_path: Path, text: str = BASE, name: str = "m") -> Project:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    chains._CACHE.clear()
    return Project(mdl.load(d))


def work(p: Project, n: int = 12, path=PATH, first: str = "ticket.opened", by: dict | None = None, extra=None) -> None:
    """``n`` tickets in the last hour, each through ``path``: (event type, the block whose run records it; None: from
    outside). ``by`` overrides who records a type; ``extra(i)`` more steps for ticket i."""
    t0 = time.time() - 3600
    for i in range(n):
        it, t = f"ticket/{i}", t0 + i * 60
        if first:
            p.events.add(first, item=it, source="person", at=t)
        steps = list(path) + list(extra(i) if extra else [])
        for j, (ty, b) in enumerate(steps):
            b = (by or {}).get(ty, b)
            at = t + 10 * j + 5
            if b is None:
                p.events.add(ty, item=it, source="person", at=at + 1)
                continue
            run = p.events.add("agent.started", item=b, source="ergostat", at=at)
            p.events.add(ty, item=it, source=b, causedby=run["id"], at=at + 1)


def found(p: Project) -> dict[str, dict]:
    got = co.of_project(p, p.model.spec)
    return got, {f"{f['code']}@{f['about']}": f for f in got["findings"]}


def mismatches(got: dict) -> list[str]:
    return sorted(f"{f['code']}@{f['about']}" for f in got["findings"] if f["level"] == "mismatch")


def test_a_coherent_model_and_record_agree_everywhere(tmp_path):
    p = project(tmp_path)
    work(p)
    got, _ = found(p)
    k = got["kinds"]["ticket"]
    assert mismatches(got) == [] and k["needs"] is None
    assert k["agree"] == k["compared"] and k["compared"] >= 15
    assert all(k["pairs"][x]["compared"] for x in co.PAIRS)            # every pair compared something
    assert co.score_line("ticket", k).startswith(f"ticket: {k['compared']} of {k['compared']} agree (100%)")


def test_too_little_record_says_how_much_more_it_needs(tmp_path):
    p = project(tmp_path)
    work(p, n=2)
    got, _ = found(p)
    k = got["kinds"]["ticket"]
    assert k["needs"].startswith("2 more moves and 1 more item of ticket in the window (has 8 moves of 2 items")
    assert k["pairs"]["process-dynamics"]["compared"] == 0 and k["pairs"]["blocks-process"]["compared"] == 0
    assert k["pairs"]["dynamics-blocks"]["compared"] > 0                # the model alone is always compared
    assert "needs" in co.score_line("ticket", k)


# ---- Process ↔ Dynamics

def test_rework_seen_needs_a_backward_flow(tmp_path):
    p = project(tmp_path)
    work(p, path=PATH[:2] + (("ticket.reopened", "worker"), ("ticket.submitted", "worker"), PATH[2]))
    got, by = found(p)
    f = by["rework-without-flow@stock.doing"]
    assert f["pair"] == "process-dynamics" and f["file"].endswith("ergostat.yaml") and f["line"] > 0
    assert "went back from review to doing" in f["message"]
    assert "flow review-to-doing from review to doing, measured as items of ticket entering doing" in f["fix"]
    assert f["links"] == ["move-without-flow@stock.doing"]              # check says it too: linked, not duplicated


def test_a_step_the_record_skips_and_an_order_it_contradicts(tmp_path):
    p = project(tmp_path)
    work(p, path=(("ticket.submitted", None), ("ticket.merged", "merger")))     # new straight to review
    got, by = found(p)
    f = by["chain-skipped@stock.review"]
    assert "went from new straight to review" in f["message"] and "only through doing" in f["message"]
    q = project(tmp_path, BASE.replace("start: {from: new, to: doing", "start: {from: review, to: doing")
                .replace("submit: {from: doing, to: review", "submit: {from: new, to: review"), "q")
    work(q)
    got, by = found(q)
    assert "order-contradicted@stock.review" in by
    assert "run the other way, from review to doing" in by["order-contradicted@stock.review"]["message"]


def test_arrivals_and_completions_match_the_chain_s_ends(tmp_path):
    text = BASE.replace("  merge: {from: review, sensor: {items: ticket, entering: done}}\n", "").replace(", out: flow.merge}", "}")
    text = text.replace("  arriving: {to: new, sensor: {items: ticket, entering: new}}\n", "")
    p = project(tmp_path, text)
    work(p)
    got, by = found(p)
    a = by["arrival-not-modelled@stock.new"]
    assert "arrived in new in the window" in a["message"] and "from outside to new" in a["fix"]
    assert a["links"] == ["state-stock-without-inflow@stock.new"]
    c = by["completion-not-modelled@stock.review"]
    assert "finished (review to done)" in c["message"] and "from review to outside" in c["fix"]


def test_a_modelled_flow_the_record_never_moved_is_said_not_counted(tmp_path):
    text = BASE.replace("flows:\n", "flows:\n  bounced: {from: review, to: new, sensor: {items: ticket, entering: new, "
                                    "where: {bounced: true}}}\n")
    p = project(tmp_path, text)
    work(p)
    got = co.compare(p.model.spec, p.events, problems=[], quiet={})
    f = next(x for x in got["findings"] if x["id"] == "flow-not-seen@items.ticket")
    assert f["level"] == "note" and "Quiet is not absent" in f["message"] and "in the window: bounced." in f["message"]
    assert got["kinds"]["ticket"]["unseen"] == ["bounced"] and mismatches(got) == []
    k = got["kinds"]["ticket"]
    assert k["agree"] == k["compared"]                                 # not counted against
    quiet = {"flow.bounced": {"says": "it never moved (at most 0 an hour)"}}
    g2 = co.compare(p.model.spec, p.events, problems=[], quiet=quiet)
    f2 = next(x for x in g2["findings"] if x["code"] == "flow-not-seen")
    assert "(bounced: not exercised by the record)" in f2["message"]


# ---- Dynamics ↔ Blocks

def test_a_stock_where_work_waits_needs_a_goal_and_a_loop(tmp_path):
    text = BASE.replace('  review-clear: {stock: review, hold: "<= 0"}\n', "") \
        .replace('  doing-clear: {stock: doing, hold: "<= 0"}\n', '  doing-clear: {stock: doing, hold: "<= 0"}\n  '
                 'doing-short: {stock: doing, hold: "<= 3"}\n').replace("goal: doing-clear, ", "")
    text = text.replace("merger: {type: program, run: 'true', goal: review-clear, ", "merger: {type: program, run: 'true', ")
    p = project(tmp_path, text)
    got, by = found(p)
    w = by["waiting-without-goal@stock.review"]
    assert w["pair"] == "dynamics-blocks" and 'review-clear: {stock: review, hold: "<= 0"}' in w["fix"]
    g = by["goal-without-loop@goal.doing-clear"]
    assert g["links"] == ["missing-feedback@goal.doing-clear"]


def test_a_flow_work_moves_is_moved_by_a_block_or_said_to_come_from_outside(tmp_path):
    text = BASE.replace("  submit: {from: doing, to: review, sensor: {items: ticket, entering: review}}",
                        "  submit: {from: doing, to: review}") \
        .replace("worker: {type: program, run: 'true', goal: doing-clear, takes: {kind: ticket, at: doing, to: [review]}, "
                 "out: flow.submit}", "worker: {type: program, run: 'true', goal: doing-clear, out: flow.start}")
    text = text.replace("starter: {type: program, run: 'true', goal: new-clear, takes: {kind: ticket, at: new, to: [doing]}, "
                        "out: flow.start}", "starter: {type: program, run: 'true', goal: new-clear, takes: {kind: ticket, "
                        "at: new, to: [doing]}, out: block.worker}")
    p = project(tmp_path, text)
    got, by = found(p)
    f = by["flow-moved-by-nothing@flow.submit"]
    assert "no block moves it and nothing measures it" in f["message"] and "type: external, out: flow.submit" in f["fix"]
    assert "flow-moved-by-nothing@flow.arriving" not in by            # an observed rate from outside: said, fine
    assert got["kinds"]["ticket"]["movers"]["arriving"] == "outside (observed by its sensor)"
    assert got["kinds"]["ticket"]["movers"]["merge"] == "block merger"
    # a block that takes the items and moves no flow: the other direction
    q = project(tmp_path, BASE.replace(", out: flow.merge}", "}"), "q")
    got, by = found(q)
    assert by["block-moves-no-flow@block.merger"]["links"] == ["no-visible-effect@block.merger"]


def test_the_owners_thirteen_disconnected_stocks_and_a_block_never_seen_acting(tmp_path):
    """The owner's shape (thirteen state stocks, each drained to a cloud, a goal and a block per step), with a record
    where the items move through every state and one block (do-approved) never acts: its moves come from outside."""
    from tests.test_chains import STATES, owners_model
    p = project(tmp_path, owners_model(), "ff")
    t0 = time.time() - 3600
    for i in range(6):
        it, t = f"ff/{i}", t0 + i * 120
        p.events.add("ff.opened", item=it, source="person", at=t)
        for j, s in enumerate(STATES[1:]):
            b = f"do-{STATES[j]}"
            if b == "do-approved":
                p.events.add(f"ff.{s}", item=it, source="person", at=t + 5 * j + 2)
                continue
            run = p.events.add("agent.started", item=b, source="ergostat", at=t + 5 * j + 1)
            p.events.add(f"ff.{s}", item=it, source=b, causedby=run["id"], at=t + 5 * j + 2)
    got, by = found(p)
    codes = mismatches(got)
    assert "loops-not-connected@stock.ff-requested" in codes
    assert by["loops-not-connected@stock.ff-requested"]["links"] == ["loops-not-connected@stock.ff-requested"]
    assert sum(c.startswith("move-without-flow@") for c in codes) == 12      # each move seen, no flow carries it
    assert "arrival-not-modelled@stock.ff-requested" in codes
    n = by["declared-not-seen-acting@block.do-approved"]
    assert n["pair"] == "blocks-process" and "moved by outside ergostat (person) 6 times" in n["message"]
    k = got["kinds"]["ff-ticket"]
    assert k["agree"] < k["compared"]


# ---- Blocks ↔ Process

def test_a_block_seen_acting_on_work_it_does_not_declare(tmp_path):
    p = project(tmp_path)
    work(p, by={"ticket.merged": "worker"})
    got, by = found(p)
    f = by["acts-undeclared@block.worker"]
    assert f["pair"] == "blocks-process" and "from review to done 12 times" in f["message"]
    assert f["fix"].startswith("add review to its takes: at: (and done to its to:); or out: flow.merge")
    m = by["declared-not-seen-acting@block.merger"]
    assert "they were moved by block worker 12 times" in m["message"]


def test_a_move_from_outside_where_the_model_says_a_block_moves_it(tmp_path):
    p = project(tmp_path)
    work(p, by={"ticket.merged": None})
    got, by = found(p)
    f = by["moved-without-its-block@flow.merge"]
    assert "by outside ergostat (person)" in f["message"] and "block merger moves it" in f["message"]
    assert "type: external, out: flow.merge" in f["fix"]
    # said as an outside rate, it agrees
    text = BASE.replace(", out: flow.merge}", "}").replace("  merger: {type: program", "  merging: {type: external, "
                                                                                       "out: flow.merge}\n  merger: {type: program")
    q = project(tmp_path, text.replace("merger: {type: program, run: 'true', goal: review-clear, takes: {kind: ticket, at: "
                                       "review, to: [done]}}\n", ""), "q")
    work(q, by={"ticket.merged": None})
    got, by = found(q)
    assert "moved-without-its-block@flow.merge" not in by


def test_check_says_coherence_in_its_text_and_json(tmp_path, capsys):
    from ergostat.cli import main
    p = project(tmp_path)
    work(p, by={"ticket.merged": "worker"})
    assert main(["-C", str(p.model.spec.root), "check"]) == 0
    out = capsys.readouterr().out
    assert "Coherence" in out and "ticket: " in out and "Blocks ↔ Process" in out and "acts-undeclared" in out
    main(["-C", str(p.model.spec.root), "check", "--json"])
    j = json.loads(capsys.readouterr().out)
    assert j["coherence"]["kinds"]["ticket"]["compared"] > 0
    assert any(f["id"] == "acts-undeclared@block.worker" for f in j["coherence"]["findings"])


def test_the_mcp_tool(tmp_path):
    from ergostat.mcp import TOOLS, Server
    p = project(tmp_path)
    work(p, by={"ticket.merged": None})
    assert any(t["name"] == "coherence" for t in TOOLS)
    r = Server(Path(p.model.spec.root)).call("coherence", {})
    got = json.loads(r["content"][0]["text"])
    assert any(f["id"] == "moved-without-its-block@flow.merge" for f in got["findings"])
    assert got["scores"][0].startswith("ticket: ")


@pytest.mark.parametrize("example", ["ticket-factory", "the-job", "small-requests", "coordinator"])
def test_the_examples_model_alone_has_no_dynamics_blocks_mismatch(example):
    """Without a record, only Dynamics ↔ Blocks compares: every example's chains have goals, loops and movers."""
    from ergostat.spec import read
    root = Path(__file__).resolve().parent.parent / "examples" / example
    spec, _ = read(root / "ergostat.yaml")
    got = co.compare(spec, None, problems=[])
    assert mismatches(got) == []
    assert all(k["needs"] == "a record (none yet)" for k in got["kinds"].values())


def _fresh(example: str, dest: Path) -> Path:
    import shutil
    import subprocess
    src = Path(__file__).resolve().parent.parent / "examples" / example
    files = subprocess.run(["git", "-C", str(src), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    for f in files:
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / f, dest / f)
    return dest


@pytest.mark.slow
def test_the_coherent_examples_agree_after_a_short_run_on_their_stand_ins(tmp_path):
    """ticket-factory and coordinator, run on their stand-ins for half a minute (no page): where the record is enough to
    compare, every comparison agrees; the rest says how much more it needs."""
    import os
    import subprocess
    import sys
    env = {**os.environ, "TF_OFFLINE": "1"}
    ds = [_fresh(x, tmp_path / x) for x in ("ticket-factory", "coordinator")]
    try:
        for d in ds:
            subprocess.run([sys.executable, "-m", "ergostat", "-C", str(d), "run", "--no-web"], env=env, check=True,
                           capture_output=True, timeout=60)
        time.sleep(25)
    finally:
        for d in ds:
            subprocess.run([sys.executable, "-m", "ergostat", "-C", str(d), "run", "--stop"], env=env, capture_output=True,
                           timeout=60)
    compared = 0
    for d in ds:
        p = Project(mdl.load(d))
        got = co.of_project(p, p.model.spec)
        assert mismatches(got) == [], (d.name, [f["message"] for f in got["findings"] if f["level"] == "mismatch"])
        compared += sum(x["compared"] for x in got["kinds"].values() if not x["needs"])
    assert compared > 20                                  # the record was compared, not only waited for
