"""The merge queue's empty batch (dev/bin/queue.py picks() and emptied()): a run whose batch comes back empty says
why, and a gap that keeps coming back empty is sent back, not taken forever (docs/roadmap/overnight/
a-queue-run-that-lands-nothing.md)."""

from __future__ import annotations

import json
import subprocess
import sys

from tests.test_factory import BIN, Factory, approved_gaps, main_moves, merges, suite_runs

RED = "echo run >> {runs}"

# git's dry merge as it once came back for a gap (gap/a's commit, argv[2]): a conflict that names no file, which the
# walk reads as one with batch-mates only, on both walks; every other dry merge is git's own
NO_FILE = ("import sys; sys.path[:0] = [sys.argv[1]]; import queue\n"
           "real, own = queue.dry, sys.argv[2]\n"
           "queue.dry = lambda repo, onto, sha, msg: (None, []) if sha == own else real(repo, onto, sha, msg)\n")


def run_queue(f: Factory, iid: str, own_sha: str) -> tuple[list[str], list[dict]]:
    """queue.py for ``iid`` as Factory.run runs it, with NO_FILE's dry merge for ``own_sha``."""
    it = f.item(iid)
    given = {"trigger": "item", "item": it, "lease": {"fence": 1, "back": it["state"]}}
    code = NO_FILE + "sys.exit(queue.main())"
    r = subprocess.run([sys.executable, "-c", code, str(BIN), own_sha], input=json.dumps(given), cwd=f.model,
                       capture_output=True, text=True, timeout=120,
                       env={**f.env, "ERGOSTAT_ITEM": iid, "ERGOSTAT_LEASE": "1"})
    assert r.returncode == 0, r.stderr
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    return f.fold(lines, iid), lines


def given_back(f: Factory, iid: str) -> None:
    """The lease's nack played: the gap back at approved."""
    db = f.db()
    db["items"][iid]["state"] = "approved"
    f.record.write_text(json.dumps(db))


def test_an_empty_batch_nacks_its_gap_with_the_reason(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    shas = approved_gaps(f, {"a": 1})
    said, lines = run_queue(f, "gap/a", shas["a"])
    assert said == ["gap.queued", "gap.measured"] and merges(f) == [] and suite_runs(f) == 0
    nacks = [x["nack"] for x in lines if "nack" in x]
    assert len(nacks) == 1 and nacks[0]["count"] is False and nacks[0]["after"] == "10m"
    assert "came back empty (1 of 3)" in nacks[0]["why"]
    assert "failed only with batch-mates on both walks" in nacks[0]["why"]
    got = f.item("gap/a")["fields"]
    assert got["empty_batches"] == {"head": shas["a"], "n": 1} and got["empty_batch"] in nacks[0]["why"]


def test_a_gap_whose_batch_is_empty_past_the_ceiling_is_sent_back(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    shas = approved_gaps(f, {"a": 1})
    for k in (1, 2):
        said, lines = run_queue(f, "gap/a", shas["a"])
        assert said == ["gap.queued", "gap.measured"] and f.item("gap/a")["fields"]["empty_batches"]["n"] == k
        given_back(f, "gap/a")
    said, lines = run_queue(f, "gap/a", shas["a"])
    assert said == ["gap.queued", "gap.measured", "gap.sent-back"] and not [x for x in lines if "nack" in x]
    a = f.item("gap/a")
    assert a["state"] == "fix" and a["fields"]["failed_gates"] == 1
    assert a["fields"]["findings"][0].startswith("its queue batch came back empty 3 times: its dry merge failed only")
    assert a["fields"]["empty_batches"] == {"head": shas["a"], "n": 0}          # counted again from nothing
    # a count kept for another reviewed commit is not this one's (the same id, made again: lesson-5)
    db = f.db()
    db["items"]["gap/a"]["state"] = "approved"
    db["items"]["gap/a"]["fields"]["empty_batches"] = {"head": "0" * 40, "n": 2}
    f.record.write_text(json.dumps(db))
    said, lines = run_queue(f, "gap/a", shas["a"])
    assert said == ["gap.queued", "gap.measured"] and f.item("gap/a")["fields"]["empty_batches"]["n"] == 1


def test_picks_says_why_its_batch_is_empty(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    shas = approved_gaps(f, {"a": 1, "b": 2, "c": 3}, edits={"b": "app.py"})
    main_moves(f, "app.py")                                                    # b conflicts with main
    db = f.db()
    db["items"]["gap/c"]["fields"]["reviewed_head"] = "f" * 40                 # c's branch moved after its review
    f.record.write_text(json.dumps(db))
    code = NO_FILE + ("import fac, json; cfg = fac.config(); repo = fac.path(cfg, 'checkout')\n"
                      "fac.git(repo, 'fetch', '-q', 'origin', 'main'); fac.git(repo, 'merge', '-q', '--ff-only', "
                      "'origin/main'); pre = fac.git(repo, 'rev-parse', 'HEAD')\n"
                      "gaps = {g['id']: g for g in fac.items('gap', 'approved')}; out = {}\n"
                      "for gid in ('gap/a', 'gap/b', 'gap/c'):\n"
                      "    batch, head, why = queue.picks(cfg, repo, gaps[gid], 1, pre)\n"
                      "    out[gid] = [[g['id'] for g, _ in batch], why]\n"
                      "queue.dry = real\n"
                      "batch, head, why = queue.picks(cfg, repo, gaps['gap/a'], 1, pre)\n"
                      "out['merging'] = [[g['id'] for g, _ in batch], why]\n"
                      "print(json.dumps(out))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), shas["a"]], cwd=f.model, env=f.env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.splitlines()[-1])
    assert out["gap/a"] == [[], "its dry merge failed only with batch-mates on both walks (no file)"]
    assert out["gap/b"] == [[], "it was sent back: conflicts with main: app.py"]
    assert out["gap/c"][0] == [] and out["gap/c"][1].startswith("it was sent back: not merged: its branch moved")
    assert out["merging"] == [["gap/a"], ""]                                   # a batch that is not empty: no why
