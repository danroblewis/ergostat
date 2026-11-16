"""The lab's tools: what the researcher, the developer, the tuner, the matcher and the rollout use.
Every step is recorded in ergostat as an event about an item (hypothesis/3, release/2), so the
experiments' stocks and flows are counted from the record.

    lab.py init                       squeeze's repository (run/product) and production (run/prod)
    lab.py propose TITLE --idea TEXT [--key KEY]
                                      file a hypothesis
    lab.py history                    every hypothesis so far, and what its experiment measured
    lab.py claim                      take the oldest proposed hypothesis (or the one left half built): a working copy, and the idea
    lab.py test HYPOTHESIS            run squeeze's tests in that hypothesis's working copy
    lab.py bench HYPOTHESIS           run the benchmark on it: cases met, gained and lost against production
    lab.py submit HYPOTHESIS          test the working copy; if its tests pass, it becomes the candidate
    lab.py abandon HYPOTHESIS --why   give up on it (it cannot be built)
    lab.py tune                       the tuner: move production's quality toward the quality goal
    lab.py match                      the matcher: move the candidate's quality until it looks as good as production
    lab.py rollout                    the rollout: give the candidate more traffic, keep it, or roll it back

The last line each prints is what its block reports to ergostat (JSON)."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shlex
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "run"
REPO, PROD, CAND, WORK = RUN / "product", RUN / "prod", RUN / "candidate", RUN / "work"
GIT = ["git", "-c", "user.name=lab", "-c", "user.email=lab@example.invalid", "-c", "init.defaultBranch=main",
       "-c", "advice.detachedHead=false"]

TIME_BUDGET = 120.0       # ms, 95th percentile: a candidate slower than this is rolled back
STAGES = [0.05, 0.25, 0.5, 1.0]
PAIRS_PER_STAGE = 30      # images compared at a stage before it moves on
GIVE_UP_AFTER = 240       # images compared with no clear answer: no measurable difference


def ergostat() -> list[str]:
    cmd = os.environ.get("ERGOSTAT_CMD")
    return shlex.split(cmd) if cmd else ["ergostat", "-C", str(ROOT)]


def record(type: str, item: str, data: dict | None = None, by: str = "lab") -> None:
    subprocess.run([*ergostat(), "event", "--add", type, "--item", item, "--data", json.dumps(data or {}), "--as", by],
                   check=True, capture_output=True, text=True)


def items(kind: str, state: str | None = None) -> list[dict]:
    args = [*ergostat(), "item", "--kind", kind, "-n", "1000", "--json"] + (["--state", state] if state else [])
    return json.loads(subprocess.run(args, check=True, capture_output=True, text=True).stdout)["items"]


def git(*args, cwd: Path = REPO, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True, check=check)


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


@contextmanager
def lock():
    RUN.mkdir(exist_ok=True)
    with open(RUN / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def number(kind: str) -> int:
    c = load(RUN / "counters.json", {})
    c[kind] = c.get(kind, 0) + 1
    save(RUN / "counters.json", c)
    return c[kind]


def say(x) -> None:
    print(x if isinstance(x, str) else json.dumps(x, indent=1), file=sys.stderr if isinstance(x, str) else sys.stdout)


# ---- the product

def init() -> None:
    with lock():
        if (REPO / ".git").exists():
            return
        REPO.mkdir(parents=True, exist_ok=True)
        for f in (ROOT / "seed").iterdir():
            if f.suffix == ".py":
                shutil.copy2(f, REPO / f.name)
        shutil.copy2(ROOT / "seed" / "gitignore", REPO / ".gitignore")
        git("init", "-q")
        git("add", "-A")
        git("commit", "-q", "-m", "squeeze as it was handed over")
        git("worktree", "add", "-q", "--detach", str(PROD), "main")
        WORK.mkdir(exist_ok=True)
        save(RUN / "settings.json", {"quality": 80})
        save(RUN / "rollout.json", {"candidate": None, "share": 0.0, "offset": 0})


def tests(where: Path) -> tuple[bool, str]:
    py = str(ROOT / "bin" / "py")
    try:
        p = subprocess.run([py, "test_squeeze.py"], cwd=where, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "the tests did not finish in 120s"
    return p.returncode == 0, (p.stdout + p.stderr).strip()[-1500:]


# ---- hypotheses

def propose(title: str, idea: str, key: str | None, by: str) -> str:
    with lock():
        hid = f"hypothesis/{number('hypothesis')}"
    record("hypothesis.proposed", hid, {"title": title, "idea": idea, **({"key": key} if key else {}), "by": by}, by)
    return hid


def history() -> list[dict]:
    return [{"id": h["id"], "state": h["state"], "title": h["fields"].get("title"), "idea": h["fields"].get("idea"),
             "result": h["fields"].get("result")} for h in sorted(items("hypothesis"), key=lambda h: h["first"])]


def claim(by: str) -> dict | None:
    init()
    with lock():
        if items("hypothesis", "testing"):
            return None                                       # one experiment at a time: there is one candidate slot
        half = items("hypothesis", "building")               # a session that ended before submitting: carry on with it
        if half:
            h = half[0]
            n = h["id"].split("/")[1]
            wd = WORK / f"hypothesis-{n}"
            if wd.exists():
                record("hypothesis.resumed", h["id"], {"developer": by}, by)
                f = h["fields"]
                return {"hypothesis": h["id"], "title": f.get("title"), "idea": f.get("idea"), "key": f.get("key"),
                        "workdir": str(wd), "resumed": True,
                        "how": f"a session before you started this and did not submit it: its changes are in {wd}. Finish them; "
                               f"bin/py bin/lab.py test {h['id']} runs the tests; then bin/py bin/lab.py submit {h['id']}"}
        waiting = sorted(items("hypothesis", "proposed"), key=lambda h: h["first"])
        if not waiting:
            return None
        h = waiting[0]
        n = h["id"].split("/")[1]
        branch, wd = f"hypothesis-{n}", WORK / f"hypothesis-{n}"
        if wd.exists():
            git("worktree", "remove", "--force", str(wd), check=False)
        git("branch", "-D", branch, check=False)
        git("worktree", "add", "-q", "-b", branch, str(wd), "main")
        record("hypothesis.started", h["id"], {"developer": by, "branch": branch}, by)
    f = h["fields"]
    return {"hypothesis": h["id"], "title": f.get("title"), "idea": f.get("idea"), "key": f.get("key"), "workdir": str(wd),
            "how": f"change squeeze.py (and test_squeeze.py) in {wd}; bin/py bin/lab.py test {h['id']} runs its tests; "
                   f"then bin/py bin/lab.py submit {h['id']}"}


def submit(hid: str, note: str, by: str) -> str:
    n = hid.split("/")[1]
    wd = WORK / f"hypothesis-{n}"
    if not wd.exists():
        return "no working copy: claim it first"
    git("add", "-A", cwd=wd)
    if not git("status", "--porcelain", cwd=wd).stdout.strip():
        abandon(hid, "nothing was changed", by)
        return "abandoned: nothing changed"
    git("commit", "-q", "-m", f"{hid}: {note or 'the experiment'}", cwd=wd)
    ok, report = tests(wd)
    if not ok:
        abandon(hid, "its tests fail: " + report.splitlines()[-1] if report else "its tests fail", by)
        return "abandoned: tests fail"
    bench = benchmark(wd)
    with lock():
        if CAND.exists():
            shutil.rmtree(CAND)
        shutil.copytree(wd, CAND, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        save(RUN / "rollout.json", {"candidate": hid, "share": 0.0, "offset": 0, "stage": -1, "since": 0, "benchmark": bench})
    record("hypothesis.testing", hid, {"note": note, "diff": git("diff", "--shortstat", "main...HEAD", cwd=wd).stdout.strip(),
                                       "benchmark": bench}, by)
    return "testing"


def benchmark(build: Path) -> dict:
    """The candidate on the benchmark, against production's last measurement: cases gained and lost."""
    try:
        p = subprocess.run([str(ROOT / "bin" / "py"), str(ROOT / "world" / "benchmark.py"), str(build)], capture_output=True,
                           text=True, timeout=600)
        now = json.loads(p.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        return {"error": "the benchmark did not finish"}
    prod = load(RUN / "world" / "benchmark.json", {"cases": {}})
    pc = prod.get("cases", {})
    return {"met": now.get("met"), "of": now.get("of"), "score": now.get("score"), "production_met": prod.get("met"),
            "production_score": prod.get("score"),
            "gained": sorted(c for c, x in now.get("cases", {}).items() if x.get("met") and not pc.get(c, {}).get("met")),
            "lost": sorted(c for c, x in now.get("cases", {}).items() if not x.get("met") and pc.get(c, {}).get("met")),
            **({"error": now["error"]} if now.get("error") else {})}


def abandon(hid: str, why: str, by: str) -> None:
    record("hypothesis.dropped", hid, {"result": {"verdict": "not built", "why": why}}, by)
    git("worktree", "remove", "--force", str(WORK / f"hypothesis-{hid.split('/')[1]}"), check=False)


# ---- the loops

def tune(ctx: dict) -> float:
    """Integral control: production's quality setting moves by the quality error each time, so it
    settles where the measured quality meets the setpoint whatever the mix (no steady error)."""
    s = load(RUN / "settings.json", {"quality": 80})
    q = float(s.get("quality", 80))
    g = (ctx.get("goals") or {}).get("quality-held") or {}
    y = g.get("value")
    if y is None or not g.get("hold"):
        return q
    r = float(str(g["hold"]).split()[-1])                    # the setpoint, as ergostat.yaml's goal says ("== 0.93")
    e = r - float(y)                                         # e = r − y: positive when it looks too poor
    if abs(e) > 0.004:                                       # a dead band: hold steady inside the tolerance
        q = max(5.0, min(95.0, q + 350 * e))
    s["quality"] = round(q, 1)
    save(RUN / "settings.json", s)
    return q


def match() -> float:
    """The candidate's own quality setting (production's plus an offset), raised until the candidate
    looks as good as production on the same images, so a change that saves bytes by looking worse
    is compared at equal quality. It is only ever raised (and let back down to 0): a candidate that
    looks better is not made to look worse to match, because its gain may be all on one kind of
    image, and spending it would make every other kind worse."""
    r = load(RUN / "rollout.json", {})
    st = load(RUN / "world" / "state.json", {})
    c = st.get("candidate") or {}
    if not r.get("candidate") or c.get("id") != r.get("candidate") or c.get("paired", 0) < 10:
        return float(r.get("offset") or 0)
    dq = float(c.get("quality_mean") or 0)                   # candidate − production, recent images
    off = float(r.get("offset") or 0)
    if dq < -0.004 or (dq > 0.004 and off > 0):
        new = max(0.0, min(40.0, off - 350 * dq))            # looks worse: raise it; better again: let it back down
        r["offset"] = round(new, 1)
        if abs(new - off) >= 2:                              # a real move: compare from here on
            r["matched_since"] = c.get("paired", 0)
        save(RUN / "rollout.json", r)
        off = new
    return off


def rollout(by: str) -> dict:
    """Progressive delivery as a feedback loop. While the candidate is no worse (no failures, in
    time, matched quality), more images go to it, stage by stage; when it saves bytes at equal
    quality with confidence at full share, it becomes production; when it fails, is slow, cannot
    match production's quality, or shows no difference after enough images, it is rolled back."""
    r = load(RUN / "rollout.json", {})
    st = load(RUN / "world" / "state.json", {})
    hid, c = r.get("candidate"), st.get("candidate") or {}
    if not hid or c.get("id") != hid:
        return {"share": 0.0, "kept": 0, "dropped": 0}
    lo, hi = c.get("bytes_saved", [0, 0])
    n, since = int(c.get("paired", 0)), int(r.get("matched_since", 0))
    dq = float(c.get("quality_mean", 0))
    # compared at equal or better quality: what the matcher is for
    matched = n - since >= 20 and dq >= -0.006
    looks_better = dq > 0.006
    better = matched and (lo > 0.5 or (looks_better and lo > -3))   # fewer bytes, or better looking for about the same
    worse = [f"{k}: {v['saved']:+.0f}% bytes, {v['quality_change']:+.3f} SSIM" for k, v in (c.get("by_kind") or {}).items()
             if v.get("n", 0) >= 6 and (v["saved"] < -25 or v["quality_change"] < -0.02)]   # a guardrail on every kind
    bench = r.get("benchmark") or {}
    verdict = None
    if bench.get("lost"):                                    # a regression on the benchmark: what it could do, it cannot
        verdict = ("dropped", f"loses benchmark cases production meets: {', '.join(bench['lost'])}")
    elif c.get("failures"):
        verdict = ("dropped", f"failed on {c['failures']} images")
    elif n >= 20 and c.get("time", 0) > TIME_BUDGET:
        verdict = ("dropped", f"too slow: {c['time']} ms at the 95th percentile (the budget is {TIME_BUDGET:g})")
    elif r.get("offset", 0) >= 40 and dq < -0.006:
        verdict = ("dropped", "it cannot look as good as production at any quality")
    elif matched and hi < 0 and not looks_better:
        verdict = ("dropped", f"more bytes at equal quality: {lo:.1f}% to {hi:.1f}% saved")
    elif n - since >= 20 and worse:
        verdict = ("dropped", "much worse for some images (" + "; ".join(worse) + ")")
    elif n >= GIVE_UP_AFTER and not better:
        verdict = ("dropped", f"no clear difference after {n} images ({lo:.1f}% to {hi:.1f}% saved)")
    stage = int(r.get("stage", -1))
    if verdict is None and better:
        if stage + 1 < len(STAGES) and n >= (stage + 2) * PAIRS_PER_STAGE:
            stage += 1                                       # better so far: give it more of the traffic
        elif stage == len(STAGES) - 1 and n >= (len(STAGES) + 1) * PAIRS_PER_STAGE:
            verdict = ("kept", f"better looking (+{dq:.3f} SSIM) for {lo:.1f}% to {hi:.1f}% fewer bytes" if looks_better
                       else f"{lo:.1f}% to {hi:.1f}% fewer bytes at equal quality")
    result = {"bytes_saved": [lo, hi], "quality_offset": r.get("offset", 0), "paired": n, "by_kind": c.get("by_kind"),
              "benchmark": bench}
    if verdict and verdict[0] == "kept":
        promote(hid, {**result, "verdict": "kept", "why": verdict[1]}, by)
        return {"share": 0.0, "kept": 1, "dropped": 0}
    if verdict:
        rollback(hid, {**result, "verdict": "dropped", "why": verdict[1]}, by)
        return {"share": 0.0, "kept": 0, "dropped": 1}
    share = STAGES[stage] if stage >= 0 else 0.0
    if share != r.get("share") or stage != r.get("stage"):
        r.update(share=share, stage=stage)
        save(RUN / "rollout.json", r)
        record("hypothesis.rollout", hid, {"share": share, "bytes_saved": [lo, hi], "paired": n}, by)
    return {"share": share, "kept": 0, "dropped": 0}


def promote(hid: str, result: dict, by: str) -> None:
    n = hid.split("/")[1]
    with lock():
        git("merge", "--no-ff", "-q", "-m", f"keep {hid}", f"hypothesis-{n}")
        git("checkout", "-q", "--force", "--detach", "main", cwd=PROD)
        s = load(RUN / "settings.json", {"quality": 80})     # production now runs at the quality the candidate matched with
        s["quality"] = max(5.0, min(95.0, float(s.get("quality", 80)) + float(result.get("quality_offset", 0))))
        save(RUN / "settings.json", s)
        shutil.rmtree(CAND, ignore_errors=True)
        save(RUN / "rollout.json", {"candidate": None, "share": 0.0, "offset": 0})
        git("worktree", "remove", "--force", str(WORK / f"hypothesis-{n}"), check=False)
        rel = f"release/{number('release')}"
    record("hypothesis.kept", hid, {"result": result}, by)
    record("release.made", rel, {"hypothesis": hid, "commit": git("rev-parse", "--short", "main").stdout.strip()}, by)


def rollback(hid: str, result: dict, by: str) -> None:
    n = hid.split("/")[1]
    with lock():
        shutil.rmtree(CAND, ignore_errors=True)
        save(RUN / "rollout.json", {"candidate": None, "share": 0.0, "offset": 0})
        git("worktree", "remove", "--force", str(WORK / f"hypothesis-{n}"), check=False)
    record("hypothesis.dropped", hid, {"result": result}, by)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["init", "propose", "history", "claim", "test", "bench", "submit", "abandon", "tune", "match",
                                     "rollout"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--idea", default="")
    ap.add_argument("--key")
    ap.add_argument("--note", default="")
    ap.add_argument("--why", default="")
    ap.add_argument("--as", dest="by", default=os.environ.get("ERGOSTAT_BLOCK", "someone"))
    a = ap.parse_args()
    if a.what == "init":
        init()
    elif a.what == "propose":
        if not a.arg:
            ap.error("propose TITLE --idea TEXT")
        say(propose(a.arg, a.idea, a.key, a.by))
        print(json.dumps({"out": "flow.proposed", "moved": 1}))
    elif a.what == "history":
        say(history())
    elif a.what == "claim":
        h = claim(a.by)
        say(h if h else "nothing to start: no hypothesis is waiting, or an experiment is already running")
        print(json.dumps({"out": "flow.started", "moved": 1 if h and not h.get("resumed") else 0}))
    elif a.what == "test":
        wd = WORK / f"hypothesis-{(a.arg or '').split('/')[-1]}"
        if not a.arg or not wd.exists():
            ap.error("test HYPOTHESIS (one that has been claimed)")
        ok, report = tests(wd)
        print(report)
        return 0 if ok else 1
    elif a.what == "bench":
        wd = WORK / f"hypothesis-{(a.arg or '').split('/')[-1]}"
        if not a.arg or not wd.exists():
            ap.error("bench HYPOTHESIS (one that has been claimed)")
        say(benchmark(wd))
    elif a.what == "submit":
        got = submit(a.arg, a.note, a.by)
        say(got)
        print(json.dumps({"out": "flow.abandoned" if got.startswith("abandoned") else "flow.submitted",
                          "moved": 0 if got.startswith("no working copy") else 1}))
    elif a.what == "abandon":
        abandon(a.arg, a.why or "given up", a.by)
        print(json.dumps({"out": "flow.abandoned", "moved": 1}))
    elif a.what == "tune":
        ctx = json.loads(sys.stdin.read() or "{}")
        print(json.dumps({"out": "variable.quality-setting", "value": tune(ctx)}))
    elif a.what == "match":
        sys.stdin.read()
        print(json.dumps({"out": "variable.candidate-offset", "value": match()}))
    elif a.what == "rollout":
        sys.stdin.read()
        r = rollout(a.by)
        print(json.dumps({"out": "variable.rollout-share", "value": r["share"]}))
        print(json.dumps({"out": "flow.kept", "moved": r["kept"]}))
        print(json.dumps({"out": "flow.dropped", "moved": r["dropped"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
