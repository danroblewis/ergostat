"""What the factory's programs share: its settings, git, the record, the cost ledger and the daily cap, the load
interlock's wait, and one AI session (Claude Code, or the free stand-in).

Every program here is run by ergostat in the model's folder (the instance's folder, ~/ergostat-live/instance, or a
checkout), and fails hard: an error it cannot handle raises, and its run fails."""

from __future__ import annotations

import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import tomllib
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # dev/
MODEL = Path.cwd()                                     # the model's folder: ergostat runs every block there
TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
DEFS = "docs/roadmap/overnight"


# ---- settings

def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def config() -> dict:
    """dev/factory.toml (or FACTORY_CONFIG), then factory.local.toml in the model's folder over it."""
    path = Path(os.environ.get("FACTORY_CONFIG") or HERE / "factory.toml")
    cfg = tomllib.loads(path.read_text())
    local = MODEL / "factory.local.toml"
    if local.is_file():
        cfg = _merge(cfg, tomllib.loads(local.read_text()))
    return cfg


def path(cfg: dict, key: str) -> Path:
    p = Path(os.path.expanduser(cfg["paths"][key]))
    return p if p.is_absolute() else MODEL / p


def run_dir(cfg: dict, *parts: str) -> Path:
    d = path(cfg, "run").joinpath(*parts)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---- the record

def say(event: str, item: str | None = None, **data) -> None:
    """One event line, taken by ergostat as it is printed (about the run's own item when ``item`` is None)."""
    line = {"event": event, "data": data}
    if item:
        line["item"] = item
    print(json.dumps(line, default=str), flush=True)


def nack(why: str, after: str | None = None, count: bool = True) -> None:
    n = {"why": why[:500], "count": count}
    if after:
        n["after"] = after
    print(json.dumps({"nack": n}), flush=True)


def ergostat(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """$ERGOSTAT_CMD (this ergostat, on this model). Absent outside a run: a FileNotFoundError says so."""
    cmd = os.environ.get("ERGOSTAT_CMD")
    if not cmd:
        raise FileNotFoundError("ERGOSTAT_CMD is not set: not run by ergostat")
    r = subprocess.run([*shlex.split(cmd), *args], capture_output=True, text=True, timeout=300)
    if check and r.returncode:
        raise RuntimeError(f"ergostat {' '.join(args)}: exit {r.returncode}: {(r.stderr or r.stdout)[-400:]}")
    return r


_renewed = [0.0]


def renew(every: float = 60.0) -> None:
    """Keep the run's lease while it waits (a lock, a busy machine, a long session), at most once a minute; nothing
    outside a run."""
    if os.environ.get("ERGOSTAT_CMD") and os.environ.get("ERGOSTAT_LEASE") and time.time() - _renewed[0] >= every:
        _renewed[0] = time.time()
        ergostat("lease", "--renew", check=False)


@contextmanager
def renewing(every: float = 300.0):
    """Renew the lease from a thread of its own while the body runs (an AI session that prints nothing for an hour)."""
    done = threading.Event()

    def beat():
        while not done.wait(every):
            renew(0)
    t = threading.Thread(target=beat, daemon=True)
    t.start()
    try:
        yield
    finally:
        done.set()


def items(kind: str, state: str | None = None) -> list[dict]:
    """The items of a kind (in a state), from the record (at most 5,000: the factory's kinds are small)."""
    args = ["item", "--kind", kind, "--json", "-n", "5000"] + (["--state", state] if state else [])
    return json.loads(ergostat(*args).stdout).get("items", [])


def act(name: str, key: str, **args) -> tuple[int, str]:
    """Ask for a gated action ($ERGOSTAT_CMD act); (exit, what it said): 0 ran, 1 failed, 3 held, 4 denied, 2 refused."""
    a = ["act", name, "--key", key] + [x for k, v in args.items() for x in ("--arg", f"{k}={v}")]
    r = ergostat(*a, check=False)
    return r.returncode, (r.stdout + r.stderr).strip()[-600:]


# ---- git

def git(repo: Path, *args: str, check: bool = True) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env, timeout=600)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {r.stderr.strip()[-400:]}")
    return r.stdout.strip()


def git_ok(repo: Path, *args: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=600).returncode == 0


def commit_all(repo: Path, message: str) -> bool:
    """Commit whatever is changed (never a stash); False when nothing was."""
    git(repo, "add", "-A")
    if git_ok(repo, "diff", "--cached", "--quiet"):
        return False
    git(repo, "commit", "-q", "-m", f"{message}\n\n{TRAILER}")
    return True


def slug(text: str, most: int = 0) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if most and len(s) > most:
        s = s[:most].rsplit("-", 1)[0] or s[:most]
    return s


def branch_of(gap: dict) -> str:
    return gap["fields"].get("branch") or slug(gap["id"].split("/", 1)[1], 32)


def net_lines(repo: Path, base: str, head: str) -> int:
    """Net lines of ergostat's core changed: outside tests/, docs/, dev/ and the root model."""
    add = rem = 0
    out = git(repo, "diff", "--numstat", f"{base}...{head}", "--", ".", ":(exclude)tests", ":(exclude)docs",
              ":(exclude)dev", ":(exclude)ergostat.yaml")
    for line in out.splitlines():
        a, d, _ = line.split("\t", 2)
        if a != "-":
            add, rem = add + int(a), rem + int(d)
    return add - rem


def budget_of(definition: str, default: int = 600) -> int:
    m = re.search(r"^## Size budget.*?$(.*?)(?=^## |\Z)", definition, re.M | re.S)
    nums = re.findall(r"(\d[\d,]*)\s*(?:net )?lines", m.group(1)) if m else []
    return int(nums[0].replace(",", "")) if nums else default


# ---- the daily cap, which fails closed

CAP = re.compile(r"^\s*ai-budget:\s*$.*?^\s*hold:\s*\"<=\s*([\d.]+)\"", re.M | re.S)


def daily_cap() -> float:
    """The goal ai-budget's setpoint in dev/model/budget.yaml: the one place the cap is written."""
    m = CAP.search((HERE / "model" / "budget.yaml").read_text())
    if not m:
        raise RuntimeError("no ai-budget goal with a hold in dev/model/budget.yaml")
    return float(m.group(1))


def spent_today(cfg: dict) -> float:
    """Dollars the factory's sessions cost over the last 24 hours, from its ledger. An unreadable line raises."""
    ledger = run_dir(cfg) / "costs.jsonl"
    if not ledger.exists():
        return 0.0
    since, total = time.time() - 86400, 0.0
    for line in ledger.read_text().splitlines():
        if line.strip():
            e = json.loads(line)
            if float(e["at"]) >= since:
                total += float(e["usd"])
    return total


def may_spend(cfg: dict, usd: float) -> str | None:
    """None when a session that may cost ``usd`` fits under the day's cap; else why not. Fails closed: a cap or a
    ledger that cannot be read refuses."""
    try:
        cap, spent = daily_cap(), spent_today(cfg)
    except Exception as e:  # noqa: BLE001 - any failure to know the spend refuses the session
        return f"the day's spend cannot be told ({type(e).__name__}: {e}); refusing"
    if spent + usd > cap:
        return f"${spent:.2f} spent in the last day; a session of up to ${usd:.2f} would pass the ${cap:g} cap"
    return None


def record_cost(cfg: dict, usd: float, **what) -> None:
    with (run_dir(cfg) / "costs.jsonl").open("a") as f:
        f.write(json.dumps({"at": time.time(), "usd": round(usd, 4), **what}) + "\n")


# ---- the load interlock

SUITE = re.compile(r"^[^ ]*python[0-9.]* -m pytest")


def suites_running() -> int:
    """Suites running now, but for one this process runs inside (a test of the factory itself)."""
    out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True, timeout=30).stdout
    rows = {int(p): (int(pp), c) for p, pp, c in (line.split(None, 2) for line in out.splitlines() if line.strip()
                                                  and len(line.split(None, 2)) == 3)}
    mine, p = set(), os.getpid()
    while p in rows and p not in mine:
        mine.add(p)
        p = rows[p][0]
    return sum(1 for pid, (_, cmd) in rows.items() if pid not in mine and SUITE.match(cmd.strip()))


def wait_quiet(cfg: dict, why: str = "") -> float:
    """Wait until no suite runs on this machine (the coordinator's, another block's), renewing the lease; the
    seconds waited."""
    began, poll = time.time(), float(cfg["load"]["wait_poll"])
    while cfg["load"].get("wait", True) and suites_running():
        renew()
        time.sleep(poll)
    return time.time() - began


@contextmanager
def queue_lock(cfg: dict):
    """The queue's lock: the same file the coordinator's queue-fast.sh takes, so the two never run at once."""
    p = path(cfg, "queue_lock")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                renew()
                time.sleep(10)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def suite(cfg: dict, name: str, cwd: Path, log: Path, **fmt) -> tuple[int, float]:
    """One of [suites] in cwd, its output to log; (exit, seconds). Run by the shell, as the coordinator does."""
    cmd = cfg["suites"][name].format(**fmt)
    began = time.time()
    with log.open("w") as out:
        p = subprocess.Popen(cmd, shell=True, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        while p.poll() is None:
            renew()
            try:
                p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                pass
    return p.returncode, time.time() - began


FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)", re.M)


def failed_tests(text: str) -> list[str]:
    return sorted(set(FAILED.findall(text)))


# ---- an AI session

def session(cfg: dict, role: str, brief: str, cwd: Path, tools: list[str], never: list[str]) -> dict:
    """One headless session on the brief, in cwd: Claude Code (claude -p) or the stand-in. Returns its result
    message (Claude Code's JSON: result, total_cost_usd, usage, ...), and prints it, so the run is charged with it."""
    model, usd = cfg["ai"][f"{role}_model"], float(cfg["ai"][f"{role}_session_usd"])
    if cfg["ai"]["mode"] == "standin":
        out = standin(role, brief, cwd)
    else:
        cmd = ["claude", "-p", "--model", model, "--output-format", "json", "--max-budget-usd", f"{usd:g}",
               "--permission-mode", "dontAsk", "--allowedTools", *tools, "--disallowedTools", *never]
        with renewing():
            r = subprocess.run(cmd, input=brief, cwd=cwd, capture_output=True, text=True, timeout=3 * 3600)
        try:
            out = json.loads(r.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"claude answered no JSON (exit {r.returncode}): {(r.stderr or r.stdout)[-400:]}") from None
    record_cost(cfg, float(out.get("total_cost_usd") or 0), role=role, model=model,
                item=os.environ.get("ERGOSTAT_ITEM", ""), run=os.environ.get("ERGOSTAT_RUN", ""))
    print(json.dumps({k: v for k, v in out.items() if k != "result"} | {"type": "result"}), flush=True)
    if out.get("is_error"):
        raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
    return out


def standin(role: str, brief: str, cwd: Path) -> dict:
    """Free and scripted. The implementor writes a note into the work; the reviewer's verdict is FACTORY_STANDIN_VERDICT
    (merge by default; fix, or park)."""
    if role == "implementor":
        note = cwd / "standin" / f"{cwd.name}.txt"
        note.parent.mkdir(exist_ok=True)
        with note.open("a") as f:
            f.write(f"worked by the stand-in ({len(brief)} characters of brief)\n")
        said = f"wrote {note.relative_to(cwd)}"
    else:
        v = os.environ.get("FACTORY_STANDIN_VERDICT", "merge")
        said = "The stand-in read the diff.\n```json\n" + json.dumps(
            {"verdict": v, "blocking": [] if v == "merge" else ["the stand-in's blocking finding"],
             "non_blocking": ["a stand-in's note"], "where_it_stopped": "stopped by the stand-in"}) + "\n```"
    return {"type": "result", "subtype": "success", "is_error": False, "result": said, "total_cost_usd": 0.0,
            "num_turns": 1, "usage": {"input_tokens": len(brief) // 4, "output_tokens": 50}}


def read_input() -> dict:
    """The run's input: {item, lease}. A program block is given it as JSON on standard input; an `ai` block's `run:`
    is given its prompt there instead, so its item is read from the record ($ERGOSTAT_ITEM)."""
    data = sys.stdin.read()
    try:
        given = json.loads(data) if data.strip() else {}
    except json.JSONDecodeError:
        given = {}
    if not isinstance(given, dict) or not given.get("item"):
        iid = os.environ.get("ERGOSTAT_ITEM")
        if not iid:
            raise RuntimeError("no item: this program runs for the item its block takes ($ERGOSTAT_ITEM)")
        it = json.loads(ergostat("item", iid, "--json").stdout)
        given = {"item": {k: it[k] for k in ("id", "kind", "state", "fields")}, "lease": it["fields"].get("lease")}
    return given
