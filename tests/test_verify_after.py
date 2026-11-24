"""Merge first, verify after (dev/bin/verify.py; dev/records/merge-first-verify-after.md), on the factory's fixture
repository: gaps land on the quick check without a full suite; verification is due on the line threshold and on the
time limit; a red window is bisected to its culprit, which is reverted with what is stacked on it and sent back; the
ref `verified` moves only on green; a reverted gap comes back whole; the replay and the dashboard series."""

from __future__ import annotations

import calendar
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.test_factory import ANY_BAD, BIN, Factory, approved_gaps, git, module, stacked_gaps, suite_runs

if str(BIN) not in sys.path:
    sys.path.append(str(BIN))                          # (after the stdlib: dev/bin/queue.py never shadows it here)

NAMED = ("echo named >> {named}; if ls bad*.txt >/dev/null 2>&1; then echo 'FAILED tests/test_b.py::test_b - boom'; "
         "exit 1; fi; echo 'PASSED tests/test_b.py::test_b'")


def lane(tmp: Path, rerun: str = NAMED, lines: int = 3, hours: float = 2) -> Factory:
    """The fixture with [verify] after on: unit (the full suites) fails while a bad*.txt is in the tree, counting its
    runs; imports counts the quick checks; main holds tests/test_b.py; the ref verified starts at main."""
    f = Factory(tmp, unit=ANY_BAD.format(runs=tmp / "runs", greens=tmp / "greens"))
    text = f.config.read_text().replace('rerun = "echo again {tests}"', f'rerun = "{rerun.format(named=tmp / "named")}"')
    f.config.write_text(text + f'imports = "echo imports >> {tmp / "quick"}"\n[verify]\nafter = true\nlines = {lines}\n'
                               f'hours = {hours}\nsmoke = []\n')
    (f.checkout / "tests").mkdir()
    (f.checkout / "tests" / "test_b.py").write_text("def test_b():\n    pass\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "a test")
    git(f.checkout, "push", "-q", "origin", "main")
    f.run("verify.py", argv=("start",))
    return f


def count(f: Factory, name: str) -> int:
    p = f.tmp / name
    return len(p.read_text().splitlines()) if p.exists() else 0


def pushed(f: Factory) -> None:
    """The push the queue (or the lane) asked for, approved and run: the fixture's origin moved to main."""
    db = f.db()
    db["actions"] = {k: "ran" for k in db.get("actions", {})}
    f.record.write_text(json.dumps(db))
    git(f.checkout, "push", "-q", "origin", "main")


def ref(f: Factory) -> str:
    return git(f.checkout, "rev-parse", "refs/heads/verified")


def on_main(f: Factory, path: str) -> bool:
    return subprocess.run(["git", "-C", str(f.checkout), "cat-file", "-e", f"main:{path}"]).returncode == 0


def landed_stack(tmp: Path, **kw) -> tuple[Factory, str]:
    """x, a, b (stacked on a) and c landed in one batch; a breaks the full suites. (f, the verified commit)"""
    f = lane(tmp, **kw)
    start = ref(f)
    stacked_gaps(f, {"a": 1, "b": 2}, bad="a")
    approved_gaps(f, {"x": 0, "c": 3}, batch=4)
    said, _ = f.run("queue.py", "gap/x")
    assert said.count("gap.merged") == 4 and suite_runs(f) == 0          # landed with no full suite run
    assert count(f, "quick") == 1                                         # one quick check for the batch
    pushed(f)
    return f, start


def test_a_batch_lands_on_the_quick_check_and_a_red_window_is_bisected_reverted_and_verified_again(tmp_path):
    f, start = landed_stack(tmp_path)
    said, _ = f.run("verify.py", argv=("run",))
    assert suite_runs(f) == 1                                             # the tip; the bisection ran by name
    assert said.count("gap.queue-failed") == 1 and said.count("gap.retried") == 1
    a, b = f.item("gap/a"), f.item("gap/b")
    assert a["state"] == "queue-failed" and a["fields"]["failed_tests"] == ["tests/test_b.py::test_b"]
    assert a["fields"]["verify_confirmed"] is True and len(a["fields"]["reverted_by_verify"]) == 1
    assert b["state"] == "approved" and len(b["fields"]["reverted_by_verify"]) == 1
    assert f.item("gap/x")["state"] == f.item("gap/c")["state"] == "merged"
    assert not on_main(f, "bad.txt") and not on_main(f, "a.txt") and not on_main(f, "b.txt")
    assert on_main(f, "x.txt") and on_main(f, "c.txt")
    body = git(f.checkout, "log", "-2", "--format=%B", "main")
    assert body.count("This reverts commit") == 2                        # (escapes.py reads these)
    assert ref(f) == start                                                # red: the ref stays
    pending = json.loads((f.model / "run" / "queue.json").read_text())["pending"]
    assert pending["reverts"] is True and pending["sha"] == git(f.checkout, "rev-parse", "main")
    assert json.loads((f.model / "run" / "verify.json").read_text())["again"] == "after the revert of gap/a"
    pushed(f)
    said, _ = f.run("verify.py", argv=("run",))                         # due again after the revert: green
    assert suite_runs(f) == 2 and ref(f) == git(f.checkout, "rev-parse", "main")
    told = {i for i, g in f.db()["items"].items() if g["fields"].get("verified_sha") == ref(f)}
    assert told == {"gap/x", "gap/c"}                                    # (a reverted merge is not verified)
    said, _ = f.run("verify.py", argv=("run",))
    assert suite_runs(f) == 2                                             # nothing new: not due


def test_a_reverted_gap_and_its_stack_come_back_whole(tmp_path):
    f, _ = landed_stack(tmp_path)
    f.run("verify.py", argv=("run",))
    pushed(f)
    f.fold([{"event": "gap.retried", "item": "gap/a", "data": {"approved_by": "flake-retry"}}], None)
    said, _ = f.run("queue.py", "gap/b")                                 # b's base was reverted: it comes along
    assert said.count("gap.merged") == 2 and on_main(f, "a.txt") and on_main(f, "b.txt")
    assert "Reapply gap/a" in git(f.checkout, "log", "--format=%s", "main")


def test_two_culprits_in_one_window_are_found_one_after_the_other(tmp_path):
    f = lane(tmp_path)
    start = ref(f)
    approved_gaps(f, {"p": 0, "a": 1, "q": 2, "c": 3}, bad="a", batch=4, edits={"c": "bad-c.txt"})
    f.run("queue.py", "gap/p")
    pushed(f)
    f.run("verify.py", argv=("run",))
    assert f.item("gap/a")["state"] == "queue-failed" and f.item("gap/c")["state"] == "merged"
    pushed(f)
    said, _ = f.run("verify.py", argv=("run",))                         # red again: c, never a again
    assert said.count("gap.queue-failed") == 1 and f.item("gap/c")["state"] == "queue-failed"
    assert ref(f) == start and not on_main(f, "bad-c.txt") and on_main(f, "q.txt")
    pushed(f)
    f.run("verify.py", argv=("run",))
    assert ref(f) == git(f.checkout, "rev-parse", "main")


def test_a_dependent_never_lands_while_its_reverted_base_is_away(tmp_path):
    f, _ = landed_stack(tmp_path)
    f.run("verify.py", argv=("run",))
    pushed(f)
    head = git(f.checkout, "rev-parse", "main")
    said, lines = f.run("queue.py", "gap/b")                             # a is still in triage (queue-failed)
    assert "gap.merged" not in said and git(f.checkout, "rev-parse", "main") == head
    assert any("its base gap/a is not approved" in str(x.get("nack")) for x in lines)


def test_a_culprit_found_by_full_runs_when_its_tests_do_not_fail_by_name(tmp_path):
    f = lane(tmp_path, rerun="echo again")                                # (named runs say nothing: unknown)
    approved_gaps(f, {"p": 0, "q": 1, "r": 2, "s": 3}, batch=4, edits={"r": "bad-r.txt"})
    f.run("queue.py", "gap/p")
    pushed(f)
    said, _ = f.run("verify.py", argv=("run",))
    assert f.item("gap/r")["state"] == "queue-failed" and said.count("gap.retried") == 0
    assert [f.item(f"gap/{g}")["state"] for g in "pqs"] == ["merged"] * 3
    assert not on_main(f, "bad-r.txt") and on_main(f, "s.txt")
    # the tip; a round of 2 prefixes at once, then 1 (with or without the docs commit as the last prefix); r alone
    assert suite_runs(f) == 5


def test_main_s_own_failure_reverts_nothing_and_holds_the_lane(tmp_path):
    f = lane(tmp_path, lines=1)
    (f.checkout / "bad-main.txt").write_text("main's own\n")               # (verified before it broke: the machine)
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "main breaks")
    git(f.checkout, "push", "-q", "origin", "main")
    git(f.checkout, "update-ref", "refs/heads/verified", "main")
    start = ref(f)
    approved_gaps(f, {"p": 0}, batch=1)
    f.run("queue.py", "gap/p")
    pushed(f)
    said, _ = f.run("verify.py", argv=("run",))
    assert "intervention.recorded" in said and "gap.queue-failed" not in said and ref(f) == start
    assert on_main(f, "p.txt")
    said, _ = f.run("verify.py", argv=("run",))                         # held until the intervention is remedied
    assert said == [] and suite_runs(f) == 1


def test_a_red_quick_check_keeps_the_gap_off_main_with_no_full_suite(tmp_path):
    quick = ("if [ -e tests/test_q.py ]; then echo 'FAILED tests/test_q.py::test_q - no'; exit 1; fi; "
             "echo 'PASSED tests/test_q.py::test_q'")
    f = lane(tmp_path, rerun=quick)
    approved_gaps(f, {"q": 0}, batch=1, edits={"q": "tests/test_q.py"})
    said, _ = f.run("queue.py", "gap/q")
    assert "gap.queue-failed" in said and not on_main(f, "q.txt") and suite_runs(f) == 0


def history(tmp: Path) -> tuple[Path, list[str]]:
    """A repository: a start, then three merges of 10, 10 and -10 lines (made an hour apart from 2026-11-01 00:00)."""
    repo = tmp / "r"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    (repo / "f.txt").write_text("")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "start")
    shas = [git(repo, "rev-parse", "HEAD")]
    for i, body in enumerate(["a\n" * 10, "a\n" * 20, "a\n" * 10], 1):
        git(repo, "checkout", "-q", "-b", f"g{i}")
        (repo / "f.txt").write_text(body)
        git(repo, "commit", "-q", "-am", f"g{i}")
        git(repo, "checkout", "-q", "main")
        at = f"2026-11-01T0{i}:00:00Z"
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", "merge", "-q",
                        "--no-ff", "-m", f"Merge branch 'factory/g{i}'", f"g{i}"], check=True,
                       env={**os.environ, "GIT_COMMITTER_DATE": at, "GIT_AUTHOR_DATE": at})
        shas.append(git(repo, "rev-parse", "HEAD"))
    return repo, shas


def test_verification_is_due_on_the_line_threshold_and_on_the_time_limit(tmp_path):
    v = module("verify")
    repo, shas = history(tmp_path)
    t1 = float(calendar.timegm((2026, 11, 1, 1, 0, 0)))                  # the first merge
    cfg = lambda lines, hours: {"verify": {"lines": lines, "hours": hours}}   # noqa: E731
    assert v.due(cfg(15, 2), repo, {}, shas[0], shas[1], t1 + 60) == ""                     # 10 lines, a minute
    assert v.due(cfg(15, 2), repo, {}, shas[0], shas[2], t1 + 3660).startswith("20 lines merged")
    assert v.due(cfg(25, 2), repo, {}, shas[0], shas[3], t1 + 7260).startswith("30 lines merged")  # a removal adds
    assert v.due(cfg(15, 2), repo, {}, shas[0], shas[1], t1 + 2 * 3600).startswith("its oldest unverified commit")
    assert v.due(cfg(15, "90m"), repo, {}, shas[0], shas[1], t1 + 1.4 * 3600) == ""
    assert v.due(cfg(15, 2), repo, {}, shas[1], shas[1], t1 + 9 * 3600) == ""                # verified: never due
    assert v.due(cfg(15, 2), repo, {"again": "after the revert of gap/x"}, shas[0], shas[1], t1) == \
        "after the revert of gap/x"
    assert v.due(cfg(15, 2), repo, {}, "", shas[1], t1) == "no commit is verified yet"
    for bad in (0, 100_001, True, "x"):                                   # refused: verified at once, never silent
        assert "cannot be read" in v.due(cfg(bad, 2), repo, {}, shas[0], shas[1], t1)
    assert "cannot be read" in v.due(cfg(15, 49), repo, {}, shas[0], shas[1], t1)


def test_the_model_s_parameters_are_the_default_settings():
    v = module("verify")
    assert v.settings({}) == (1500, 2.0)
    assert v.settings({"verify": {"lines": 40, "hours": "30m"}}) == (40, 0.5)


@pytest.mark.parametrize("bad", [3, 0, 9])
def test_first_red_finds_the_first_failing_prefix(bad):
    v = module("verify")
    asked: list[list[int]] = []

    def check(picks):
        asked.append(picks)
        return ["fail" if p >= bad else "pass" for p in picks]
    assert v.first_red(-1, 9, check, 2) == (bad - 1, bad)
    assert len(asked) <= 3 and all(len(p) <= 2 for p in asked)            # 10 prefixes in rounds of 2: log3


def test_first_red_stops_where_a_check_cannot_tell():
    v = module("verify")
    assert v.first_red(-1, 9, lambda picks: ["pass", "unknown"][:len(picks)], 2) == (2, 9)


def batch(i: int, state: str, gaps: list[str], runs: int, start: float, failed: tuple = ()) -> dict:
    return {"id": f"batch/b{i}", "state": state, "fields": {
        "started_at": start, "landed_at": start + 1800 * runs if state != "failed" else None,
        "landed": gaps if state != "failed" else [], "failed": list(failed), "runs": [{"run": n} for n in range(runs)]}}


def test_the_replay_reports_runs_per_merged_gap_and_time_to_main_before_and_after():
    v = module("verify")
    now = 2_000_000.0
    gaps = [{"id": f"gap/{n}", "state": "merged", "fields": {"approved_at": now - 3600, "merged_lines": 400}}
            for n in "abcdef"]
    bs = [batch(1, "landed", ["gap/a", "gap/b"], 1, now), batch(2, "partial", ["gap/c"], 5, now + 3600, ("gap/x",)),
          batch(3, "landed", ["gap/d", "gap/e", "gap/f"], 1, now + 7200), batch(0, "landed", ["gap/old"], 1, 0)]
    got = v.replay(bs, gaps, now - 1, 1500, 2, 3)
    assert got["batches"] == 3 and got["merged"] == 6 and got["failed_in_queue"] == 1
    assert got["before"] == {"full_runs": 7, "runs_per_merged_gap": round(7 / 6, 3), "hours_to_main_median": 3.5}
    a = got["after"]
    # 4 x 400 lines reach 1500 at d: one window of 4, then e, f; the failing gap's window (4, and it): 1 + 2 x 2 + 2
    assert a["verifications"] == 2 and a["full_runs"] == 2 + 7 and a["quick_checks"] == 7
    assert a["hours_to_main_median"] == 2.55                             # its approval to its batch, and a quick check


def test_the_dashboard_series_read_the_verifications_and_the_batches():
    v = module("verify")
    now = time.time()
    lines = [{"at": now - 60, "outcome": "red", "runs": 5, "reverted": ["gap/a", "gap/b"]},
             {"at": now - 30, "outcome": "green", "runs": 1}, {"at": 1.0, "outcome": "red", "runs": 9, "reverted": ["x"]}]
    gaps = [{"id": "gap/c", "state": "merged", "fields": {"merged_at": now - 100, "verified_at": now, "verify_hours": 1.5}},
            {"id": "gap/d", "state": "merged", "fields": {"merged_at": now - 100, "verified_at": now, "verify_hours": 0.5}}]
    bs = [batch(1, "landed", ["gap/c", "gap/d"], 2, now - 200)]
    since = now - 86400
    assert v.reading("verify-escapes", lines, bs, gaps, since) == 1.0
    assert v.reading("verify-reverts", lines, bs, gaps, since) == 2.0
    assert v.reading("merge-to-verified-hours", lines, bs, gaps, since) == 1.0
    assert v.reading("suite-runs-per-merged-gap", lines, bs, gaps, since) == (2 + 6) / 2
    with pytest.raises(v.NoValue):
        v.reading("merge-to-verified-hours", lines, bs, [], since)


def test_switches_take_only_the_verified_commit(tmp_path):
    v = module("verify")
    repo, shas = history(tmp_path)
    git(repo, "update-ref", "refs/heads/verified", shas[1])
    assert v.switchable({}, repo, shas[3]) == shas[3]                     # off: main as pushed, as before
    assert v.switchable({"verify": {"after": True}}, repo, shas[3]) == shas[1]
    git(repo, "update-ref", "refs/heads/verified", shas[3])
    assert v.switchable({"verify": {"after": True}}, repo, shas[2]) is None   # (not pushed yet: none)
