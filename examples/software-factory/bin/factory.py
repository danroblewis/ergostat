"""The factory's tools: what support, the product manager, the developer, the reviewer and the
deployer use to do their work. Every step is recorded in ergostat as an event about an item
(ticket/12, pr/7, release/3), so the tickets' stocks and flows are counted from the record.

    factory.py init                     the product's repository (run/product) and production (run/prod)
    factory.py support                  file a bug ticket for each operation customers report broken
    factory.py pm                       file a feature ticket for each operation customers ask for that is missing
    factory.py claim [--as NAME]        take the most urgent open ticket: a working copy to change, and the ticket
    factory.py submit TICKET [--note]   commit the working copy and open a pull request for review
    factory.py review                   the oldest pull request waiting: its ticket, its diff, its tests
    factory.py approve PR [--note]      merge it into main (refused if it no longer merges cleanly)
    factory.py reject PR --why WHY      send its ticket back to the backlog, with why
    factory.py deploy                   put main into production: every merged ticket goes live

The output ends with the line its block reports to ergostat ({"out": "flow.submitted", "moved": 1})."""

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
REPO = RUN / "product"
PROD = RUN / "prod"
WORK = RUN / "work"
WORLD = RUN / "world"
GIT = ["git", "-c", "user.name=factory", "-c", "user.email=factory@example.invalid", "-c", "init.defaultBranch=main",
       "-c", "advice.detachedHead=false"]
ACTIVE = ("open", "doing", "review", "merged")


def ergostat() -> list[str]:
    cmd = os.environ.get("ERGOSTAT_CMD")
    return shlex.split(cmd) if cmd else ["ergostat", "-C", str(ROOT)]


def record(type: str, item: str, data: dict | None = None, by: str = "factory") -> None:
    subprocess.run([*ergostat(), "event", "--add", type, "--item", item, "--data", json.dumps(data or {}), "--as", by],
                   check=True, capture_output=True, text=True)


def tickets() -> list[dict]:
    out = subprocess.run([*ergostat(), "item", "--projection", "ticket", "-n", "1000", "--json"], check=True,
                         capture_output=True, text=True).stdout
    return json.loads(out)["items"]


def item(id: str) -> dict:
    return json.loads(subprocess.run([*ergostat(), "item", id, "--json"], check=True, capture_output=True, text=True).stdout)


def git(*args, cwd: Path = REPO, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True, check=check)


@contextmanager
def lock():
    RUN.mkdir(exist_ok=True)
    with open(RUN / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def next_number(kind: str) -> int:
    path = RUN / "counters.json"
    c = json.loads(path.read_text()) if path.exists() else {}
    c[kind] = c.get(kind, 0) + 1
    path.write_text(json.dumps(c))
    return c[kind]


def moved(flow: str, n: float) -> None:
    print(json.dumps({"out": f"flow.{flow}", "moved": n}))


def say(x) -> None:
    print(x if isinstance(x, str) else json.dumps(x, indent=1), file=sys.stderr if isinstance(x, str) else sys.stdout)


# ---- the product's repository and production

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
        git("commit", "-q", "-m", "textkit as it was handed over")
        git("worktree", "add", "-q", "--detach", str(PROD), "main")
        WORK.mkdir(exist_ok=True)


def tests(where: Path) -> tuple[bool, str]:
    try:
        p = subprocess.run([sys.executable, "test_textkit.py"], cwd=where, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return False, "the tests did not finish in 60s"
    return p.returncode == 0, (p.stdout + p.stderr).strip()[-1500:]


# ---- filing tickets: the product's outcomes become the factory's work

def complaints() -> tuple[dict, dict]:
    c, s = WORLD / "complaints.json", WORLD / "state.json"
    return (json.loads(c.read_text()) if c.exists() else {}), (json.loads(s.read_text()) if s.exists() else {})


def file(kind: str, by: str) -> int:
    """A ticket for each operation customers report (bugs) or ask for (features) that has none
    active. An operation whose fix went live since the world last looked is given time."""
    reported, world = complaints()
    filed = 0
    with lock():
        ts = tickets()
        for op, c in reported.items():
            if (c["kind"] == "missing") != (kind == "feature"):
                continue
            mine = [t for t in ts if t["fields"].get("op") == op]
            if any(t["state"] in ACTIVE for t in mine):
                continue
            if any(t["state"] == "live" and t["entered"] > world.get("at", 0) - 20 for t in mine):
                continue                                    # just deployed: wait for the world to try it
            n = next_number("ticket")
            again = sum(1 for t in mine if t["state"] == "live")
            if kind == "bug":
                title = f"{op} gives {'errors' if c['kind'] == 'error' else 'wrong answers'}" + (" again" if again else "")
                data = {"title": title, "type": "bug", "op": op, "priority": 1, "description": c["description"],
                        "failures": c["examples"], "customers_failed": c["failed"], "regression": bool(again)}
            else:
                sys.path.insert(0, str(ROOT / "world"))
                import oracle
                rank = [f.__name__ for f in oracle.OPS].index(op)
                data = {"title": f"customers want {op}", "type": "feature", "op": op, "priority": 2 + rank // 4,
                        "description": c["description"], "examples": oracle.examples(op), "asked": c["asked"]}
            record("ticket.filed", f"ticket/{n}", data, by)
            filed += 1
    return filed


# ---- the developer

def claim(by: str) -> dict | None:
    init()
    with lock():
        open_ = [t for t in tickets() if t["state"] == "open"]
        if not open_:
            return None
        open_.sort(key=lambda t: (t["fields"].get("type") != "bug", t["fields"].get("priority", 9), t["first"]))
        t = open_[0]
        n = t["id"].split("/")[1]
        branch, wd = f"ticket-{n}", WORK / f"ticket-{n}"
        if wd.exists():
            git("worktree", "remove", "--force", str(wd), check=False)
        git("branch", "-D", branch, check=False)
        git("worktree", "add", "-q", "-b", branch, str(wd), "main")
        record("ticket.started", t["id"], {"developer": by, "branch": branch, "workdir": str(wd)}, by)
    f = t["fields"]
    return {"ticket": t["id"], "type": f.get("type"), "op": f.get("op"), "title": f.get("title"),
            "description": f.get("description"), "examples": f.get("examples"), "failures": f.get("failures"),
            "last_review": f.get("review_note"), "workdir": str(wd),
            "how": f"change textkit.py (and test_textkit.py) in {wd}; python3 test_textkit.py runs the tests; then "
                   f"factory.py submit {t['id']}"}


def submit(ticket: str, note: str, by: str) -> bool:
    n = ticket.split("/")[1]
    wd = WORK / f"ticket-{n}"
    if not wd.exists():
        say(f"no working copy for {ticket}: claim it first")
        return False
    ok, out = tests(wd)
    git("add", "-A", cwd=wd)
    if not git("status", "--porcelain", cwd=wd).stdout.strip():
        say(f"{ticket}: nothing changed in {wd}")
        return False
    git("commit", "-q", "-m", f"{ticket}: {note or 'work for the ticket'}", cwd=wd)
    stat = git("diff", "--shortstat", "main...HEAD", cwd=wd).stdout.strip()
    with lock():
        pr = f"pr/{next_number('pr')}"
    record("pr.opened", pr, {"ticket": ticket, "branch": f"ticket-{n}", "author": by, "tests": "pass" if ok else "fail",
                             "diff": stat, "note": note}, by)
    record("ticket.submitted", ticket, {"pr": pr}, by)
    say(f"{pr} opened for {ticket} ({stat}); tests {'pass' if ok else 'FAIL'}")
    return True


# ---- the reviewer

def waiting() -> dict | None:
    out = subprocess.run([*ergostat(), "item", "--projection", "pr", "--state", "review", "-n", "1000", "--json"], check=True,
                         capture_output=True, text=True).stdout
    prs = sorted(json.loads(out)["items"], key=lambda p: p["first"])
    return prs[0] if prs else None


def review() -> dict | None:
    pr = waiting()
    if pr is None:
        return None
    t = item(pr["fields"]["ticket"])
    wd = WORK / pr["fields"]["branch"]
    ok, out = tests(wd) if wd.exists() else (False, "its working copy is gone")
    diff = git("diff", "main...HEAD", cwd=wd, check=False).stdout if wd.exists() else ""
    f = t["fields"]
    return {"pr": pr["id"], "ticket": t["id"], "title": f.get("title"), "type": f.get("type"), "op": f.get("op"),
            "description": f.get("description"), "examples": f.get("examples"), "failures": f.get("failures"),
            "workdir": str(wd), "tests_pass": ok, "tests": out, "diff": diff[:12000],
            "how": f"read the diff; try it in {wd}; then factory.py approve {pr['id']} or factory.py reject {pr['id']} --why ..."}


def approve(pr: str, note: str, by: str) -> str:
    p = item(pr)
    branch, ticket = p["fields"]["branch"], p["fields"]["ticket"]
    with lock():
        r = git("merge", "--no-ff", "-q", "-m", f"merge {pr} ({ticket})", branch, check=False)
        if r.returncode != 0:
            git("merge", "--abort", check=False)
            why = "it no longer merges cleanly into main: start again from main"
            record("pr.rejected", pr, {"reviewer": by, "why": why}, by)
            record("ticket.rejected", ticket, {"review_note": why, "rework": True}, by)
            return "rejected"
        git("worktree", "remove", "--force", str(WORK / branch), check=False)
    record("pr.merged", pr, {"reviewer": by, "review_note": note}, by)
    record("ticket.merged", ticket, {"pr": pr}, by)
    return "merged"


def reject(pr: str, why: str, by: str) -> None:
    p = item(pr)
    record("pr.rejected", pr, {"reviewer": by, "why": why}, by)
    record("ticket.rejected", p["fields"]["ticket"], {"review_note": why, "rework": True}, by)
    git("worktree", "remove", "--force", str(WORK / p["fields"]["branch"]), check=False)


# ---- the deployer

def deploy(by: str) -> int:
    init()
    with lock():
        ready = [t for t in tickets() if t["state"] == "merged"]
        if not ready:
            return 0
        head = git("rev-parse", "--short", "main").stdout.strip()
        git("checkout", "-q", "--force", "--detach", "main", cwd=PROD)     # production is never edited by hand
        rel = f"release/{next_number('release')}"
    record("release.made", rel, {"commit": head, "tickets": [t["id"] for t in ready]}, by)
    for t in ready:
        record("ticket.deployed", t["id"], {"release": rel}, by)
        if t["fields"].get("pr"):
            record("pr.deployed", t["fields"]["pr"], {"release": rel}, by)
    return len(ready)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["init", "support", "pm", "claim", "submit", "review", "approve", "reject", "deploy"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--as", dest="by", default=os.environ.get("ERGOSTAT_BLOCK", "someone"))
    ap.add_argument("--note", default="")
    ap.add_argument("--why", default="")
    a = ap.parse_args()
    if a.what == "init":
        init()
    elif a.what == "support":
        moved("filed-bugs", file("bug", a.by))
    elif a.what == "pm":
        moved("filed-features", file("feature", a.by))
    elif a.what == "claim":
        t = claim(a.by)
        say(t if t else "nothing open: the backlog is empty")
        if t is None:
            moved("submitted", 0)
    elif a.what == "submit":
        if not a.id:
            ap.error("submit TICKET")
        moved("submitted", 1 if submit(a.id, a.note, a.by) else 0)
    elif a.what == "review":
        r = review()
        say(r if r else "nothing waits for review")
    elif a.what == "approve":
        if not a.id:
            ap.error("approve PR")
        moved(approve(a.id, a.note, a.by), 1)
    elif a.what == "reject":
        if not a.id or not a.why:
            ap.error("reject PR --why WHY")
        reject(a.id, a.why, a.by)
        moved("rejected", 1)
    elif a.what == "deploy":
        moved("deployed", deploy(a.by))
    return 0


if __name__ == "__main__":
    sys.exit(main())
