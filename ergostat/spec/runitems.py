"""``ergostat.run``, the built-in projection of runs (SPEC §9.1, *A run is an object*): one object per run of a machine
block, ``ergostat.run/<block>/<run id>``, folded from the events every run already writes (``agent.started``, and its
``agent.ran`` or ``agent.failed``, caused by it), so nothing more is written per run than the end's ``said``.

Those events are about the block (their item is its name), not about the run, so the run's object is not told by
their item: each is read here as the run's own (``derive``: the same event, its id, type and time, about the run,
its data the run's fields: running, then ran or failed, its ``outcome`` in a word: ran, failed, timed-out, stopped).
The item index folds what it derives as the events arrive (it reads them already, for the status's ``latest``), and
an item's page reads one run's events by its id and
by what they caused (``events_of``: two lookups, never a scan). A run's object lives as long as its ``agent.started``
is kept: they are loose events, never rolled up, pruned with the record (``storage``), and its row in the index goes
with them (``Index._reconcile``). Its log file is pruned sooner (``storage: logs: runs:``): ``log`` names it
while it is kept, ``said`` (the last lines it wrote, on its end event) stays.

Volume: a busy block makes many runs (a factory-size record: half its events are runs'), so the item index keeps
each block's newest ``KEPT`` runs, one row each, and takes the older out as new ones arrive (``Index._cap_runs``,
reading that block's id range alone): what every listing and count of the index costs stays bounded by the blocks,
never by the record's length. An older run is still an object: its page (``items.detail``, ``ergostat item``) reads
its two events from the record by its id while they are kept. A block's runs are an id range (``prefix``:
``block``), so an agent's page lists its runs a page at a time, counted and paged by the index."""

from __future__ import annotations

from .ir import ItemKind, Relation

RUN = "ergostat.run"
STATES = ["running", "ran", "failed"]
FINISHED = ["ran", "failed"]
TYPES = ("agent.started", "agent.ran", "agent.failed")
MARK = "~run"                       # a derived event's mark: only these fold into a run (never one pushed as one)
STOPPED = ("stopped with ergostat", "stopped as the owner asked")   # (runner.STOPPED_WITH_US, engine.STOPPED_BY_OWNER)
TIMEOUT = "stopped after its timeout"
KEPT = 200                          # each block's newest runs the item index keeps (the older: read from the record by id)


def run_kind(sessions=("session",)) -> ItemKind:
    """``sessions``: the projections its AI sessions are items of (the built-in ``session``, or the one the model
    declares for ``session/*``)."""
    on = dict(zip(TYPES, STATES, strict=True))
    return ItemKind(RUN, f"{RUN}/*", list(STATES), on,
                    ["block", "outcome", "trigger", "seconds", "cost_usd", "moved", "said"], {}, None,
                    "one run of a machine block: what started it, how it ended, what it moved, cost and said, and its "
                    "log while kept; folded from its agent.started and agent.ran or agent.failed (built in, SPEC §9.1)",
                    fold={"sessions": "union"}, relations={"sessions": Relation("sessions", list(sessions))} if sessions else {},
                    finished=list(FINISHED), lost=["failed"], prefix="block")


def id_of(block: str, run: str) -> str:
    return f"{RUN}/{block}/{run}"


def run_of(id: str) -> tuple[str, str] | None:
    """``(block, run id)`` of a run's object id; None for any other."""
    if not isinstance(id, str) or not id.startswith(RUN + "/"):
        return None
    block, _, run = id[len(RUN) + 1:].rpartition("/")
    return (block, run) if block and run else None


def moved_text(d: dict) -> str:
    """What a run did, as ``ergostat block NAME --now`` says it: the flows it moved and the lines it wrote."""
    parts = [f"{v:g} along flow.{k}" for k, v in (d.get("moved") or {}).items() if isinstance(v, (int, float)) and v]
    flows = "moved " + ", ".join(parts) if parts else "moved nothing"
    did = [f"{d[k]} {w}" for k, w in (("openings", "openings"), ("commands", "commands"), ("decisions", "decisions"),
                                      ("events", "events"), ("proposed", "proposed"), ("claims", "claims"),
                                      ("answers", "answers"), ("refused", "refused"))
           if isinstance(d.get(k), int) and d.get(k)]
    return flows + (f"; {', '.join(did)}" if did else "")


def outcome_of(e: dict) -> str:
    """How a run ended, in a word: ran, failed, timed-out, or stopped (by the owner, or with ergostat: not a failure)."""
    note = str((e.get("data") or {}).get("note") or "")
    if e["type"] == "agent.failed":
        return "timed-out" if note.startswith(TIMEOUT) else "failed"
    return "stopped" if note in STOPPED else "ran"


def derive(e: dict) -> dict | None:
    """The run's own reading of one of ``TYPES`` (None for any other, or one that names no run): the same event (its
    id, type, time and seq), about the run, its data the run's fields."""
    t, block = e.get("type"), e.get("item")
    if t not in TYPES or not isinstance(block, str) or not block or "/" in block:
        return None
    d = e.get("data") if isinstance(e.get("data"), dict) else {}
    if t == "agent.started":
        run = e.get("id")
        cmd = d.get("command") if isinstance(d.get("command"), dict) else None
        data = {"block": block, "outcome": "running", "started": e.get("time"), "trigger": d.get("trigger"),
                **{k: d[k] for k in ("rung", "item", "model", "timeout") if d.get(k) is not None},
                **({"command": cmd.get("amount"), "commanded_by": cmd.get("from")} if cmd else {}),
                **({"cause": e["causedby"]} if e.get("causedby") else {})}
    else:
        run, state = e.get("causedby") or e.get("id"), outcome_of(e)     # (an end with no start: a run of its own)
        ai = d.get("ai") if isinstance(d.get("ai"), dict) else {}
        res = d.get("resources") if isinstance(d.get("resources"), dict) else {}
        cost = ai.get("cost_usd") if ai else d.get("cost_usd")
        toks = (ai.get("tokens") or {}).get("total") if isinstance(ai.get("tokens"), dict) else None
        sessions = [s for s in (ai.get("items") or []) if isinstance(s, str)]
        data = {"block": block, "outcome": state, "ended": e.get("time"), "moved": moved_text(d),
                **{k: d[k] for k in ("seconds", "exit", "note", "said", "item") if d.get(k) is not None},
                **({"log": f"file:{d['log']}"} if isinstance(d.get("log"), str) else {}),   # (shown while kept)
                **({"flows": d["moved"]} if isinstance(d.get("moved"), dict) and d["moved"] else {}),
                **({"cost_usd": cost} if isinstance(cost, (int, float)) else {}),
                **({"cost": ai["cost"]} if ai.get("cost") else {}),
                **({"tokens": toks} if isinstance(toks, (int, float)) else {}),
                **({"ai_model": ai["model"]} if ai.get("model") else {}),
                **({"cpu": res["cpu"]} if isinstance(res.get("cpu"), (int, float)) else {}),
                **({"memory": res["memory_peak"]} if isinstance(res.get("memory_peak"), (int, float)) else {}),
                **({"sessions": sessions} if sessions else {}),
                **({"error": d.get("note") or "failed"} if state in ("failed", "timed-out") else {})}
    if not isinstance(run, str) or not run:
        return None
    return {"id": e.get("id"), "seq": e.get("seq"), "time": e.get("time"), "type": t,
            "item": id_of(block, run), "source": e.get("source"), "causedby": e.get("causedby"), "data": data,
            MARK: True}


def derived(evs) -> list[dict]:
    return [x for e in evs if (x := derive(e)) is not None]


def events_of(events, id: str, until: float | None = None) -> list[dict]:
    """One run's own events, oldest first: its start by its id, its end by what it caused (two lookups)."""
    got = run_of(id)
    if got is None:
        return []
    block, run = got
    start = events.get(run)
    evs = [start] if start and start.get("id") == run and (start.get("type") == "agent.started" or start.get("type")
                                                          in TYPES and not start.get("causedby")) else []
    evs += [e for e in events.caused_by(run) if e.get("type") in ("agent.ran", "agent.failed")]
    if until is not None:
        evs = [e for e in evs if e["time"] <= until]
    out = [x for x in derived(evs) if x["item"] == id]
    return sorted(out, key=lambda e: (e.get("seq") or 0))


def all_of(events, until: float | None = None) -> list[dict]:
    """Every run's own events (a record kept nowhere on disk: no index to follow them)."""
    return derived(events.query(n=None, type=",".join(TYPES), until=until))


def said_of(text: str, most: int = 5, cap: int = 2000) -> str:
    """What a run said: the last ``most`` plain lines of its log's tail (not JSON: those are what it reported),
    at most ``cap`` characters, the newest kept."""
    lines = [x.rstrip() for x in (text or "").splitlines() if x.strip() and not x.lstrip().startswith(("{", "["))]
    out = "\n".join(x[:500] for x in lines[-most:])
    return out[-cap:]
