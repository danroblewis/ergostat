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
DEFS = "dev/records"                                   # where a gap's definition is written (the owner, 2026-11-21)
OLD_DEFS = "docs/roadmap/overnight"                    # where the first gaps' are: still read, the new path first
REF = re.compile(r"([\w/.-]+):((?:dev/records|docs/roadmap/overnight)/[a-z0-9-]+\.md)")


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
    limits(cfg)                                         # (a limit past its ceiling refused here, and again at run time)
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
    print(json.dumps(line, default=str) + "\n", end="", flush=True)   # (one write: a half's thread may say one too)


def nack(why: str, after: str | None = None, count: bool = True) -> None:
    n = {"why": why[:500], "count": count}
    if after:
        n["after"] = after
    print(json.dumps({"nack": n}), flush=True)


def _aihold():
    """dev/bin/aihold.py, found beside this file when fac was loaded by path (dev/bin not on sys.path)."""
    if str(HERE / "bin") not in sys.path:
        sys.path.append(str(HERE / "bin"))
    import aihold
    return aihold


def draining(cfg: dict) -> bool:
    """A switch drains the runs under way (run/drain.json): a session that holds no lease (the groomer, the plan
    review) waits for its next turn instead of starting; so it does while the AI is held (aihold.py)."""
    aihold = _aihold()
    return (run_dir(cfg) / "drain.json").exists() or aihold.held(cfg) is not None


def drain_holds(cfg: dict) -> bool:
    """While an approved switch drains the runs under way (run/drain.json, dev/bin/drain.py), or the AI is held for the
    provider's usage limit (aihold.py), an AI run takes no new item: it gives it back uncounted, to be taken again
    after the switch, or at the reset."""
    aihold = _aihold()
    if aihold.holds(cfg):
        return True
    if not (run_dir(cfg) / "drain.json").exists():
        return False
    nack("a switch drains the runs under way (run/drain.json): taken again after it", after="5m", count=False)
    return True


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
    """The items of a kind (in a state), from the record. One listing carries at most 500 items (spec/items.py
    LISTED), so with no state each state is listed on its own and the lists joined (past 500 gaps the
    intake read merged and closed gaps as new and opened them again). A kind whose one listing carries all of its
    items (none past the cap) is that one listing: the header and a listing per declared state, empty ones too, cost a
    process each (drain.py's step read four kinds so, some forty `ergostat` processes a minute)."""
    def listed(st):
        args = ["item", "--kind", kind, "--json", "-n", "5000"] + (["--state", st] if st else [])
        got = json.loads(ergostat(*args).stdout)
        return got.get("items", []), int(got.get("total") or 0)

    def one(st):
        got, total = listed(st)
        if len(got) < total:                                            # (a state past the cap: said, as before)
            print(f"items({kind!r}, {st!r}): {total} items, the listing carries {len(got)}", file=sys.stderr)
        return got
    if state:
        return one(state)
    every, total = listed(None)
    if len(every) >= total:
        return every
    head = [ln for ln in ergostat("item", "--kind", kind).stdout.splitlines() if ln.startswith(f"{kind} ")]
    states = re.findall(r"([a-z][a-z-]*) \d+", head[0].split("  ", 2)[-1]) if head else []
    if not states:
        return one(None)
    out, seen = [], set()
    for st in states:
        for i in one(st):
            if i["id"] not in seen:
                seen.add(i["id"])
                out.append(i)
    return out


STACKABLE = ("approved", "queued", "push-pending")      # a dependency reviewed and not yet on main: one to build on


def stack_base(cfg: dict, gap: dict) -> list[dict] | None:
    """The bases a gap is built on: when every dependency not yet merged or closed is in STACKABLE, each one's reviewed
    head ({gap, sha, branch}; sha "" when none is recorded, which no branch tip equals), in rank order. None for any
    other gap (no unfinished dependency, or one not found or not reviewed): it builds on main, as before."""
    deps = ids(gap["fields"].get("depends_on"))
    gaps = {g["id"]: g for g in items("gap")} if deps else {}
    left = [gaps.get(d) for d in deps if (gaps.get(d) or {}).get("state") not in ("merged", "closed")]
    if not left or any(g is None or g["state"] not in STACKABLE for g in left):
        return None
    left.sort(key=lambda g: (g["fields"].get("rank") or 10**9, g["id"]))
    return [{"gap": g["id"], "sha": str(g["fields"].get("reviewed_head") or ""), "branch": branch_of(g)} for g in left]


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


def definition_file(gap: dict, work: Path | None = None) -> str:
    """The definition's path in the repository: `dev/records/<branch>.md`, or the old
    `docs/roadmap/overnight/<branch>.md` when the clone ``work`` has only that (a branch begun before the move); or,
    for a gap that `continues` a branch and names its `definition` as `REF:dev/records/X.md` (or the old folder), that
    file (the continued branch's own, so no copy is made under the new gap's name)."""
    m = REF.fullmatch(str(gap["fields"].get("definition") or ""))
    if m and gap["fields"].get("continues"):
        return m.group(2)
    new, old = (f"{d}/{branch_of(gap)}.md" for d in (DEFS, OLD_DEFS))
    return old if work and not (work / new).is_file() and (work / old).is_file() else new


def git_branch(branch: str) -> str:
    """The git ref a gap's work is on, in the drop and the checkout: factory/<branch>."""
    if not SAFE.match(branch):
        raise ValueError(f"branch {branch!r} is not lowercase words and dashes")
    return f"factory/{branch}"


def run_tag(branch: str, began: float) -> str:
    """A run's log name: the branch and when the run began (UTC, to the second; never a gap's own count, which starts
    again for a gap that continues a branch another gap built)."""
    return f"{branch}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(began))}"


def net_lines(repo: Path, base: str, head: str, core: bool = True) -> int:
    """Net lines changed outside tests/, docs/ and the gaps' records (dev/records/): of ergostat's core (dev/ and the
    root model left out too), or, with core=False, with dev/ and the root model counted (a merge's lines, scored
    against its planned size class)."""
    add = rem = 0
    out = git(repo, "diff", "--numstat", f"{base}...{head}", "--", ".", ":(exclude)tests", ":(exclude)docs",
              f":(exclude){DEFS}",
              *((":(exclude)dev", ":(exclude)ergostat.yaml") if core else ()))
    for line in out.splitlines():
        a, d, _ = line.split("\t", 2)
        if a != "-":
            add, rem = add + int(a), rem + int(d)
    return add - rem


def budget_of(definition: str, default: int = 600) -> int:
    m = re.search(r"^## Size budget.*?$(.*?)(?=^## |\Z)", definition, re.M | re.S)
    nums = re.findall(r"(\d[\d,]*)\s*(?:net )?lines", m.group(1)) if m else []
    return int(nums[0].replace(",", "")) if nums else default


def allowances(definition: str) -> dict[str, str]:
    """The definition's `allows-findings: [code part: why, ...]`: each `ergostat check` finding it allows ("code part",
    or the code alone for one about no part), with its reason (no comma in it); one with no reason allows nothing."""
    m = re.search(r"^allows-findings:\s*\[(.*)\]\s*$", definition, re.M)
    return {f"{c} {p}" if p else c: why.strip() for c, p, why in re.findall(
        r"([\w.-]+)(?: ([^\s:,\]]+))?:([^,\]]*)", m[1] if m else "") if why.strip()}


RECORD_FINDINGS = r"calibration-.*|fit-.*|takes-order-unset"   # (codes of findings of the record, not the change)
UNFINISHED = {"extremes-running", "extremes-skipped"}   # notes: check's extreme-conditions tests did not all finish


def findings(text: str, record: str) -> set[str] | None:
    """The findings in `ergostat check --json`'s output (in a log), each "code part" (the code alone about no part), but
    those whose code matches the regex `record`; None when no output there says (the check could not run)."""
    for m in re.finditer(r"^\{", text, re.M):
        try:
            got = json.JSONDecoder().raw_decode(text[m.start():])[0]
        except ValueError:
            continue
        if isinstance(got, dict) and isinstance(got.get("found"), list):
            keys = [(str(x.get("code") or x.get("level")), x.get("about")) for x in got["found"] if isinstance(x, dict)]
            return {f"{c} {a}" if a else c for c, a in keys if not re.fullmatch(record, c)}
    return None


# ---- the daily cap, which fails closed

CAP = re.compile(r"^\s*ai-budget:\s*$.*?^\s*hold:\s*\"<=\s*([\d.]+)\"", re.M | re.S)


def daily_cap() -> float:
    """The goal ai-budget's setpoint in dev/model/budget.yaml: the one place the cap is written."""
    m = CAP.search((HERE / "model" / "budget.yaml").read_text())
    if not m:
        raise RuntimeError("no ai-budget goal with a hold in dev/model/budget.yaml")
    return float(m.group(1))


def run_alive(cfg: dict, run: str) -> bool:
    """Whether a run's process is still there, from the engine's record of it (written before the run starts, removed
    when it ends). A record that cannot be read counts as alive: the cap fails closed."""
    import live
    try:
        pid = int(json.loads((live.state_dir(cfg) / "runs" / f"{run}.json").read_text())["pid"])
        os.kill(pid, 0)
    except (FileNotFoundError, ProcessLookupError):
        return False
    except (OSError, ValueError, KeyError, TypeError):
        return True
    return True


def spent_today(cfg: dict) -> float:
    """Dollars the factory's sessions cost over the last 24 hours, from its ledger. A reservation with no settlement is
    held in full while its run is alive. A run that died (killed by a restart) never settles and what it spent is not
    known, so it is charged twice the day's mean session, at most what it reserved, rather than holding the whole
    reservation against the cap. An unreadable line raises."""
    ledger = run_dir(cfg) / "costs.jsonl"
    if not ledger.exists():
        return 0.0
    since, total, unsettled, spends = time.time() - 86400, 0.0, {}, []
    for line in ledger.read_text().splitlines():
        if line.strip():
            e = json.loads(line)
            at, usd, run = float(e["at"]), float(e["usd"]), e.get("run")
            if run and e.get("kind") == "reserved":
                unsettled.setdefault(run, []).append((at, usd))
                continue
            if at >= since:
                total += usd
                if e.get("kind") == "settled" and "spent" in e:
                    spends.append(float(e["spent"]))
            if run and e.get("kind") == "settled" and unsettled.get(run):
                was_at, was = unsettled[run].pop(0)
                total += was if was_at >= since else 0.0
    typical = 2 * sum(spends) / len(spends) if spends else None
    for run, held in unsettled.items():
        held = [(at, usd) for at, usd in held if at >= since]
        if held:
            alive = typical is None or run_alive(cfg, run)
            total += sum(usd if alive else min(usd, typical) for _, usd in held)
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
    known; a session that dies unsettled is charged as spent_today says. Returns its time."""
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


SUITES: set[int] = set()                                # the process groups of the suites running now (suite())


def stop_suites(group: set | None = None) -> None:
    """Every running suite's process group stopped, and its container by name: a run stopped while suites run in
    threads of its own (queue.py). ``group`` (what suite() added to it): only those, so one half's failure never stops
    the other's suites."""
    for pid in [p for p in list(SUITES) if group is None or p in group]:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for name in [b for b in list(BOXES) if group is None or b in group]:
        agents_module().killed(name)


BOXES: set[str] = set()                                 # the queue's suite containers running now (suite(box=...))


SUITE_GOAL_MINUTES = 15                                 # the suites-in-time goal (dev/model/measures.yaml)
STALL_MOST, WALL_MOST = 60, 120                         # the ceilings of [suites] stall_minutes and wall_minutes
STALLS_MOST = 3                                         # a gap's stalls (alone): then its failure (queue, triage)


def limits(cfg: dict) -> tuple[float, float]:
    """The queue's suite limits in seconds: (no log growth for [suites] stall_minutes, default 10, at most 60; in all
    [suites] wall_minutes, default 3 x the suite-minutes goal, at most 120). One past its ceiling, or not above 0, is
    refused (ValueError), never clamped."""
    s = cfg.get("suites", {})
    stall, wall = s.get("stall_minutes", 10), s.get("wall_minutes", 3 * SUITE_GOAL_MINUTES)
    for key, v, most in (("stall_minutes", stall, STALL_MOST), ("wall_minutes", wall, WALL_MOST)):
        if isinstance(v, bool) or not isinstance(v, int | float) or not 0 < v <= most:
            raise ValueError(f"[suites] {key} = {v!r}: more than 0 and at most {most}")
    return stall * 60.0, wall * 60.0


class Stalled(Exception):
    """A queue suite stopped for a limit (limits()): never its result, nor the batch's failure. Its test: the test
    function in the last stack pytest's faulthandler dumped (suite() sets its timeout), else the last test id named."""

    def __init__(self, name: str, why: str, text: str):
        tests = [f"{p}::{t}" for p, t in re.findall(r'File "(?:[^"]*/)?(tests/test_\w+\.py)", line \d+ in (test_\w+)',
                                                     text)] or re.findall(r"(\S+\.py::[^\s\]]+\]?)", text)
        self.suite, self.why, self.test, self.tail = name, why, tests[-1] if tests else None, text[-2000:]
        super().__init__(f"the {name} suite was stopped ({why}), on {self.test or 'no test the log names'}")


def agents_module():
    import agents
    return agents


def suite(cfg: dict, name: str, cwd: Path, log: Path, slot: bool = True, command: str | None = None,
          quarantined: list[str] = (), box: str = "", group: set | None = None, **fmt) -> tuple[int, float]:
    """One of [suites] in cwd (or ``command`` for it: in a container), its output to log; (exit, seconds). Run by the
    shell, as the coordinator does, inside [suites] slot (a machine-wide suite slot, waited for) unless ``slot`` is
    False (the queue: its lock is its slot); ``quarantined``: deselected from unit and browser. The suite's whole
    process group is killed if this one is stopped. ``box`` ("queue", "triage", "host"): under limits() (stall, wall,
    faulthandler); "host" (the queue's and triage's `[suites] host`) on the Mac, never boxed; the others, with
    [suites] queue_container (true unless false), in a container of its own (agents.queued), killed by name on any
    way out; one that did not start raises agents.NotStarted (an infrastructure failure, never read as the suite's
    result). ``group``: a set this suite's pid and container are added to, for stop_suites(group)."""
    quoted = {k: " ".join(map(shlex.quote, v)) if isinstance(v, list) else shlex.quote(str(v)) for k, v in fmt.items()}
    cmd = command or deselected(name, cfg["suites"][name].format(**quoted), list(quarantined))
    stall, wall = limits(cfg) if box else (600.0, 600.0)  # (again at run time: the queue's and triage's only)
    env = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")}   # (never the engine's socket)
    if box:                                             # a test running past half the stall limit: its stack, logged
        env["PYTEST_ADDOPTS"] = f"{env.get('PYTEST_ADDOPTS', '')} -o faulthandler_timeout={stall / 2:g}".strip()
    boxed = None
    if box and box != "host" and cfg["suites"].get("queue_container", True) is not False:
        boxed, cmd = agents_module().queued(cfg, name, cmd, cwd, box, (f"PYTEST_ADDOPTS={env['PYTEST_ADDOPTS']}",))
        BOXES.add(boxed)
        if group is not None:
            group.add(boxed)
    held = None
    if slot and cfg["suites"].get("slot") and name != "ruff":
        if box:                                         # the limits' clocks start once the slot is held (marked inside)
            held = log.with_name(log.name + ".held")
            held.unlink(missing_ok=True)
            cmd = "sh -c " + shlex.quote(f": > {shlex.quote(str(held))}; {cmd}")
        cmd = f"{cfg['suites']['slot']} {cmd}"
    began, stopped = time.time(), None
    with log.open("w") as out:
        p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT,
                             start_new_session=True)
        SUITES.add(p.pid)
        if group is not None:
            group.add(p.pid)
        try:
            size, grew, clock = 0, began, began
            while p.poll() is None:
                if held and not held.exists():          # waiting for the slot: the machine's time, not the suite's
                    size, grew = log.stat().st_size, time.time()
                    clock = grew
                elif box:
                    now, got = time.time(), log.stat().st_size
                    size, grew = (got, now) if got != size else (size, grew)
                    stopped = (f"its log did not grow for {stall / 60:g} min" if now - grew > stall else
                               f"it ran past {wall / 60:g} min" if now - clock > wall else None)
                    if stopped:                         # (past a limit: never renewed, killed in the finally)
                        break
                renew()
                try:
                    p.wait(timeout=min(60.0, stall / 10, wall / 10))
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if p.poll() is None:                        # stopped part way (an error, a kill): its whole group goes
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
            SUITES.discard(p.pid)
            if held:
                held.unlink(missing_ok=True)
            if boxed:
                agents_module().killed(boxed)
                BOXES.discard(boxed)
    if stopped:
        raise Stalled(name, stopped, log.read_text(errors="replace"))
    if boxed and p.returncode in agents_module().NOT_STARTED:
        raise agents_module().NotStarted(f"the {name} suite's container did not start (exit {p.returncode}): "
                                         f"{log.read_text()[-400:].strip()}")
    return p.returncode, time.time() - began


GATES = {"kill_after": 6, "build_failures": 6, "build_hours": 12.0}   # the kill rule's defaults ([gates])


def gate(cfg: dict, key: str) -> float:
    """One of the kill rule's numbers: [gates] kill_after (failed gates: reviews, conflicts, real failures in the
    queue), build_failures (the implementor's failed fast suites), build_hours (the implementor's hours, every round)."""
    return float(cfg.get("gates", {}).get(key, GATES[key]))


def kill_after(cfg: dict) -> int:
    """The failed gates that park a gap (the kill rule): [gates] kill_after."""
    return int(gate(cfg, "kill_after"))


def stop_on_term() -> None:
    """SIGTERM (a lease expired, ergostat stopping) raised as SystemExit, so every finally runs: a merge undone, a
    suite's processes killed."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))


FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)", re.M)


def failed_tests(text: str) -> list[str]:
    return sorted(set(FAILED.findall(text)))


# ---- the quarantine (tests/quarantine.txt): tests deselected from the suites and run beside them, never blocking

def quarantine(repo: Path, ref: str) -> list[str]:
    """The tests quarantined at ``ref``: the base a run merges onto, never the branch under test, so a branch's own
    line in tests/quarantine.txt quarantines nothing until it is on main. The id before the first `|` of each line
    (`#` comments). No list at ``ref``, or a ref that cannot be read: none, and every test blocks."""
    lines = git(repo, "show", f"{ref}:tests/quarantine.txt", check=False).splitlines()
    return [x.split("|")[0].strip() for x in lines if x.strip() and not x.lstrip().startswith("#")]


def deselected(name: str, cmd: str, tests: list[str]) -> str:
    """The unit or browser suite's command with each of ``tests`` deselected (any other suite's as it is)."""
    return " ".join([cmd, *(f"--deselect {shlex.quote(t)}" for t in tests)]) if name in ("unit", "browser") else cmd


OUTCOME = re.compile(r"^(PASSED|FAILED|ERROR) (\S+::\S+)", re.M)


def outcomes(text: str, tests: list[str]) -> dict[str, str]:
    """Each test's result from the whole log of a `-rA` run: pass only on its own PASSED line and no FAILED or ERROR
    one; fail on either; anything else (skipped, not collected, a run killed or unreadable) unknown, never a pass."""
    said: dict[str, str] = {}
    for word, t in OUTCOME.findall(text):
        said[t] = "fail" if word != "PASSED" or said.get(t) == "fail" else "pass"
    return {t: said.get(t, "unknown") for t in tests}


# pytest's summary line, -q or not, xdist's too: `1 failed, 3 passed, 2 warnings in 2.10s (0:00:02)`, `no tests ran in`
SUMMARY = re.compile(r"^=*\s*((?:\d+ [a-z]+, )*\d+ [a-z]+|no tests ran) in \d+(?:\.\d+)?s(?: \([\d:]+\))?\s*=*\s*$", re.M)
COUNTS = ("passed", "failed", "skipped", "deselected", "errors")
COUNTED_AS = {**{k: k for k in COUNTS}, "error": "errors"}


def counts(text: str) -> dict[str, int] | None:
    """A pytest log's counts (passed, failed, skipped, deselected, errors) from its last summary line, anywhere in the
    whole log; None without one (killed, stopped, not pytest): unknown, never zeros. Other words (warnings, xfailed)
    are not counted."""
    found = SUMMARY.findall(re.sub(r"\x1b\[[0-9;]*m", "", text))
    if not found:
        return None
    got = dict.fromkeys(COUNTS, 0)
    for n, word in re.findall(r"(\d+) ([a-z]+)", found[-1]):
        if word in COUNTED_AS:
            got[COUNTED_AS[word]] += int(n)
    return got


def beside(tests: list[str], log: Path, run) -> dict[str, str]:
    """The quarantined ``tests`` run once beside a suite (``run(tests)`` writes ``log``), never blocking it: each
    result said on its item flake/<test> (`last_run`). A run that fails to start or leaves no log records unknown. A
    flake item still marked quarantined whose test is no longer listed is marked released (`quarantined: false`)."""
    try:
        for it in items("flake"):
            if it["fields"].get("quarantined") and it["fields"].get("test") not in tests:
                say("flake.measured", it["id"], quarantined=False)
    except Exception:  # noqa: BLE001 - a record that cannot be read leaves the marks as they were, never the suite
        pass
    if not tests:
        return {}
    try:
        run([*tests, "-rA"])
        text = log.read_text()
    except Exception as e:  # noqa: BLE001 - the quarantine never fails the suite it runs beside
        text = f"not run: {type(e).__name__}: {e}"
    got = outcomes(text, tests)
    for t, r in got.items():
        say("flake.measured", f"flake/{slug(t, 80)}", test=t, quarantined=True, last_run=r, last_run_at=time.time(),
            last_run_log=str(log))
    return got


# ---- an AI session

def session(cfg: dict, role: str, brief: str, work: Path, item: str | None = None) -> dict:
    """One session on the brief, on a work folder: in its own container (agents.py), or the free stand-in. Its most
    (--max-budget-usd) is reserved first and what it did not spend given back once its cost is known; a session that
    fails keeps its whole reservation. Returns Claude Code's result message, and prints it so the run is charged.
    Its conversation is kept as the item session/<item>-<role>-<n> (sessions.py; ``item``: the gap, research or
    review it works for, else the run's own). One that ends on the provider's usage limit holds the AI till its reset
    and ends the run, its lease given back uncounted (aihold.py)."""
    aihold = _aihold()
    import sessions
    model, usd = cfg["ai"][f"{role}_model"], float(cfg["ai"][f"{role}_session_usd"])
    who = dict(role=role, model=model, item=os.environ.get("ERGOSTAT_ITEM", ""), run=os.environ.get("ERGOSTAT_RUN", ""))
    if cfg["ai"]["mode"] != "standin":
        import agents
        agents.token(cfg)                                # no token, no session (and nothing charged)
    at = reserve(cfg, usd, **who)
    kept = sessions.Session(cfg, role, item)
    kept.started(model)
    out, error = None, None
    try:
        if cfg["ai"]["mode"] == "standin":
            out = standin(role, brief, work)
            sessions.standin(kept, brief, out)
        else:
            with renewing():
                out = agents.session(cfg, role, brief, work, keep=kept)
    except BaseException as e:
        error = f"{type(e).__name__}: {e}"
        if isinstance(e, SystemExit) or not aihold.limited(str(e), anywhere=True):
            raise
        aihold.stop(cfg, str(e))                         # (the usage limit: the run given back uncounted, ended)
    finally:
        kept.ended(out, error)
    if out.get("total_cost_usd") is not None:
        settle(cfg, usd, float(out["total_cost_usd"]), at, **who)
    print(json.dumps({k: v for k, v in out.items() if k != "result"} | {"type": "result"}), flush=True)
    if aihold.limited(str(out.get("result"))):
        aihold.stop(cfg, str(out.get("result")))
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
               'It works.\n\n## Files to touch\n\n- `x.py` (new)\n- `standin/work.txt` (new)\n\n## Risks\n\n- none.\n\n'
               '## Acceptance tests\n\n- `tests/test_x.py::test_it`: it works.\n\n## Size budget\n\n'
               'size: M (confidence: medium)\n\n100 net lines.\n</definition>',
    "researcher": "<report>\n# The stand-in's answer\n\nNothing was read.\n\n## Sources\n\n- `docs/GAPS.md:1`: the gaps\n</report>\n"
                  "<summary>The stand-in's answer.</summary>",
    "librarian": "```json\n[]\n```", "groomer": "```json\n{}\n```",
    "pipeline_manager": '```json\n{"calls": [], "summary": "The stand-in looked and did nothing."}\n```'}


def standin(role: str, brief: str, cwd: Path) -> dict:
    """Free and scripted. FACTORY_STANDIN_<ROLE> is what a role says, when set. Else the implementor finishes a merge
    it was handed (main's side of each conflict; or aborts it, when FACTORY_STANDIN_MERGE=abort) and writes a note
    into the work, and each of FACTORY_STANDIN_WRITES (comma-separated paths; `git rm`ed once its brief says they
    were refused); the planner, researcher and
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
        refused = re.search(r"^# (Scratch files refused|New `ergostat check` findings)", brief, re.M)
        for p in filter(None, os.environ.get("FACTORY_STANDIN_WRITES", "").split(",")):   # (the tests' scratch files:
            if refused and (refused[1][0] == "S" or f"`{Path(p).name.replace('@', ' ')}`" in brief):   # removed once
                git(cwd, "rm", "-q", "--", p)                    # refused; a check finding's, once the brief lists it)
            else:
                (cwd / p).parent.mkdir(parents=True, exist_ok=True)
                (cwd / p).write_text("a scratch file\n")
    else:
        v = os.environ.get("FACTORY_STANDIN_VERDICT", "merge")
        said = "The stand-in read the diff.\n```json\n" + json.dumps(
            {"verdict": v, "blocking": [] if v == "merge" else ["the stand-in's blocking finding"],
             "non_blocking": ["a stand-in's note"], "where_it_stopped": "stopped by the stand-in"}) + "\n```"
    return {"type": "result", "subtype": "success", "is_error": False, "result": said, "total_cost_usd": 0.0,
            "num_turns": 1, "usage": {"input_tokens": len(brief) // 4, "output_tokens": 50},
            "permission_denials": []}                                    # (the stand-in refuses nothing)


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
