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
- **Recovery** (``recover``): a reserving run with no end whose process is gone, or is this one but no longer has it
  open (``OPEN``), is closed (``budget.closed``, cost unknown: charged its reserve for a day from the close).
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import time

from ..leases import TAKEN
from . import record as cr

SOURCE = "ergostat"
STARTED, CLOSED, REFUSED = "agent.started", "budget.closed", "budget.refused"
DAY, WEEK = 86400.0, 7 * 86400.0
FREE = ("person", "decision", "program", "rule")   # the agent kinds whose non-ai runs are free (an allowlist)
OPEN: set[str] = set()                     # the reserving runs this process has open (added under the flock)
SAID_EVERY, RECOVER_EVERY = 60.0, 60.0
_said: dict[tuple[str, str], float] = {}   # (state dir, block) → when (monotonic) a refusal was last recorded
_recovered: dict[str, float] = {}          # state dir → when (monotonic) it was last recovered


def _between() -> None:
    """Called under the flock, after the read and the decision and before the write (a test's hook)."""


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


def _charge(e: dict, reserve: float | None, cap: float) -> float:
    """One end's charge: its known cost; unknown, its reserve (0 for a free run or one whose start is not in the
    window), or ``max-cost`` when it used AI at no known price, or a close of unknown cost with no reserve."""
    d = e.get("data") or {}
    if e["type"] == CLOSED:
        return float(d["cost_usd"]) if _number(d.get("cost_usd")) else reserve or cap
    n = cr.numbers(e)
    if n["cost_usd"] is not None:
        return float(n["cost_usd"])
    return cap if isinstance(d.get("ai"), dict) else reserve or 0.0


def read(p, now: float) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """The reserving runs of the last 7 days (run → reserve, pid, block) and the ends of the same 7 days, by run."""
    runs: dict[str, dict] = {}
    for e in p.events.query(n=None, type=f"{TAKEN},{STARTED}", source=SOURCE, since=now - WEEK):
        d = e.get("data") or {}
        if _number(d.get("reserve")):
            run = d.get("run") if e["type"] == TAKEN else e["id"]
            runs[run] = {"reserve": float(d["reserve"]), "pid": d.get("pid"), "block": d.get("block") or e.get("item")}
    ends: dict[str, list[dict]] = {}
    for e in p.events.query(n=None, type=f"{cr.ENDS},{CLOSED}", source=SOURCE, since=now - WEEK):
        run = (e.get("data") or {}).get("run") if e["type"] == CLOSED else e.get("causedby")
        ends.setdefault(run or e["id"], []).append(e)        # (an end of no run: on its own)
    return runs, ends


def fold(p, spec, now: float | None = None) -> tuple[float, float]:
    """(spent, reserved) over the trailing day; raises when the record cannot be read."""
    now = time.time() if now is None else now
    runs, ends = read(p, now)
    spent = 0.0
    for run, es in ends.items():
        r = runs[run]["reserve"] if run in runs else None
        day = [_charge(e, r, spec.budget.max_cost) for e in es if e["time"] >= now - DAY]
        spent += max(day, default=0.0)
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
        runs, ends = read(p, time.time())
        mine, me = OPEN.copy(), os.getpid()
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
    if spec is None or spec.budget is None:
        raise MeasureError("no budget: is declared in ergostat.yaml")
    try:
        spent, reserved = fold(p, spec)
    except Exception as e:
        raise MeasureError(f"the record could not be read: {type(e).__name__}: {e}") from e
    return spec.budget.daily - spent - reserved
