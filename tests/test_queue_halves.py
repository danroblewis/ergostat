"""A red batch is split into two halves run at once, and a green half lands (dev/bin/queue.py land(), dev/bin/halves.py).
Every count below is worked by hand: R is a round of two trees at once, and a merge's number is its place in the batch."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest

from tests.test_factory import ANY_BAD, BIN, CLOCKED, Factory, approved_gaps, git, merges, module, stacked_gaps, suite_runs

TEN = "abcdefghij"
TAG = "batch-20261122T094631Z"


def ten(tmp: Path, bad: str, n: int = 10, minutes: float | None = None) -> Factory:
    """``n`` gaps a, b, ... ranked so, each of ``bad`` breaking the unit suite; each green tree logged in `greens`."""
    tmp.mkdir(exist_ok=True)
    f = Factory(tmp, unit=ANY_BAD.format(runs=tmp / "runs", greens=tmp / "greens"))
    text = f.config.read_text().replace("batch_max = 4", f"batch_max = {n}")
    f.config.write_text(text.replace(f"batch_max = {n}", f"batch_max = {n}\nbatch_minutes = {minutes}") if minutes else text)
    approved_gaps(f, {x: i for i, x in enumerate(TEN[:n], 1)}, batch=n, edits={x: f"bad-{x}.txt" for x in bad})
    return f


def proven(f: Factory) -> None:
    """Each commit main moved to in this run is a tree a full run passed."""
    greens = set((f.tmp / "greens").read_text().split())
    assert git(f.checkout, "rev-parse", "main^{tree}") in greens


def rounds(f: Factory, gid: str) -> list[dict]:
    return f.item(gid)["fields"]["suites_queue"]["rounds"]


def state(f: Factory, g: str) -> str:
    return f.item(f"gap/{g}")["state"]


# one bad merge of 10: the full run; R1 5+5 (the good 5 land); R2 on the bad 5, as 3+2; then
#   1, 2 (or 6, 7): R3 2+1, R4 1+1, so 1 + 4 x 2 = 9 full runs
#   3 (or 8): R3 2+1, where the 1 is it: 7
#   4, 5 (or 9, 10): the 2 is red, R3 1+1: 7
RUNS = {"a": 9, "b": 9, "c": 7, "d": 7, "e": 7, "f": 9, "g": 9, "h": 7, "i": 7, "j": 7}


@pytest.mark.parametrize("bad", TEN)
def test_one_bad_merge_of_ten_a_half_lands_after_the_first_round(tmp_path, bad):
    f = ten(tmp_path, bad)
    said, _ = f.run("queue.py", "gap/b" if bad == "a" else "gap/a")            # (a failing own gap waits on the push)
    assert said.count("gap.queue-failed") == 1 and said.count("gap.merged") == 9 and state(f, bad) == "queue-failed"
    assert suite_runs(f) == RUNS[bad] and sorted(merges(f)) == sorted(set(TEN) - {bad})
    first = set("fghij" if bad in "abcde" else "abcde")
    assert set(merges(f)[:5]) == first                                         # the good half, first
    for g in first:
        assert f.item(f"gap/{g}")["fields"]["suites_queue"]["batch_rounds"] == 1   # landed on the first round
    r = rounds(f, f"gap/{bad}")
    assert [h["result"] for h in r[0]["halves"]] == (["red", "green"] if bad in "abcde" else ["green", "red"])
    assert len(r) == (RUNS[bad] - 1) // 2
    proven(f)


def test_two_bad_merges_in_the_same_half(tmp_path):
    f = ten(tmp_path, "bd")
    said, _ = f.run("queue.py", "gap/a")
    # all red; R1 a..e red, f..j green; R2 a, b, c red and d, e red; R3 a, b red, c green; R4 a green, b red;
    # then d, e, known red: R5 d red, e green. 1 + 5 x 2
    assert suite_runs(f) == 11 and merges(f) == list("fghijcae")
    assert said.count("gap.queue-failed") == 2 and state(f, "b") == state(f, "d") == "queue-failed"
    proven(f)


def test_two_bad_merges_in_different_halves_the_next_round_lands(tmp_path):
    f = ten(tmp_path, "bg")
    said, _ = f.run("queue.py", "gap/a")
    # all red; R1 both red; R2 on a..e: a, b, c red, d, e green, landing; R3 c lands; R4 a lands, b; then f..j:
    # R5 i, j land; R6 h lands; R7 f lands, g. 1 + 7 x 2
    assert suite_runs(f) == 15 and merges(f) == list("decaijhf")
    assert said.count("gap.queue-failed") == 2 and state(f, "b") == state(f, "g") == "queue-failed"
    assert [h["result"] for h in rounds(f, "gap/b")[0]["halves"]] == ["red", "red"]
    assert [h["result"] for h in rounds(f, "gap/b")[1]["halves"]] == ["red", "green"]   # the next round lands
    proven(f)


def stacked_with_two(tmp: Path, bad: str) -> Factory:
    f = Factory(tmp, unit=ANY_BAD.format(runs=tmp / "runs", greens=tmp / "greens"))
    stacked_gaps(f, {"a": 1, "b": 2}, bad=bad)
    approved_gaps(f, {"c": 3, "d": 4}, batch=4)
    return f


def test_a_stacked_pair_stays_together_and_its_top_is_found(tmp_path):
    f = stacked_with_two(tmp_path, "b")
    f.run("queue.py", "gap/c")
    # all red; R1 a, b red and c, d green; R2 the stack's lower half a, alone: green. b on it is the very tree the first
    # run found red (the same four merges), so it is not run again: 1 + 2 + 1
    assert suite_runs(f) == 4 and merges(f) == ["c", "d", "a"] and state(f, "b") == "queue-failed"
    assert rounds(f, "gap/c")[0]["halves"][0]["gaps"] == ["gap/a", "gap/b"]
    proven(f)


def test_a_stacked_pair_whose_base_fails_never_lands_its_top(tmp_path):
    f = stacked_with_two(tmp_path, "a")
    f.run("queue.py", "gap/c")
    assert suite_runs(f) == 4 and merges(f) == ["c", "d"]                      # all red; R1; a alone red
    assert state(f, "a") == "queue-failed" and state(f, "b") == "approved"
    assert "failed_gates" not in f.item("gap/b")["fields"]


CONFLICT = """\
import sys
sys.path[:0] = [sys.argv[1]]
import queue
real, run, ran = queue.dry, queue.halves.run_all, [0]
def counted(*a, **k):
    ran[0] += 1
    return run(*a, **k)
queue.halves.run_all = counted
queue.dry = lambda repo, onto, sha, msg: (None, ["a.txt"]) if sha == sys.argv[2] and ran[0] else real(repo, onto, sha, msg)
sys.exit(queue.main())
"""


def test_a_half_that_conflicts_after_the_other_landed_goes_back_with_its_stack(tmp_path):
    f = Factory(tmp_path, unit=ANY_BAD.format(runs=tmp_path / "runs", greens=tmp_path / "greens"))
    approved_gaps(f, {"x": 0})
    shas = stacked_gaps(f, {"a": 1, "b": 2})
    approved_gaps(f, {"y": 3}, batch=4, edits={"y": "bad-y.txt"})
    (tmp_path / "conflict.py").write_text(CONFLICT)
    said, _ = f.run(str(tmp_path / "conflict.py"), "gap/x", argv=(str(BIN), shas["a"]))
    # all red; R1 x green, a, b, y red; then a conflicts on the new base, b goes with it, and y alone is red: 1 + 2 + 1
    assert suite_runs(f) == 4 and merges(f) == ["x"] and state(f, "y") == "queue-failed"
    for g in "ab":                                                             # not lost, and no gate failed
        assert state(f, g) == "approved" and "failed_gates" not in f.item(f"gap/{g}")["fields"]
    assert "gap.sent-back" not in said
    proven(f)


def test_the_time_allowance_running_out_mid_split_gives_the_rest_back(tmp_path):
    f = ten(tmp_path, "a", minutes=70)
    (tmp_path / "clocked.py").write_text(CLOCKED)
    said, lines = f.run(str(tmp_path / "clocked.py"), "gap/f", argv=(str(BIN), "20"))
    # all red (20), the named check (40), main (60), R1 (80: f..j land); no second round
    assert suite_runs(f) == 3 and merges(f) == list("fghij") and "gap.queue-failed" not in said
    assert all(state(f, g) == "approved" and "findings" not in f.item(f"gap/{g}")["fields"] for g in "abcde")
    assert f.item("gap/a")["fields"]["queue_runs"][-1]["given_back"] == 5
    proven(f)


def test_a_batch_of_two_with_one_bad_merge(tmp_path):
    f = ten(tmp_path, "a", n=2)
    f.run("queue.py", "gap/b")
    assert suite_runs(f) == 3 and merges(f) == ["b"] and state(f, "a") == "queue-failed"     # all red; R1 1 + 1
    proven(f)


def test_a_failure_of_both_merges_together_blames_the_second_without_running_it_again(tmp_path):
    runs = tmp_path / "runs"
    unit = f"echo run >> {runs}; if [ -e a.txt ] && [ -e b.txt ]; then echo 'FAILED tests/t.py::t - x'; exit 1; fi"
    f = Factory(tmp_path, unit=unit)
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    f.run("queue.py", "gap/a")
    # red together; R1 both green: a lands, and b on a is the very tree that was red
    assert suite_runs(f) == 3 and merges(f) == ["a"] and state(f, "b") == "queue-failed"


def test_a_red_half_never_stops_the_other(tmp_path):
    runs = tmp_path / "runs"
    unit = (f"echo run >> {runs}; if ls bad*.txt >/dev/null 2>&1; then echo 'FAILED tests/t.py::t - x'; exit 1; fi; "
            f"sleep 2; git write-tree >> {tmp_path}/greens")
    f = Factory(tmp_path, unit=unit)
    approved_gaps(f, {"a": 1, "b": 2}, batch=2, edits={"a": "bad-a.txt"})
    f.run("queue.py", "gap/b")
    assert merges(f) == ["b"] and state(f, "a") == "queue-failed"              # b's sleeping run outlived a's failure
    proven(f)


STALLS = """\
import sys
sys.path[:0] = [sys.argv[1]]
import fac, queue
real, only = queue.suites, sys.argv[2]
def suites(cfg, repo, tag, logs, *a, **k):
    if "-r" in tag and (repo / only).exists():
        raise fac.Stalled("unit", "its log did not grow", "")
    return real(cfg, repo, tag, logs, *a, **k)
queue.suites = suites
sys.exit(queue.main())
"""


def test_a_half_that_stalls_lands_nothing_and_goes_back(tmp_path):
    f = ten(tmp_path, "a", n=4)
    (tmp_path / "stalls.py").write_text(STALLS)
    said, _ = f.run(str(tmp_path / "stalls.py"), "gap/b", argv=(str(BIN), "c.txt"))
    # all red; R1 a, b red and c, d stalled: given back; R2 a red, b green
    assert merges(f) == ["b"] and state(f, "a") == "queue-failed"
    assert state(f, "c") == state(f, "d") == "approved" and "gap.merged" in said
    assert [h["result"] for h in rounds(f, "gap/a")[0]["halves"]] == ["red", "unknown"]


def test_both_halves_stalling_is_the_run_s_stall(tmp_path):
    f = ten(tmp_path, "a", n=2)
    (tmp_path / "stalls.py").write_text(STALLS.replace('(repo / only).exists()', "True"))
    said, lines = f.run(str(tmp_path / "stalls.py"), "gap/a", argv=(str(BIN), "x"))
    assert merges(f) == [] and "gap.queue-failed" not in said
    assert [x["nack"]["count"] for x in lines if "nack" in x] == [False] and f.item("gap/a")["fields"]["stalled"] == "unit"


NAMED = ('echo "$*" >> {t}/reruns\nrc=0\nfor x in "$@"; do case "$x" in -*) continue;; esac\n'
         ' if ls bad-*.txt >/dev/null 2>&1; then echo "FAILED $x - boom"; rc=1; else echo "PASSED $x"; fi\ndone\nexit $rc\n')


def reproducing(f: Factory) -> None:
    """The named tests fail alone while a bad merge is in the tree."""
    (f.tmp / "rerun.sh").write_text(NAMED.format(t=f.tmp))
    f.config.write_text(f.config.read_text().replace('rerun = "echo again {tests}"',
                                                     f'rerun = "sh {f.tmp / "rerun.sh"} {{tests}}"'))


@pytest.mark.parametrize("bad", TEN)
def test_one_bad_merge_that_reproduces_alone_costs_two_full_runs(tmp_path, bad):
    f = ten(tmp_path, bad)
    reproducing(f)
    said, _ = f.run("queue.py", "gap/b" if bad == "a" else "gap/a")
    # the full run (red), test_b on its tree, on main, a named round on the 10 prefixes, the full run on the 9
    assert suite_runs(f) == 2 and len((tmp_path / "reruns").read_text().splitlines()) == 12
    assert merges(f) == [x for x in TEN if x != bad] and state(f, bad) == "queue-failed"
    assert [r["kind"] for r in rounds(f, f"gap/{bad}")] == ["named"]
    assert not list((f.model / "run" / "queue-half").iterdir())
    proven(f)


@pytest.mark.parametrize("bad", ["bd", "bg"])
def test_two_bad_merges_that_reproduce_alone_cost_three_full_runs(tmp_path, bad):
    f = ten(tmp_path, bad)
    reproducing(f)
    f.run("queue.py", "gap/a")
    # red; a named round finds the first (both fail the same test, so no later prefix tells them apart); the survivors
    # red in full; a named round finds the second; the 8 green in full
    assert suite_runs(f) == 3 and merges(f) == [x for x in TEN if x not in bad]
    assert all(state(f, x) == "queue-failed" for x in bad)
    assert [r["kind"] for r in rounds(f, f"gap/{bad[1]}")] == ["named", "named"]
    proven(f)


def test_a_red_half_takes_the_named_path_too(tmp_path):
    # the first run's tests pass alone on the whole tree, so the batch is split; on the red half they fail alone, so it
    # is settled by name and not split further
    f = ten(tmp_path, "b", n=8)
    (tmp_path / "rerun.sh").write_text(f'echo "$*" >> {tmp_path}/reruns\nn=$(wc -l < {tmp_path}/reruns)\nrc=0\n'
                                       'for x in "$@"; do case "$x" in -*) continue;; esac\n'
                                       ' if [ "$n" -gt 2 ] && ls bad-*.txt >/dev/null 2>&1; then echo "FAILED $x - x"; rc=1;'
                                       ' else echo "PASSED $x"; fi\ndone\nexit $rc\n')
    f.config.write_text(f.config.read_text().replace('rerun = "echo again {tests}"',
                                                     f'rerun = "sh {tmp_path / "rerun.sh"} {{tests}}"'))
    (tmp_path / "unit2.sh").write_text(f"echo run >> {tmp_path}/runs\nif ls bad-*.txt >/dev/null 2>&1; then "
                                       + "".join(f"echo 'FAILED tests/t.py::t{i} - x'; " for i in range(4))
                                       + f"exit 1; fi\ngit write-tree >> {tmp_path}/greens\n")
    f.config.write_text(f.config.read_text().replace(f.config.read_text().split('unit = "')[1].split('"\n')[0],
                                                     f"sh {tmp_path / 'unit2.sh'}"))
    f.run("queue.py", "gap/a")
    # all red (alone: passes, n=1; main: passes, n=2); R1 a..d red and e..h green; a..d's tests now fail alone: a named
    # round on its 4 prefixes finds b; a, c, d get one full run. 1 + 2 + 1
    assert suite_runs(f) == 4 and merges(f) == list("efghacd") and state(f, "b") == "queue-failed"
    assert [r["kind"] for r in rounds(f, "gap/b")] == ["halves", "named"]
    proven(f)


CRASH_UNIT = ("echo run >> {t}/runs; if [ ! -e {t}/crashed ]; then touch {t}/crashed; "
              + "".join(f"echo 'FAILED tests/test_x.py::test_{i} - OSError'; " for i in range(120))
              + "echo 'INTERNALERROR> OSError: [Errno 28] No space left on device'; exit 3; fi; "
              "if ls bad-*.txt >/dev/null 2>&1; then echo 'FAILED tests/test_b.py::test_b - boom'; exit 1; fi; "
              "git write-tree >> {t}/greens")


def test_a_crashed_run_names_no_test_and_goes_to_halves(tmp_path):
    f = Factory(tmp_path, unit=CRASH_UNIT.format(t=tmp_path))
    reproducing(f)
    approved_gaps(f, {x: i for i, x in enumerate("abcd", 1)}, batch=4)
    said, _ = f.run("queue.py", "gap/a")
    # crashed (no named run, no check on main: no gap or main blamed); R1 both green: a, b land; c, d on them, run whole
    assert suite_runs(f) == 4 and merges(f) == list("abcd") and not (tmp_path / "reruns").exists()
    assert "gap.queue-failed" not in said and "intervention.recorded" not in said
    proven(f)


@pytest.mark.parametrize(("rc", "text", "crash"), [
    (3, "", True), (1, "INTERNALERROR> boom", True), (1, "OSError: [Errno 28] No space left on device", True),
    (1, "FAILED t.py::t - worker 'gw3' crashed while running", True), (1, "FAILED t.py::t - assert 1", False),
    (2, "Interrupted: 1 error during collection", False), (0, "INTERNALERROR> said by a passing test", False),
    (1, "FAILED t.py::t[OSError: [Errno 28] x] - assert 1", False), (1, "t.py::t[[Errno 28]] FAILED [ 50%]", False),
    (1, "  File x, line 1\nOSError: [Errno 28] No space left on device\nFAILED t.py::t - assert 1", True),
])
def test_what_counts_as_a_crash(rc, text, crash):
    sys.modules.setdefault("fac", module("fac"))
    sys.path.append(str(BIN))
    try:
        assert bool(module("queue").crashed(rc, text)) is crash
    finally:
        sys.path.remove(str(BIN))


@pytest.mark.parametrize("passed", [
    "tests/test_queue_halves.py::test_what_counts_as_a_crash[1-OSError: [Errno 28] No space left on device-True] PASSED",
    "[gw3] [ 50%] PASSED tests/t.py::t[1-OSError: [Errno 28] No space left on device-True]",
    "SKIPPED [1] t.py::t[[Errno 28]]: no port", "t.py::t[[Errno 28]] XFAIL", "t.py::t[[Errno 28]] XPASS",
])
def test_a_passing_tests_name_is_no_crash(passed):
    sys.modules.setdefault("fac", module("fac"))
    sys.path.append(str(BIN))
    try:
        log = f"{passed}\nFAILED tests/test_b.py::test_b - assert 1 == 2\n"
        assert module("queue").crashed(1, log) == ""
        assert module("queue").crashed(1, log + "FAILED t.py::t - worker 'gw3' crashed while running 't.py::t'\n")
    finally:
        sys.path.remove(str(BIN))


def test_both_halves_crashing_blames_no_merge(tmp_path):
    unit = (f"echo run >> {tmp_path}/runs; echo 'FAILED tests/test_x.py::t - x'; "
            "echo 'INTERNALERROR> OSError: [Errno 28] No space left on device'; exit 3")
    f = Factory(tmp_path, unit=unit)
    approved_gaps(f, {x: i for i, x in enumerate("abcd", 1)}, batch=4)
    said, lines = f.run("queue.py", "gap/a")
    assert suite_runs(f) == 3 and merges(f) == [] and "gap.queue-failed" not in said    # the whole, then both halves
    assert [x["nack"]["count"] for x in lines if "nack" in x] == [False] and f.item("gap/a")["fields"]["stalled"] == "unit"


def test_two_half_runs_each_get_their_own_cpus_and_longer_limits():
    h = halves()
    cfg = {"suites": {"unit": "pytest -q -n 8 --dist worksteal", "browser": "pytest -n 4 x", "stall_minutes": 10,
                      "wall_minutes": 45}, "agents": {"queue_cpuset": "12-23"}}
    a, b = h.share(cfg, 0), h.share(cfg, 1)
    assert (a["agents"]["queue_cpuset"], b["agents"]["queue_cpuset"]) == ("12,13,14,15,16,17", "18,19,20,21,22,23")
    assert a["suites"]["unit"] == "pytest -q -n 4 --dist worksteal" and a["suites"]["browser"] == "pytest -n 2 x"
    assert (a["suites"]["stall_minutes"], a["suites"]["wall_minutes"]) == (20, 90)
    assert cfg["agents"]["queue_cpuset"] == "12-23" and cfg["suites"]["stall_minutes"] == 10       # the run's own: as it was
    assert h.share({"suites": {"stall_minutes": 40, "wall_minutes": 100}}, 0)["suites"]["wall_minutes"] == 120  # ceiling
    assert h.fac.limits(h.share({"suites": {"stall_minutes": 40, "wall_minutes": 100}}, 0)) == (3600.0, 7200.0)


def halves():
    sys.modules.setdefault("fac", module("fac"))
    sys.modules.setdefault("agents", module("agents"))
    return module("halves")


def two_heads(tmp: Path) -> tuple[Path, list[str], dict]:
    repo = tmp / "checkout"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    heads = []
    for i in range(2):
        (repo / "f.txt").write_text(f"{i}\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", f"head {i}")
        heads.append(git(repo, "rev-parse", "HEAD"))
    return repo, heads, {"paths": {"run": str(tmp / "run")}, "suites": {"queue_container": False}}


def worktrees(repo: Path) -> int:
    return sum(x.startswith("worktree ") for x in git(repo, "worktree", "list", "--porcelain").splitlines())


@pytest.mark.parametrize(("n", "stacked", "first", "second", "apart"), [
    (2, {}, [0], [1], True),
    (5, {}, [0, 1, 2], [3, 4], True),
    (10, {}, [0, 1, 2, 3, 4], [5, 6, 7, 8, 9], True),
    (4, {1: 0}, [0, 1], [2, 3], True),                          # a pair at the bottom
    (4, {3: 0}, [0, 3], [1, 2], True),                          # a pair apart in the batch, kept together
    (3, {1: 0, 2: 1}, [0, 1], [2], False),                      # one stack: its lower half
    (2, {1: 0}, [0], [1], False),
    (4, {1: 0, 2: 1}, [0, 1, 2], [3], True),                    # a stack past half, never cut while another exists
])
def test_split_keeps_each_stack_whole(n, stacked, first, second, apart):
    near = lambda x, y: stacked.get(x) == y or stacked.get(y) == x      # noqa: E731
    closed = {(x, y) for x in range(n) for y in range(n) if near(x, y)}
    for _ in range(n):
        closed |= {(x, z) for x, y in closed for y2, z in closed if y == y2 and x != z}
    assert halves().split(list(range(n)), lambda x, y: (x, y) in closed) == (first, second, apart)


def test_a_round_returns_each_check_s_result_in_order_and_removes_its_worktrees(tmp_path):
    h = halves()
    repo, heads, cfg = two_heads(tmp_path)

    def check(i: int, wt: Path):
        time.sleep(0.2 * (1 - i))                       # (the last finishes first: order is heads', not theirs)
        if i:
            raise h.fac.Stalled("unit", "its log did not grow", "")
        return git(wt, "rev-parse", "HEAD")
    got = h.run_all(cfg, repo, heads, check, TAG)
    assert got[0] == heads[0] and isinstance(got[1], h.fac.Stalled)            # an exception is never a pass
    assert not list((tmp_path / "run" / "queue-half").iterdir()) and worktrees(repo) == 1
    with pytest.raises(ValueError, match="not 1 to 64"):
        h.run_all(cfg, repo, heads * 33, check, TAG)


def test_a_stopped_round_leaves_no_worktree_or_suite(tmp_path, monkeypatch):
    h = halves()
    repo, heads, cfg = two_heads(tmp_path)
    cfg["suites"] = {"queue_container": False, "unit": "echo $$; exec sleep 30"}
    monkeypatch.delenv("ERGOSTAT_LEASE", raising=False)
    root = tmp_path / "run" / "queue-half"
    root.mkdir(parents=True)
    git(repo, "worktree", "add", "-q", "--detach", str(root / "old-20261121T000000Z-0"), heads[0])  # a SIGKILLed run's
    (root / "keep-me").mkdir()                          # not of the pattern: kept (deleted by allowlist)
    logs = [tmp_path / f"log{i}" for i in range(2)]

    def stop():
        end = time.time() + 20
        while time.time() < end and not all(x.is_file() and x.read_text().strip() for x in logs):
            time.sleep(0.05)
        os.kill(os.getpid(), signal.SIGTERM)
    was = signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))              # (fac.stop_on_term)
    try:
        threading.Thread(target=stop, daemon=True).start()
        with pytest.raises(SystemExit):
            h.run_all(cfg, repo, heads, lambda i, wt: h.fac.suite(cfg, "unit", wt, logs[i], slot=False)[0], TAG)
    finally:
        signal.signal(signal.SIGTERM, was)
    assert not h.fac.SUITES
    for x in logs:                                      # the processes inside are gone
        with pytest.raises(ProcessLookupError):
            os.kill(int(x.read_text().split()[0]), 0)
    assert [x.name for x in root.iterdir()] == ["keep-me"] and worktrees(repo) == 1


def test_stop_suites_of_one_group_leaves_the_other_running(tmp_path):
    h = halves()
    cfg = {"suites": {"queue_container": False, "unit": "exec sleep 30"}}
    mine, other, rc = set(), set(), {}

    def run(name: str, group: set) -> None:
        rc[name] = h.fac.suite(cfg, "unit", tmp_path, tmp_path / f"{name}.txt", slot=False, group=group)[0]
    ts = [threading.Thread(target=run, args=a, daemon=True) for a in (("mine", mine), ("other", other))]
    for t in ts:
        t.start()
    end = time.time() + 10
    while time.time() < end and not (mine and other):
        time.sleep(0.02)
    h.fac.stop_suites(mine)
    ts[0].join(10)
    assert rc["mine"] != 0 and ts[1].is_alive()                                # the other half's suite still runs
    h.fac.stop_suites(other)
    ts[1].join(10)
    assert not ts[1].is_alive()
