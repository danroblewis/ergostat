"""Act-risk (SPEC §12k): an action declared with ``risk: {severity: S, threshold: T}`` is gated one step stricter when
this act is riskier than its class. Plain arithmetic, no AI:

    act_risk = S × (1 + s) × (1 + 4c) × (1 + n)        step  ⇔  act_risk ≥ T

``s``: 1 when the action's work item moved (an event by another writer, ``seq`` after the asking run's start) under
the run that planned it, else 0; ``c``: the asking block's contradicted share of its checked claims over the last week
(``trust.WEEK``); ``n``: 0 when another action of the same name ran (exit 0) within the last 90 days, else 1. Every
input that cannot be read counts as the worst case (s = 1, c = 1, n = 1), each with its own reason. A step goes
``auto`` → ``approve`` → ``deny``, never back."""

from __future__ import annotations

import math
import time

ORDER = ("auto", "approve", "deny")      # least to most strict
COLUMNS = ("normal", "away", "maintenance", "freeze", "incident")      # what the operating state picks (SPEC §12k)
NOVEL = 90 * 86400.0                     # how far back a run of the same action makes it known
THRESHOLD = 8.0                          # T's default
HIGHEST = 100.0                          # the largest score: S=5, s=1, c=1, n=1
START = "agent.started"                  # a run's start: its event's id is the run's id


def clamp(x) -> float:
    """A share held to [0, 1]; anything not a finite number (NaN, ±inf, text) is the worst case, 1."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 1.0
    return min(1.0, max(0.0, x)) if math.isfinite(x) else 1.0


def contradicted(p, block: str | None, now: float) -> tuple[float, str]:
    """c, and why it is what it is."""
    if not block:
        return 1.0, "no asking block"
    try:
        from ..claims import record, trust
        got = trust.counts(list(record.stored(p, since=now - trust.WEEK).values()), block)
    except Exception:                                    # noqa: BLE001 - unreadable is the worst case (lesson-3)
        return 1.0, "claims record unreadable"
    if not got.get("claims"):
        return 1.0, "no claims on record"
    if not got.get("checked"):
        return 1.0, "claims made, none checked"
    share = got.get("contradicted_share")
    c = clamp(share)
    return c, "contradicted share" if c == share else f"contradicted share {share!r}, held to {c:g}"


def novelty(p, name: str, now: float, aid: str | None = None) -> tuple[int, str]:
    """n: 0 when another action of this name reached ``ran`` within the last 90 days, else 1 (a ``failed`` one does
    not count). Keyed by the action's name only: one whose command changed under the same name is known."""
    try:
        from . import record as rec
        for a in rec.stored(p, since=now - NOVEL).values():
            if a.get("action") == name and a["id"] != aid and \
                    any(m["to"] == "ran" and m["time"] >= now - NOVEL for m in a["moves"]):
                return 0, "ran within 90 days"
    except Exception:                                    # noqa: BLE001
        return 1, "action record unreadable"
    return 1, "not run within 90 days"


def staleness(p, run: str | None, item: str | None) -> tuple[int, str]:
    """s: 1 when ``item`` has an event by a writer other than ``run`` (not caused by it) with a ``seq`` after the run's
    start, else 0. Ordered by ``seq``, never by time (lesson-2); anything not found or not read is 1 (lesson-3)."""
    if not run:
        return 1, "no asking run"
    if not item:
        return 1, "no work item"
    try:
        start = p.events.get(run)                        # (get also takes an id's prefix: the id and type are checked)
        if not start or start.get("id") != run or start.get("type") != START or not isinstance(start.get("seq"), int):
            return 1, "the run's start not found"
        moved = [e for e in p.events.query(n=None, item=item, after_seq=start["seq"]) if e.get("causedby") != run]
    except Exception:                                    # noqa: BLE001
        return 1, "record unreadable"
    if moved:
        return 1, f"{item} moved by another writer since the run started"
    return 0, "not moved since the run started"


def inputs(p, name: str, block: str | None, aid: str | None = None, now: float | None = None,
           run: str | None = None, item: str | None = None) -> dict:
    now = time.time() if now is None else now
    s, s_why = staleness(p, run, item)
    c, c_why = contradicted(p, block, now)
    n, n_why = novelty(p, name, now, aid)
    return {"s": s, "s_why": s_why, "c": c, "c_why": c_why, "n": n, "n_why": n_why}


def score(severity: int, c: float, n: int, s: int) -> float:
    return float(severity * (1 + s) * (1 + 4 * c) * (1 + n))


def step(gate: str, act_risk: float, threshold: float) -> str:
    """The gate one step stricter when the score reaches the threshold; an unknown gate is ``deny``."""
    i = ORDER.index(gate) if gate in ORDER else len(ORDER) - 1
    return ORDER[min(i + 1, len(ORDER) - 1)] if act_risk >= threshold else ORDER[i]


def stricter(a: str | None, b: str | None) -> str:
    return ORDER[max(ORDER.index(g) if g in ORDER else len(ORDER) - 1 for g in (a, b))]


def schedule(normal: str, written: dict | None = None) -> dict:
    """Each column's gate, as written, else a default never looser than ``normal``'s: away and maintenance take it,
    freeze is it one step stricter, incident is ``deny``."""
    w = written or {}
    return {"normal": normal, "away": w.get("away", normal), "maintenance": w.get("maintenance", normal),
            "freeze": w.get("freeze", step(normal, 1.0, 1.0)), "incident": w.get("incident", "deny")}


def column(action, o) -> str | None:
    """The column the operating state ``o`` (``operating.read``) picks for ``action``. None: a state read as incident
    because it was unsure, or one not known: ``deny``, whatever is written."""
    from .operating import STATES
    if o is None or o.unsure or o.state not in STATES:
        return None
    if o.state in ("freeze", "incident"):
        return o.state
    if o.state == "maintenance" and action.name in o.actions:
        return "maintenance"
    return "normal" if o.presence == "present" else "away"


def cell(action, o) -> tuple[str, float, str]:
    """The gate and threshold in force for ``action`` under ``o``, and the column they came from. An action whose
    cells were not compiled from ``actions:`` (no ``gates``: a notify channel's) is not scheduled: its gate as written,
    whatever the state, column ``unscheduled``."""
    if not action.gates:
        return action.gate if action.gate in ORDER else "deny", action.threshold, "unscheduled"
    col = column(action, o)
    if col is None:
        return "deny", action.threshold, "unsure"
    g = action.gates.get(col)
    return g if g in ORDER else "deny", float((action.thresholds or {}).get(col, action.threshold)), col


def assess(p, action, block: str | None, aid: str | None = None, gate: str | None = None,
           threshold: float | None = None, run: str | None = None, item: str | None = None) -> dict | None:
    """The act's reading (None for an action without ``risk:``): its score, inputs and its gate (``gate``: the
    column's, else the action's), stepped at ``threshold``. ``run``, ``item``: the asking run and its work item."""
    if action.severity is None:
        return None
    gate, threshold = gate or action.gate, action.threshold if threshold is None else threshold
    got = inputs(p, action.name, block, aid, run=run, item=item)
    s = score(action.severity, got["c"], got["n"], got["s"])
    return {"score": s, "severity": action.severity, "threshold": threshold, **got, "gate": step(gate, s, threshold)}


def note(risk: dict | None, base: str | None) -> str | None:
    """What the score says, when it reached the threshold: the step, or that the gate is ``deny`` already."""
    if not risk or "score" not in risk or risk["score"] < risk["threshold"]:
        return None
    head = f"act-risk {risk['score']:g} ≥ {risk['threshold']:g}: its gate"
    return f"{head} is {base} already" if risk["gate"] == base else f"{head} {base} stepped to {risk['gate']}"
