"""The day's AI budget (SPEC §9.9): the permissive P3. No charged run starts unless what is left of ``budget.daily``
covers its reserve (``budget.max-cost``).

- **The fold** (``fold``), keyed by run id, never by lease state: each reserving event of the last 7 days
  (``ergostat.lease.taken``: its ``data.run``; ``agent.started``: its id; each with ``reserve``) is matched to its
  ends of the same 7 days (``agent.ran``, ``agent.failed`` by ``causedby``; ``budget.closed`` by ``data.run``). A run
  with no end is *reserved* at its reserve; an end counts in *spent* only while it is within the last day, at its
  cost, or (unknown) its reserve, or ``max-cost`` when it used AI at no known price; several ends, the largest.
- **The permit** (``permit``): under ``fcntl.flock`` on ``<state dir>/budget.lock``, opened anew each call (threads
  and processes alike exclude each other), the fold is read, the decision made and the reserving event written. It is
  the innermost lock: nothing is taken inside it but the event store's own.
- **A call's permit** (``ask``, ``done``): one of ergostat's own AI calls (``decisions/ai.call``) reserves its own
  per-call cap under the same flock (``budget.call``), and is closed with its reported cost (``budget.closed``). A
  call made inside a reserving run (``WITHIN``, else ``$ERGOSTAT_RUN``) belongs to it: the run is charged the larger
  of its end and the calls that end includes, plus the calls it does not include.
- **Recovery** (``recover``): a reserving run with no end whose process is gone, or is this one but no longer has it
  open (``OPEN``), is closed (``budget.closed``, cost unknown: charged its reserve for a day from the close).
"""

from __future__ import annotations

import contextlib
import contextvars
import fcntl
import json
import math
import os
import re
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from ..leases import TAKEN
from . import record as cr

SOURCE = "ergostat"
STARTED, CLOSED, REFUSED, CALL = "agent.started", "budget.closed", "budget.refused", "budget.call"
DAY, WEEK = 86400.0, 7 * 86400.0
FREE = ("person", "decision", "program", "rule")   # the agent kinds whose non-ai runs are free (an allowlist)
OPEN: set[str] = set()                     # the reserving runs this process has open (added under the flock)
SAID_EVERY, RECOVER_EVERY = 60.0, 60.0
_said: dict[tuple[str, str], float] = {}   # (state dir, block) → when (monotonic) a refusal was last recorded
_recovered: dict[str, float] = {}          # state dir → when (monotonic) it was last recovered
WITHIN: contextvars.ContextVar = contextvars.ContextVar("within", default=None)  # (run, its end includes the calls)


def _between() -> None:
    """Called under the flock, after the read and the decision and before the write (a test's hook)."""


def of(model):
    """What the budget reads of a model: a YAML model's spec; a TOML model's ``[budget]`` and its agents by the kind
    written (none written: ``None``, so charged); None for a TOML model with no ``[budget]``."""
    spec = getattr(model, "spec", None)
    if spec is not None or getattr(model, "budget", None) is None:
        return spec
    return SimpleNamespace(budget=model.budget, agents={n: SimpleNamespace(kind=a.kind if a.kind_set else None)
                                                        for n, a in model.agents.items()})


def free(spec, b) -> bool:
    """A run of this block is free (reserves 0) only when it is not ``ai`` and its agent is declared a person, a
    decision, a program or a rule; every other (no agent, no kind, narrow AI, AI) is charged ``max-cost``."""
    a = spec.agents.get(b.agent or "")
    return b.type != "ai" and a is not None and a.kind in FREE


@contextlib.contextmanager
def held(p):
    """``<state dir>/budget.lock`` held exclusively, by a new open of it."""
    fd = os.open(os.path.join(p.dir, "budget.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)                        # (closing releases the lock)


def _number(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _known(v) -> bool:
    """A cost that can be counted: a finite number, not below 0 (NaN, ±inf or a negative from a run's own output
    is unknown)."""
    return _number(v) and math.isfinite(v) and v >= 0


def _charge(e: dict, reserve: float | None, cap: float) -> float:
    """One end's charge: its known cost; unknown, its reserve (0 for a free run or one whose start is not in the
    window), or ``max-cost`` when it used AI at no known price, or a close of unknown cost with no reserve. A cost
    reported but malformed is unknown, charged the reserve, or ``max-cost`` when there is none."""
    d = e.get("data") or {}
    if e["type"] == CLOSED:
        return float(d["cost_usd"]) if _known(d.get("cost_usd")) else reserve or cap
    c = cr.numbers(e)["cost_usd"]
    if _known(c):
        return float(c)
    if c is not None:
        return reserve or cap
    return cap if isinstance(d.get("ai"), dict) else reserve or 0.0


def read(p, now: float) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """The reserving runs of the last 7 days (run → reserve, pid, block) and the ends of the same 7 days, by run."""
    runs: dict[str, dict] = {}
    for e in p.events.query(n=None, type=f"{TAKEN},{STARTED},{CALL}", source=SOURCE, since=now - WEEK):
        d = e.get("data") or {}
        if _number(d.get("reserve")):
            run = d.get("run") if e["type"] == TAKEN else e["id"]
            runs[run] = {"reserve": float(d["reserve"]), "pid": d.get("pid"), "block": d.get("block") or e.get("item"),
                         "within": d.get("within"), "included": d.get("included") is True}
    ends: dict[str, list[dict]] = {}
    for e in p.events.query(n=None, type=f"{cr.ENDS},{CLOSED}", source=SOURCE, since=now - WEEK):
        run = (e.get("data") or {}).get("run") if e["type"] == CLOSED else e.get("causedby")
        ends.setdefault(run or e["id"], []).append(e)        # (an end of no run: on its own)
    return runs, ends


def fold(p, spec, now: float | None = None) -> tuple[float, float]:
    """(spent, reserved) over the trailing day; raises when the record cannot be read."""
    now = time.time() if now is None else now
    runs, ends = read(p, now)
    charge, inside = {}, {}
    for run, es in ends.items():
        r = runs[run]["reserve"] if run in runs else None
        charge[run] = max((_charge(e, r, spec.budget.max_cost) for e in es if e["time"] >= now - DAY), default=0.0)
    for run, v in runs.items():                   # counted once: the calls a run's end includes are charged with it
        if v["included"] and v["within"] in runs and run in charge:
            inside[v["within"]] = inside.get(v["within"], 0.0) + charge.pop(run)
    spent = sum(max(c, inside.pop(run, 0.0)) for run, c in charge.items()) + sum(inside.values())
    return spent, sum(v["reserve"] for run, v in runs.items() if run not in ends)


def permit(p, spec, block, write, run: str):
    """A run of ``block`` asks to start: ``write(more)`` writes its reserving event (``more``: its reserve and pid).
    Returns (the event written, None), or (None, why it was refused): then nothing is written but ``budget.refused``,
    at most once a minute per block. A free run is written without the decision."""
    why, r = spec.budget.problem(), spec.budget.max_cost
    spent = reserved = None
    if not why and free(spec, block):
        return write({"reserve": 0.0, "pid": os.getpid()}), None
    more = {"reserve": r, "pid": os.getpid()}
    try:
        with held(p):
            if not why:
                try:
                    spent, reserved = fold(p, spec)
                except Exception as e:
                    why = f"the record could not be read: {type(e).__name__}: {e}"
            if not why and spent + reserved + r > spec.budget.daily:
                why = (f"{spent:.2f} spent and {reserved:.2f} reserved of {spec.budget.daily:g} today; "
                       f"this run reserves {r:g}")
            if not why:
                _between()
                OPEN.add(run)               # (before its write: recovery never closes a run between the two)
                try:
                    return write(more), None
                except BaseException:
                    OPEN.discard(run)
                    raise
    except OSError as e:                          # (its lock, or the write: not started, either way)
        why = f"the budget's lock or record: {e}"
    refused(p, block.name, {"reserve": r, "spent": spent, "reserved": reserved,
                            "daily": getattr(spec.budget, "daily", None), "why": why})
    return None, why


def ask(p, spec, name: str, reserve) -> tuple[dict | None, str | None]:
    """One of ergostat's own AI calls (``name``) asks to start, reserving ``reserve`` (its per-call cap). Returns
    (its permit, for ``done``, None), (None, why) when refused (``budget.refused`` written), or (None, None) when no
    budget is declared. Under the flock: the read, the decision and the write of its ``budget.call``. With no
    ``spec``, the project's TOML ``[budget]`` (``of``), and a ``reserve`` of 0 or None is its ``max-cost``."""
    if spec is None and (spec := of(getattr(p, "model", None))) is not None and not reserve:
        reserve = spec.budget.max_cost              # (the caller had no spec to take ``max-cost`` from)
    if spec is None or spec.budget is None:
        return None, None
    b, why, spent, reserved = spec.budget, spec.budget.problem(), None, None
    if not why and not (_known(reserve) and 0 < reserve <= b.daily):
        why = f"this call's reserve ({reserve!r}) is not a number above 0 and within daily ({b.daily:g})"
    try:
        with held(p):
            if not why:
                try:
                    spent, reserved = fold(p, spec)
                    w, inc = WITHIN.get() or (os.environ.get("ERGOSTAT_RUN") or None, False)
                    w, inc = (w, inc) if w in read(p, time.time())[0] else (None, False)
                except Exception as e:
                    why = f"the record could not be read: {type(e).__name__}: {e}"
            if not why and spent + reserved + reserve > b.daily:
                why = f"{spent:.2f} spent and {reserved:.2f} reserved of {b.daily:g} today; this call reserves {reserve:g}"
            if not why:
                _between()
                cid = uuid.uuid4().hex
                OPEN.add(cid)
                try:
                    p.events.add(CALL, item=name, source=SOURCE, id=cid, data={
                        "reserve": float(reserve), "pid": os.getpid(), "block": name, "within": w, "included": inc})
                except BaseException:
                    OPEN.discard(cid)
                    raise
                return {"p": p, "id": cid, "name": name, "reserve": float(reserve)}, None
    except OSError as e:
        why = f"the budget's lock or record: {e}"
    refused(p, name, {"reserve": reserve if _known(reserve) else None, "spent": spent, "reserved": reserved,
                      "daily": b.daily, "why": why})
    return None, why


def done(permit: dict | None, cost) -> None:
    """A call's permit closed with its reported cost (unknown: null, charged its reserve); once only."""
    if permit is not None and permit["id"] in OPEN:
        close(permit["p"], permit["name"], permit["id"], float(cost) if _known(cost) else None, "the call ended")


def refused(p, block: str, data: dict) -> None:
    """A refusal recorded, at most once a minute per block in this process."""
    key, mono = (str(p.dir), block), time.monotonic()
    if mono - _said.get(key, -SAID_EVERY) < SAID_EVERY:
        return
    _said[key] = mono
    with contextlib.suppress(Exception):          # (an unwritable record: the run is refused all the same)
        p.events.add(REFUSED, item=block, source=SOURCE, data=data)


def close(p, block: str, run: str, cost: float | None, why: str) -> None:
    """A reserving run ended with no end of its own: ``budget.closed`` (``cost`` None: charged its reserve)."""
    p.events.add(CLOSED, item=block, source=SOURCE, causedby=run, data={"run": run, "cost_usd": cost, "why": why})
    OPEN.discard(run)


def alive(pid) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:                           # (another user's: it is there)
        return True
    return True


def recover(p, spec, every: float = RECOVER_EVERY) -> list[str]:
    """Close each reserving run with no end whose process is gone, or is this one without it open; at most every
    ``every`` seconds. OPEN is read as a copy, taking no other lock inside the flock. Returns the runs closed."""
    if spec.budget is None:
        return []
    key, mono = str(p.dir), time.monotonic()
    if mono - _recovered.get(key, -every - 1) < every:
        return []
    _recovered[key] = mono
    closed = []
    with held(p):
        mine, me = OPEN.copy(), os.getpid()        # (before the read: a run that ends after the copy is seen ended)
        runs, ends = read(p, time.time())
        for run, v in runs.items():
            if run in ends or v["reserve"] <= 0 or (v["pid"] == me and run in mine) or (v["pid"] != me and alive(v["pid"])):
                continue
            close(p, v["block"], run, None, f"its process ({v['pid']}) is gone" if v["pid"] != me else "not open here")
            closed.append(run)
    return closed


def left(p, spec) -> float:
    """``ergostat.budget.left``: daily less spent and reserved. Raises when no budget is declared or the record
    cannot be read: never ``daily``, never 0, for what could not be worked out."""
    from ..numbers.measures import MeasureError
    spec = spec if spec is not None else of(getattr(p, "model", None))
    if spec is None or spec.budget is None:
        raise MeasureError("no budget: is declared in ergostat.yaml (or [budget] in ergostat.toml)")
    try:
        spent, reserved = fold(p, spec)
    except Exception as e:
        raise MeasureError(f"the record could not be read: {type(e).__name__}: {e}") from e
    return spec.budget.daily - spent - reserved


# ---- T1 (SPEC §9.9): a run's reserve as its cap, its sessions' ledger, and the trip

T1 = "stopped at its spend cap (T1)"
RUN_ID = re.compile(r"^[0-9a-f]{32}$")


class Refused(Exception):
    """A session that may not start: why (no cap given, nothing left, the ledger unreadable)."""


def reserve_of(spec, b) -> float:
    """What a run of ``b`` reserves, as the permit decides it: 0 when free, else ``max-cost``."""
    return 0.0 if free(spec, b) else float(spec.budget.max_cost)


def tripped(parts: list[dict], reserve: float) -> bool:
    """T1: the run's reported AI parts reach its reserve. A part of unknown cost counts as the whole reserve, so it
    trips whatever the reserve; with a reserve of 0, any AI use trips."""
    return bool(parts) and sum(float(x["cost_usd"]) if _known(x.get("cost_usd")) else reserve for x in parts) >= reserve


def cap(raw) -> float:
    """``ERGOSTAT_MAX_COST`` read: a finite number of at least 0 (never NaN, ±inf or negative), else refused."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise Refused(f"ERGOSTAT_MAX_COST is not a number: {raw!r}") from None
    if not _known(v):
        raise Refused(f"ERGOSTAT_MAX_COST is not a finite amount of at least 0: {raw!r}")
    return v


def ledger(state_dir, run) -> Path:
    """``<state dir>/budget/<run>.jsonl``, for a run id of 32 hex digits that resolves under ``budget/``."""
    if not isinstance(run, str) or not RUN_ID.match(run):
        raise Refused(f"the run id is not 32 hex digits: {run!r}")
    root = (Path(state_dir) / "budget").resolve()
    f = (root / f"{run}.jsonl").resolve()
    if f.parent != root:
        raise Refused(f"the run's ledger is not under {root}")
    return f


def _ledger_between() -> None:
    """Called under the ledger's flock, after its read and before the append (a test's hook)."""


def take(state_dir, run, most: float) -> tuple[str, float]:
    """Under ``flock`` on the run's ledger: read it, work out what is left of ``most`` (each entry's cost, or its
    reserve while unsettled or of unknown cost), and append an entry reserving all of it. Returns (its id, left)."""
    f = ledger(state_dir, run)
    f.parent.mkdir(mode=0o700, exist_ok=True)
    with open(f, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.seek(0)
        held_: dict[str, float] = {}
        cost: dict[str, float | None] = {}
        try:
            for line in fh.read().splitlines():
                e = json.loads(line)
                if isinstance(e.get("id"), str) and _known(e.get("reserve")):
                    held_[e["id"]] = float(e["reserve"])
                elif isinstance(e.get("id"), str) and "cost" in e and (e["cost"] is None or _known(e["cost"])):
                    cost[e["id"]] = e["cost"]
                else:
                    raise ValueError(f"not a reserve or a cost: {line[:80]}")
        except (ValueError, TypeError, AttributeError) as e:
            raise Refused(f"the run's ledger could not be read: {e}") from None
        if set(cost) - set(held_):
            raise Refused("the run's ledger could not be read: a cost with no reserve")
        left = most - sum(r if cost.get(i) is None else float(cost[i]) for i, r in held_.items())
        _ledger_between()
        if left <= 0:
            raise Refused(f"nothing is left of the run's cap of {most:g}")
        i = uuid.uuid4().hex
        fh.write(json.dumps({"id": i, "reserve": left}) + "\n")
        fh.flush()
    return i, left


def settle(state_dir, run, i: str, cost) -> None:
    """A session's real cost (None: unknown) appended under the flock; a ledger already removed is not made again."""
    try:
        fd = os.open(ledger(state_dir, run), os.O_WRONLY | os.O_APPEND)
    except FileNotFoundError:
        return
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fcntl.flock(fd, fcntl.LOCK_EX)
        fh.write(json.dumps({"id": i, "cost": float(cost) if _known(cost) else None}) + "\n")


def remove(state_dir, run) -> None:
    """The run's own ledger removed, by its validated name, when the run ends."""
    with contextlib.suppress(Refused, FileNotFoundError):
        ledger(state_dir, run).unlink()
