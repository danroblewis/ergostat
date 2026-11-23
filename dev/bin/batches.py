"""Each merge batch an item, batch/<its run tag> (dev/model/landing.yaml), so ergostat shows what the queue is doing:
which batch runs, which run it is on, and what each run found. queue.py says each step here, and only here. The events
carry no logs (the logs stay in run/queue/):

- `batch.started` (testing): its gaps, the base commit, its size;
- `batch.run-started` (testing) and `batch.run-finished` (isolating) around each run (kind full, named or halves):
  its number, the gaps it covered, its outcome (passed, failed, crashed, stalled), its failed and passed counts (over
  the suites that said them, `counted`), the first failing tests (at most FIRST_MOST), minutes and a crash's cause. The
  runs follow one another (a round of halves is one run), so the Timeline draws one testing bar for each;
- `batch.isolated`: a gap found failing, how (named: its tests on each prefix; halves; alone: a batch of one), the tests;
- `batch.landed` (pushing): the gaps landed, main's commit, the minutes and runs so far;
- `batch.ended.<outcome>` (landed, partial, failed, given-back): what was given back and why. A batch that landed
  something ends when its push settles (queue.settle(): the push ran, was denied, or the coordinator settled it).

A batch killed part way ends given back when the next queue run recovers (abandoned()). A run under way is written to
run/batch.json; `batches.py percent` and `batches.py failures` (the measures
batch-run-percent and batch-run-failures) read that run's own logs, never the record. Every call is guarded: a failure
to say or write anything is dropped and never reaches the merge (a print that fails, a full disk)."""

from __future__ import annotations

import functools
import json
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

FIRST_MOST = 10                                         # failing tests kept on a run's record
OUTCOMES = ("landed", "partial", "failed", "given-back")
NOW: dict = {}                                          # the batch of this queue run (one a process), once begun


def _say(event: str, item: str, **data) -> None:
    fac.say(event, item, **data)


def guarded(f):
    """Never raises (but a stop): the record is evidence, the merge is the work."""
    @functools.wraps(f)
    def g(*a, **k):
        try:
            return f(*a, **k)
        except Exception:  # noqa: BLE001 - a failure to record never fails or delays a merge
            return None
    return g


@guarded
def _mark(**changes) -> None:
    """run/batch.json: the batch, whether it is still `open` (not ended, nor waiting on its push) and whether a run is
    `under_way` (its number, kind, start)."""
    NOW["mark"].update(changes)
    p = fac.run_dir(NOW["cfg"]) / "batch.json"
    tmp = p.with_suffix(".new")
    tmp.write_text(json.dumps(NOW["mark"]))
    tmp.replace(p)


@guarded
def begin(cfg: dict, tag: str, gaps: list[str], pre: str) -> None:
    NOW.clear()
    NOW.update(cfg=cfg, id=f"batch/{tag}", tag=tag, gaps=list(gaps), began=time.time(), runs=0, ended=False,
               mark={"batch": f"batch/{tag}", "tag": tag, "gaps": list(gaps), "began": time.time()})
    _mark(open=True, under_way=False)
    _say("batch.started", NOW["id"], gaps=list(gaps), base=pre, size=len(gaps), started_at=NOW["began"])


@guarded
def abandoned(cfg: dict) -> None:
    """A queue run killed part way (recover(), as it puts main back): the batch it left open ends given back."""
    p = fac.run_dir(cfg) / "batch.json"
    m = json.loads(p.read_text()) if p.exists() else {}
    if not m.get("open"):
        return
    NOW.clear()
    NOW.update(cfg=cfg, id=m["batch"], tag=m["tag"], gaps=list(m["gaps"]), began=float(m["began"]),
               runs=int(m.get("run") or 0), ended=False, mark=m)
    end("given-back", "its queue run was stopped part way (killed or crashed): main put back")
    NOW.clear()


@guarded
def _start(kind: str, gaps: list[str]) -> int:
    NOW["runs"] += 1
    n, at = NOW["runs"], time.time()
    _say("batch.run-started", NOW["id"], run=n, run_kind=kind, run_gaps=list(gaps), run_started_at=at)
    _mark(run=n, kind=kind, at=at, under_way=True)
    return n


def _one(r, kind: str) -> tuple:
    """(outcome, failed, passed, counted, tests, crash) of one result: suites()'s, named()'s, or an exception."""
    if isinstance(r, BaseException):
        return ("stalled" if type(r).__name__ == "Stalled" else "crashed"), 0, 0, [], [], f"{type(r).__name__}: {r}"[:300]
    if r is None:                                       # (a named check that could not tell: never a pass)
        return "crashed", 0, 0, [], [], "the named check could not tell"
    if kind == "named":
        asked = int((r.get("named") or {}).get("tests") or 0)
        bad = len(r.get("tests") or []) if r.get("failed") else 0
        return ("failed" if bad else "passed"), bad, asked - bad, ["named"], list(r.get("tests") or []) if bad else [], ""
    counted = [n for n in ("unit", "browser", "host") if isinstance((r.get(n) or {}).get("counts"), dict)]
    out = "crashed" if r.get("crashed") else "failed" if r.get("failed") else "passed"
    return (out, sum(r[n]["counts"].get("failed", 0) + r[n]["counts"].get("errors", 0) for n in counted),
            sum(r[n]["counts"].get("passed", 0) for n in counted), counted, list(r.get("tests") or []),
            r.get("crashed") or "")


@guarded
def _finish(n: int, kind: str, gaps: list[str], seen: list, at: float) -> None:
    got = [_one(r, kind) for r in seen if r != {}] or [("crashed", 0, 0, [], [], "the run said nothing")]
    outcome = next((o for o in ("failed", "crashed", "stalled") if any(x[0] == o for x in got)), "passed")
    tests = list(dict.fromkeys(t for x in got for t in x[4]))[:FIRST_MOST]
    crash = next((x[5] for x in got if x[5]), "")
    rec = {"run": n, "kind": kind, "gaps": list(gaps), "outcome": outcome, "failed": sum(x[1] for x in got),
           "passed": sum(x[2] for x in got), "counted": sorted({c for x in got for c in x[3]}), "first_failing": tests,
           "minutes": round((time.time() - at) / 60, 1), **({"crash": crash} if crash else {})}
    _mark(under_way=False)
    _say("batch.run-finished", NOW["id"], runs=[rec], run=n, outcome=outcome)


@contextmanager
def run(kind: str, gaps: list[str]):
    """One run of the batch (full, named or halves): the caller puts what it returned in the list given (a half's or a
    prefix's each); an exception out of it is the run's outcome too, and goes on."""
    if not NOW:
        yield []
        return
    seen: list = []
    at, n = time.time(), _start(kind, gaps)
    try:
        yield seen
    except BaseException as e:
        seen.append(e)
        raise
    finally:
        if n:
            _finish(n, kind, gaps, seen, at)


@guarded
def isolated(gap: str, how: str, tests: list[str]) -> None:
    if NOW:
        _say("batch.isolated", NOW["id"], isolated=[{"gap": gap, "how": how, "tests": list(tests)[:FIRST_MOST]}])


@guarded
def settled(landed: list[str], sha: str, back: list[tuple[str, str]]) -> None:
    """land() returned: what landed (the batch then waits on its push), or nothing (it ends now)."""
    if not NOW:
        return
    out = set(landed) | {g for g, _ in back}
    NOW.update(failed=[g for g in NOW["gaps"] if g not in out], back=[{"gap": g, "why": w} for g, w in back])
    if landed:
        NOW["outcome"] = "landed" if len(landed) == len(NOW["gaps"]) else "partial"
        _say("batch.landed", NOW["id"], landed=list(landed), main_sha=sha, runs_n=NOW["runs"], minutes=_minutes())
    else:
        end("failed" if NOW["failed"] else "given-back", "nothing landed")


def _minutes() -> float:
    return round((time.time() - NOW["began"]) / 60, 1)


@guarded
def end(outcome: str, why: str) -> None:
    """The batch ended with nothing landed (the first end said wins: a stall, main red, an error, a stop)."""
    if not NOW or NOW["ended"]:
        return
    NOW["ended"] = True
    back = NOW.get("back")
    back = back if back is not None else [{"gap": g, "why": why} for g in NOW["gaps"]]
    _mark(open=False, under_way=False)
    _said(NOW["id"], outcome, why, back, NOW.get("failed") or [], _minutes(), NOW["runs"])


def _said(bid: str, outcome: str, why: str, back: list, failed: list, minutes: float, runs: int) -> None:
    _say(f"batch.ended.{outcome}", bid, outcome=outcome, why=why, given_back=back, failed=failed,
         minutes=minutes, runs_n=runs, ended_at=time.time())


@guarded
def pending() -> dict | None:
    """What the batch ends with once its push settles, kept in run/queue.json's pending push (queue.ask())."""
    if not NOW or NOW["ended"] or not NOW.get("outcome"):
        return None
    NOW["ended"] = True
    _mark(open=False, under_way=False)                  # (its push's settling ends it: queue.settle())
    return {"id": NOW["id"], "outcome": NOW["outcome"], "given_back": NOW["back"], "failed": NOW["failed"],
            "began": NOW["began"], "runs": NOW["runs"]}


@guarded
def pushed(b: dict | None, push: str) -> None:
    """The push of a batch's landed merges settled: ran (its outcome), denied (failed: the merges undone, its gaps
    sent back), or settled by the coordinator."""
    if not isinstance(b, dict) or b.get("outcome") not in OUTCOMES:
        return
    outcome = "failed" if push == "denied" else b["outcome"]
    _said(b["id"], outcome, f"its push {push}", b.get("given_back") or [], b.get("failed") or [],
          round((time.time() - float(b.get("began") or time.time())) / 60, 1), int(b.get("runs") or 0))


# ---- the measures: the run under way, from its own logs

PERCENT = re.compile(r"\[\s*(\d{1,3})%\]\s*$", re.M)
PROGRESS = re.compile(r"^([.FEsxX]+)\s*\[\s*\d{1,3}%\]\s*$", re.M)
LOGS = re.compile(r"-(unit|browser|host|named)\.txt$")


def progress(cfg: dict) -> tuple[int, int]:
    """(percent through, failures so far) of the run under way: the least advanced of its pytest logs, and the F and E
    in their progress lines. No run under way (no queue run, or its run finished): (0, 0). An unreadable file raises:
    the measure has no value then, never a 0 (lesson-3)."""
    st = fac.run_dir(cfg) / "queue.json"
    if not st.exists() or not json.loads(st.read_text()).get("running"):
        return 0, 0
    b = fac.run_dir(cfg) / "batch.json"
    if not b.exists():
        return 0, 0
    now = json.loads(b.read_text())
    if not now.get("under_way") or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}-\d{8}T\d{6}Z", str(now.get("tag") or "")):
        return 0, 0
    logs = [p for p in Path(fac.run_dir(cfg, "queue")).glob(f"{now['tag']}*.txt")
            if LOGS.search(p.name) and p.stat().st_mtime >= float(now["at"]) - 1]
    texts = [p.read_text(errors="replace") for p in logs]
    done = [100 if fac.counts(t) is not None else int(m[-1]) if (m := PERCENT.findall(t)) else 0 for t in texts]
    return (min(done) if done else 0), sum(x.count("F") + x.count("E") for t in texts for x in PROGRESS.findall(t))


if __name__ == "__main__":
    which = sys.argv[1:2]
    if which not in (["percent"], ["failures"]):
        sys.exit("batches.py percent | failures")
    print(progress(fac.config())[which == ["failures"]])
