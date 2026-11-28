"""Where a goal off is stuck (SPEC §8, *Where a goal off is stuck*): its loop followed from the stock to the blocks
that act for it and onward, and the first place it stops said in one line, with a link to what is stuck.

Each block that acts for the goal (its ``goal:``; on a model without blocks, the agents of its valves), in turn:
it has never run, or not for several of its runs; its last run failed (its note); it is capped by its day's spend
(the modelling template's ``--daily``); its last runs produced nothing (no opening, command, decision, event or
proposal, nor any change to the model it made), with what its last run said (the last line of its own run log).
A block that makes changes to the model (modelling's drafter, modeller, fixer, improver, redesigner) is followed
through them, from the changes store (the item index's ``ergostat.model-change`` table, the day's), counted by what
became of each: waiting for the owner, with the judge or the reviewer, written, sent back or rejected by the
reviewer, failed by the judge, refused at check, superseded, dismissed. Once something acted (a change written, a
valve opened), the stock: whether it moved toward its setpoint over the window.

Said at once, as soon as the goal is off: these are the loop's steps as they stand, not a verdict that waits for
record (the saturation suggestion, ``diagnosis_in``, does). Reads only what is kept: the snapshot's agents (each
block's runs and its newest run, from the item index), its last three runs, the changes table, the spend ledger,
one run log's tail. Never a scan of the record."""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import quote

from .durations import human

DAY = 86400.0
RUNS = 3                                     # the last runs read for whether a block produced anything
MADE = ("openings", "commands", "decisions", "events", "proposed", "claims", "routes", "answers")
CHANGES = "ergostat.model-change"

# what became of a change, in the order a change goes (the first a stop is said first)
STEPS = (
    ("you", "wait for you", True),
    ("judge", "with the judge", False),
    ("reviewer", "wait for the reviewer", False),
    ("written", "written", False),
    ("sent-back", "sent back by the reviewer", True),
    ("rejected", "rejected by the reviewer", True),
    ("failed", "failed by the judge", True),
    ("refused", "refused at check", True),
    ("superseded", "superseded (the model changed)", True),
    ("dismissed", "dismissed by you", True),
    ("inconclusive", "inconclusive (the judge needs more record)", True),
)
WORDS = {k: w for k, w, _ in STEPS}
STATE_OF = {"you": "passed", "judge": "testing", "reviewer": "reviewing", "written": "accepted", "sent-back": "sent-back",
            "rejected": "rejected", "failed": "failed", "refused": "refused", "superseded": "superseded",
            "dismissed": "dismissed", "inconclusive": "inconclusive"}


def _q(s: str) -> str:
    s = " ".join(str(s or "").split())
    return f"“{s[:117] + '...' if len(s) > 120 else s}”"


def agent_link(name: str) -> str:
    return f"/agents/{quote(name)}"


def changes_link(step: str, by: list[str]) -> str:
    """The changes in that step, listed: the ``ergostat.model-change`` items in its state, searched for their maker."""
    q = f"state={STATE_OF[step]}&finished=show"
    return f"/{CHANGES}?{q}" + (f"&q={quote(by[0])}" if len(by) == 1 else "")


def actors(spec, m, name: str, lp: dict) -> list[str]:
    """Who acts for the goal: the blocks whose ``goal:`` it is (a judge's work is followed through the changes), else
    the agents of its valves."""
    if spec is not None:
        got = [b.name for b in spec.blocks.values() if b.goal == name and not b.implied and not b.builtin]
        if got:
            return got
    return list(dict.fromkeys(a for v in lp.get("valves") or [] if (a := getattr(m.valves.get(v), "agent", None))))


def said_by(p, run: dict | None) -> str:
    """What a run said last: the last plain line of its own run log (``logs/runs/...``), read from its tail only."""
    rel = ((run or {}).get("data") or {}).get("log")
    if not rel:
        return ""
    try:
        f = Path(p.dir) / rel
        with open(f, "rb") as fh:
            size = fh.seek(0, 2)
            fh.seek(max(0, size - 4096))
            tail = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    lines = [x.strip() for x in tail.splitlines() if x.strip() and not x.lstrip().startswith(("{", "["))]
    return lines[-1][:300] if lines else ""


def capped(p, spec, name: str, now: float) -> str | None:
    """The block is capped by its day's spend: a modelling AI block's ``--daily`` (and its ``--budget``, the most one
    session reserves) against the spend ledger's day."""
    b = spec.blocks.get(name) if spec is not None else None
    run = str((b.params.get("run") if b is not None else "") or "")
    m = re.search(r"--daily\s+([0-9.]+)", run)
    if not m:
        return None
    from .numbers import modeller_spend as sp
    daily = float(m.group(1))
    got = sp.today(p, now)
    if "unreadable" in got:
        return f"the {name} cannot spend: {got['unreadable']}"
    budget = re.search(r"--budget\s+([0-9.]+)", run)
    reserve = float(budget.group(1)) if budget else float(got.get("last") or 0)
    if got["spent"] + reserve > daily or (daily <= 0):
        return (f"the {name} is capped: ${got['spent']:.2f} of ai-daily's ${daily:.2f} spent today"
                + (f" (a session reserves ${reserve:.2f})" if reserve else ""))
    return None


def _kind_of(spec, x: dict) -> str:
    """What became of a change, as one of STEPS's keys."""
    from .numbers import reviewer as rv
    st = x.get("state")
    if st in ("checked", "testing"):
        return "judge"
    if st == "reviewing":
        return "reviewer"
    if st == "passed":
        if spec is not None and rv.unread(spec, x):
            return "reviewer"
        if spec is not None and not rv.read_for_owner(spec, x) and rv.awaiting(spec, x):
            return "reviewer"
        return "you"
    if st in ("accepted", "verified", "regressed"):
        return "written"
    return st if st in WORDS else "superseded"


def _finding(kind: str, x: dict) -> str:
    """The latest word on a change in that step: the reviewer's finding, the judge's or check's why."""
    if kind == "sent-back":
        r = x.get("review") or {}
        f = [g.get("says") for g in r.get("findings") or [] if g.get("says")]
        return f[0] if f else str(x.get("why") or "").split(": ", 1)[-1]
    if kind in ("rejected", "failed", "inconclusive"):
        return str((x.get("verdict") or {}).get("why") or "").removeprefix("the reviewer rejected it: ")
    if kind in ("refused", "superseded", "dismissed"):
        return str(x.get("why") or x.get("reason") or "")
    return ""


def changes_of(p, since: float) -> dict[str, dict]:
    """The changes to the model made since ``since``, from the changes table (superseded ones too)."""
    from .spec import projections
    return {pid: {**f, "id": pid, "state": st} for pid, (st, f) in projections.stored(p, "change", since=since).items()}


def changes_step(spec, made: list[dict], by: list[str]) -> dict | None:
    """The changes the goal's blocks made, counted by what became of them: the step, its counts, the stuck one."""
    if not made:
        return None
    counts: dict[str, int] = {}
    latest: dict[str, str] = {}
    for x in made:                                   # (oldest first: the last one seen is the latest)
        k = _kind_of(spec, x)
        counts[k] = counts.get(k, 0) + 1
        if w := _finding(k, x):
            latest[k] = w
    order = [k for k, _, _ in STEPS if counts.get(k)]
    stops = [k for k, _, stop in STEPS if stop and counts.get(k)]
    moving = any(counts.get(k) for k in ("judge", "reviewer", "written"))
    if counts.get("you"):
        stuck = "you"
    elif not moving and stops:                        # nothing went on: the commonest end first
        stuck = max(stops, key=lambda k: counts[k])
    else:
        stuck = None
    first = stuck or next((k for k in ("judge", "reviewer") if counts.get(k)), None)
    if first:
        order.remove(first)
        order.insert(0, first)

    def part(k: str) -> str:
        n, w = counts[k], WORDS[k]
        if k == "you":
            w = "waits for you" if n == 1 else "wait for you"
        return f"{n} {w}" + (f" (latest: {_q(latest[k])})" if latest.get(k) else "")
    who = " and the ".join(by)
    total = len(made)
    says = f"{total} change{'s' if total != 1 else ''} the {who} made over the last day: " + ", ".join(part(k) for k in order)
    link = ("/inbox" if first == "you" else changes_link(first, by)) if first else changes_link(order[0], by)
    return {"step": "changes", "says": says, "stuck": stuck is not None, "link": link,
            "counts": [{"what": k, "says": WORDS[k], "n": counts[k], "latest": latest.get(k),
                        "link": "/inbox" if k == "you" else changes_link(k, by)} for k in order],
            "written": counts.get("written", 0), "moving": moving, "at": first}


def block_step(p, snap: dict, m, spec, name: str, now: float, made_changes: int | None) -> dict:
    """One block's step: never ran, not for long, its last run failed, capped, produced nothing; else it ran."""
    from .state import _missed
    a = snap["agents"].get(name) or {}
    ag = m.agents.get(name)
    sched = getattr(ag, "schedule", "") or ""
    b = spec.blocks.get(name) if spec is not None else None
    on = f" ({sched})" if sched else f" (it runs while {b.goal} is off)" if b is not None and b.goal else ""
    out = {"step": "block", "block": name, "link": agent_link(name), "runs": a.get("runs") or 0,
           "failed": a.get("failed") or 0}
    last = a.get("last")
    if a.get("running_since"):
        return {**out, "stuck": False, "says": f"the {name} is running (for {human(now - a['running_since'])})"}
    if last is None:
        return {**out, "stuck": True, "says": f"the {name} has never run{on}"}
    data = last.get("data") or {}
    ago = human(max(1.0, now - last["time"]))
    if a.get("failing"):
        note = data.get("note") or (f"exit {data['exit']}" if data.get("exit") is not None else "failed")
        return {**out, "stuck": True, "says": f"the {name}'s last run failed ({ago} ago): {note}"}
    if c := capped(p, spec, name, now):
        return {**out, "stuck": True, "says": c}
    if ag is not None and (ag.every or ag.cron) and _missed(ag, last["time"], now):
        return {**out, "stuck": True, "says": f"the {name} has not run for {ago}{on}"}
    from .spec.projections import query
    runs = query(p, "agent.ran", item=name, n=RUNS, until=now)
    nothing = runs and not any(sum(int((r.get("data") or {}).get(k) or 0) for k in MADE) for r in runs)
    if nothing and made_changes is not None:          # a maker of changes: what it made since the first of them
        start = runs[0]["time"] - float((runs[0].get("data") or {}).get("seconds") or 0)
        nothing = not any(x.get("made_by") == name for x in changes_of(p, start - 1).values())
    if nothing:
        k = len(runs)
        said = said_by(p, runs[-1])
        what = "proposed nothing" if made_changes is not None else "produced nothing"
        return {**out, "stuck": True, "says": (f"the {name}'s last run {what}" if k == 1 else f"the {name}'s last {k} runs {what}")
                + (f": {said}" if said else "")}
    return {**out, "stuck": False, "says": f"the {name} ran {ago} ago"}


def _makes_changes(spec, name: str) -> bool:
    b = spec.blocks.get(name) if spec is not None else None
    if b is None:
        return False
    for r in b.targets():
        f = spec.flows.get(r.name) if r.kind == "flow" else None
        for s in (getattr(f, "sensors", None) or {}).values():
            if (getattr(s, "items", None) or {}).get("kind") == CHANGES:
                return True
    return False


def of(p, snap: dict, name: str, now: float | None = None, made: dict | None = None) -> dict | None:
    """Where goal ``name``'s loop stops: ``{"says", "link", "steps": [{"step", "says", "stuck", "link", ...}]}``, the
    first stop's words as ``says`` (else the step furthest along); None when nothing acts for it."""
    m = p.model
    spec = getattr(m, "spec", None)
    lp = snap["loops"].get(name) or {}
    now = now or snap.get("at") or time.time()
    who = actors(spec, m, name, lp)
    if not who:
        return None
    steps: list[dict] = []
    makers = [n for n in who if _makes_changes(spec, n)]
    for n in who:
        steps.append(block_step(p, snap, m, spec, n, now, 0 if n in makers else None))
    ch = None
    if makers:
        made = made if made is not None else changes_of(p, now - DAY)
        mine = [x for x in made.values() if x.get("made_by") in makers]
        ch = changes_step(spec, mine, makers)
        if ch is not None:
            steps.append(ch)
            if ch.get("at") == "reviewer" and "model-reviewer" in getattr(spec, "blocks", {}):
                rv = block_step(p, snap, m, spec, "model-reviewer", now, None)
                if rv["stuck"] and "produced nothing" not in rv["says"]:
                    steps.append(rv)
    acted = (ch or {}).get("written") or sum(int(((snap["agents"].get(n) or {}).get("last") or {}).get("data", {}).get("openings")
                                                 or 0) for n in who)
    stock = lp.get("stock")
    if acted and stock:
        s = snap["stocks"].get(stock) or {}
        change = s.get("change")
        op = str(lp.get("setpoint") or "").split(" ")[0]
        toward = (change or 0) < 0 if op.startswith("<") else (change or 0) > 0 if op.startswith(">") else bool(change)
        if not toward:
            moved = ("did not move" if not change else f"{'rose' if change > 0 else 'fell'} by {_n(abs(change))}")
            steps.append({"step": "stock", "stuck": True, "link": None,
                          "says": f"it acted, and {stock} {moved} over the last {human(snap.get('window') or 3600)}"})
    stop = next((s for s in steps if s.get("stuck")), None)
    if stop is None and ch is not None and ch.get("at"):
        stop = ch                                      # nothing stops: where it is (with the judge, the reviewer)
    if stop is None:
        return {"says": None, "link": None, "steps": steps}
    return {"says": stop["says"], "link": stop.get("link"), "steps": steps}


def _n(x: float) -> str:
    from .state import fmt
    return fmt(x)


def attach(p, snap: dict) -> None:
    """Each goal off in the snapshot given where it is stuck (``loops[NAME]["stuck"]``); the changes read once."""
    off = [n for n, lp in snap["loops"].items() if lp.get("status") == "off"]
    if not off:
        return
    now = snap.get("at") or time.time()
    made = None
    for n in off:
        try:
            if made is None and getattr(p.model, "spec", None) is not None:
                made = changes_of(p, now - DAY)
            got = of(p, snap, n, now, made)
        except Exception as e:                         # never the status's undoing
            got = {"says": f"cannot follow its loop ({type(e).__name__}: {e})", "link": None, "steps": []}
        if got and got.get("says"):
            snap["loops"][n]["stuck"] = got
