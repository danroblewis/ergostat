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
import signal
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


def cli(cfg: dict) -> None:
    """For the coordinator's tools, outside a run: ergostat on this instance (the live version's, else on the PATH)."""
    exe = path(cfg, "live") / "current" / ".venv" / "bin" / "ergostat"
    os.environ.setdefault("ERGOSTAT_CMD", f"{shlex.quote(str(exe)) if exe.exists() else 'ergostat'} -C "
                                          f"{shlex.quote(str(MODEL))}")


def add(event: str, item: str, **data) -> None:
    """An event recorded by `ergostat event --add` (outside a run, or about another item from a gated action)."""
    ergostat("event", "--add", event, "--item", item, "--data", json.dumps(data, default=str))


def items(kind: str, state: str | None = None) -> list[dict]:
    """The items of a kind (in a state), from the record (at most 5,000: the factory's kinds are small)."""
    args = ["item", "--kind", kind, "--json", "-n", "5000"] + (["--state", state] if state else [])
    return json.loads(ergostat(*args).stdout).get("items", [])


def act(name: str, key: str, **args) -> tuple[int, str]:
    """Ask for a gated action ($ERGOSTAT_CMD act); (exit, what it said): 0 ran, 1 failed, 3 held, 4 denied, 2 refused."""
    a = ["act", name, "--key", key] + [x for k, v in args.items() for x in ("--arg", f"{k}={v}")]
    r = ergostat(*a, check=False)
    return r.returncode, (r.stdout + "\n" + r.stderr).strip()        # whole: the action's id is said first


# ---- git

def ids(v) -> list[str]:
    """A relation's ids (a field holding one id, or the list the record folds it to)."""
    return [v] if isinstance(v, str) else list(v or [])


def rel(p: Path) -> str:
    """A path as the record keeps it: from the model's folder when it is inside it."""
    try:
        return str(p.relative_to(MODEL))
    except ValueError:
        return str(p)


def git(repo: Path, *args: str, check: bool = True) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env, timeout=600)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {r.stderr.strip()[-400:]}")
    return r.stdout.strip()


def conflicted(repo: Path) -> list[str]:
    """The files a merge left in conflict, read NUL-separated so a path with a space (or one at its ends) stays whole."""
    r = subprocess.run(["git", "-C", str(repo), "diff", "-z", "--name-only", "--diff-filter=U"], capture_output=True,
                       text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, timeout=600)
    return [p for p in r.stdout.split("\0") if p]


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


SAFE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def branch_of(gap: dict) -> str:
    """The gap's branch name (its worktree, its session folders, its definition file): only lowercase words and
    dashes, so no path or ref can be made of it. Anything else raises. A gap that `continues` a branch (NAME or
    factory/NAME, an existing branch) is on NAME, and may name no other branch."""
    c = gap["fields"].get("continues")
    c = str(c).removeprefix("factory/") if c else None
    if c and gap["fields"].get("branch") not in (None, "", c):
        raise ValueError(f"{gap['id']}: it continues {c!r} but names the branch {gap['fields']['branch']!r}")
    b = gap["fields"].get("branch") or c or slug(gap["id"].split("/", 1)[1], 32)
    if not isinstance(b, str) or not SAFE.match(b):
        raise ValueError(f"{gap['id']}: branch {b!r} is not lowercase words and dashes (at most 64)")
    return b


def git_branch(branch: str) -> str:
    """The git ref a gap's work is on, in the drop and the checkout: factory/<branch>."""
    if not SAFE.match(branch):
        raise ValueError(f"branch {branch!r} is not lowercase words and dashes")
    return f"factory/{branch}"


def run_tag(branch: str, began: float) -> str:
    """A run's log name: the branch and when the run began (UTC, to the second; never a gap's own count, which starts
    again for a gap that continues a branch another gap built)."""
    return f"{branch}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(began))}"


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


def record_cost(cfg: dict, usd: float, at: float | None = None, **what) -> float:
    at = time.time() if at is None else at
    with (run_dir(cfg) / "costs.jsonl").open("a") as f:
        f.write(json.dumps({"at": at, "usd": round(usd, 4), **what}) + "\n")
    return at


class OverBudget(RuntimeError):
    pass


def reserve(cfg: dict, usd: float, **what) -> float:
    """Charge a session's most (its --max-budget-usd) before it starts, under a lock, so two sessions never pass the
    cap together; refused (OverBudget) when it would. ``settle`` gives back what it did not spend, once its cost is
    known: a session that times out, crashes or is killed keeps its whole reservation. Returns its time."""
    with open(run_dir(cfg) / "costs.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            why = may_spend(cfg, usd)
            if why:
                raise OverBudget(why)
            return record_cost(cfg, usd, kind="reserved", **what)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def settle(cfg: dict, reserved: float, spent: float, at: float, **what) -> None:
    """The difference between what a session spent and what was reserved for it (negative: given back; positive: an
    overshoot, charged), dated with the reservation, so the day it lands in is the session's."""
    record_cost(cfg, spent - reserved, kind="settled", spent=round(spent, 4), at=at, **what)


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
    import agents
    return sum(1 for pid, (_, cmd) in rows.items() if pid not in mine and SUITE.match(cmd.strip())) + \
        agents.suite_containers()


def wait_quiet(cfg: dict, why: str = "") -> float:
    """Wait until fewer than [load] most_suites suites run on this machine (anyone's), renewing the lease; the
    seconds waited."""
    began, poll, most = time.time(), float(cfg["load"]["wait_poll"]), int(cfg["load"].get("most_suites", 1))
    while cfg["load"].get("wait", True) and suites_running() >= most:
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


def suite(cfg: dict, name: str, cwd: Path, log: Path, slot: bool = True, command: str | None = None,
          **fmt) -> tuple[int, float]:
    """One of [suites] in cwd (or ``command`` for it: in a container), its output to log; (exit, seconds). Run by the
    shell, as the coordinator does, inside [suites] slot (a machine-wide suite slot, waited for) unless ``slot`` is
    False (the queue: its lock is its slot). The suite's whole process group is killed if this one is stopped."""
    quoted = {k: " ".join(map(shlex.quote, v)) if isinstance(v, list) else shlex.quote(str(v)) for k, v in fmt.items()}
    cmd = command or cfg["suites"][name].format(**quoted)
    if slot and cfg["suites"].get("slot") and name != "ruff":
        cmd = f"{cfg['suites']['slot']} {cmd}"
    began = time.time()
    with log.open("w") as out:
        env = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")}   # (never the engine's socket)
        p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT,
                             start_new_session=True)
        try:
            while p.poll() is None:
                renew()
                try:
                    p.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if p.poll() is None:                        # stopped part way (an error, a kill): its whole group goes
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
    return p.returncode, time.time() - began


def kill_after(cfg: dict) -> int:
    """The failed gates that park a gap (the kill rule): [gates] kill_after."""
    return int(cfg.get("gates", {}).get("kill_after", 3))


def stop_on_term() -> None:
    """SIGTERM (a lease expired, ergostat stopping) raised as SystemExit, so every finally runs: a merge undone, a
    suite's processes killed."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))


FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)", re.M)


def failed_tests(text: str) -> list[str]:
    return sorted(set(FAILED.findall(text)))


# ---- an AI session

def session(cfg: dict, role: str, brief: str, work: Path) -> dict:
    """One session on the brief, on a work folder: in its own container (agents.py), or the free stand-in. Its most
    (--max-budget-usd) is reserved first and what it did not spend given back once its cost is known; a session that
    fails keeps its whole reservation. Returns Claude Code's result message, and prints it so the run is charged."""
    model, usd = cfg["ai"][f"{role}_model"], float(cfg["ai"][f"{role}_session_usd"])
    who = dict(role=role, model=model, item=os.environ.get("ERGOSTAT_ITEM", ""), run=os.environ.get("ERGOSTAT_RUN", ""))
    if cfg["ai"]["mode"] != "standin":
        import agents
        agents.token(cfg)                                # no token, no session (and nothing charged)
    at = reserve(cfg, usd, **who)
    if cfg["ai"]["mode"] == "standin":
        out = standin(role, brief, work)
    else:
        with renewing():
            out = agents.session(cfg, role, brief, work)
    if out.get("total_cost_usd") is not None:
        settle(cfg, usd, float(out["total_cost_usd"]), at, **who)
    print(json.dumps({k: v for k, v in out.items() if k != "result"} | {"type": "result"}), flush=True)
    if out.get("is_error"):
        raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
    return out


def attempt(cfg: dict, role: str, brief: str, work: Path) -> dict | None:
    """A run's session, or None when the day's cap refuses it (the item given back for an hour, uncounted)."""
    why = may_spend(cfg, float(cfg["ai"][f"{role}_session_usd"]))
    if not why:
        try:
            return session(cfg, role, brief, work)
        except OverBudget as e:
            why = str(e)
    nack(f"budget: {why}", after="1h", count=False)
    return None


STANDIN = {
    "planner": '<definition branch="{b}">\n# {b}: planned by the stand-in\n\ndepends-on: []\n\n## Definition of done\n\n'
               'It works.\n\n## Acceptance tests\n\n- `tests/test_x.py::test_it`: it works.\n\n## Size budget\n\n'
               '100 net lines.\n</definition>',
    "researcher": "<report>\n# The stand-in's answer\n\nNothing was read.\n\n## Sources\n\n- none\n</report>\n"
                  "<summary>The stand-in's answer.</summary>",
    "librarian": "```json\n[]\n```"}


def standin(role: str, brief: str, cwd: Path) -> dict:
    """Free and scripted. FACTORY_STANDIN_<ROLE> is what a role says, when set. Else the implementor finishes a merge
    it was handed (main's side of each conflict; or aborts it, when FACTORY_STANDIN_MERGE=abort) and writes a note
    into the work; the planner, researcher and
    librarian say STANDIN's; a reviewer's (or plan reviewer's) verdict is FACTORY_STANDIN_VERDICT (merge by default; fix, or park)."""
    b = re.search(r"Branch: `([a-z0-9-]+)`", brief)
    said = os.environ.get(f"FACTORY_STANDIN_{role.upper()}") or STANDIN.get(role, "").replace("{b}", b[1] if b else "x")
    if said:
        pass
    elif role == "implementor":
        if (cwd / ".git" / "MERGE_HEAD").exists() and os.environ.get("FACTORY_STANDIN_MERGE") == "abort":
            git(cwd, "merge", "--abort")                     # (a session walking away from it: refused after)
        elif (cwd / ".git" / "MERGE_HEAD").exists():         # a merge handed over: main's side of each conflict
            git(cwd, "checkout", "--theirs", "--", *conflicted(cwd))
            git(cwd, "add", "-A")
            git(cwd, "-c", "user.name=factory", "-c", "user.email=factory@localhost", "commit", "-q", "--no-edit")
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


def last_attempt(given: dict) -> bool:
    """Whether this run is its lease's last attempt (another failure would make the item a dead letter)."""
    lease = given.get("lease") or {}
    if "attempt" in lease:
        return int(lease["attempt"]) >= int(lease.get("attempts") or lease.get("max") or 2)
    return int(lease.get("attempts") or 0) + 1 >= int(lease.get("max") or 2)


def guarded(given: dict, began: float, measured: str, stop) -> int:
    """For a run's unexpected failure (a session timed out or gave no result, a verdict that does not parse, no
    definition, Docker or the egress proxy failing): its hours recorded; on its last attempt, ``stop(why)`` (the gap
    parked with where it stopped) instead of a dead letter; before, raised again (the attempt counted)."""
    import traceback
    e = sys.exc_info()[1]
    say("gap.measured", **{measured: round((time.time() - began) / 3600, 3)}, last_error=f"{type(e).__name__}: {e}"[:500])
    if last_attempt(given):
        stop(f"Stopped on its last attempt by {type(e).__name__}: {e}\n\n```\n{traceback.format_exc()[-1500:]}\n```")
        return 0
    raise e


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
