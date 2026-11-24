"""A narrow AI's specification and a decision's means of deciding (docs/proposals/agent-means.md): nothing new is
declared, so both are read from the block as compiled and from the record, declared and recorded kept apart.

- **spec**: the block's contract, in the proposal's order (what it works, may move, may use, costs, how it is
  answered), and what its runs wrote, read from the record (``emits`` is no block key). A built-in names the module
  that computes it, the first paragraph of its docstring, and its declared keys.
- **spans**: the block's rung per span of the model's recorded versions (``model.changed``, ordered by ``seq``, never
  by time), a span where it was not in the model kept as a gap. Each span carries its own counts over the window, so a
  rung's record never mixes with the one it replaced, nor a block made again under its name with the one removed:
  - **may / did**, for item work: one row per ``takes.to`` state (0 when never reached), the lease ends that left the
    item elsewhere (``other``: given back, a dead letter, expired), and the ends whose take is not in the record
    (``unattributed``, of the kind it takes: they may be another block's), each by its take's ``seq``;
  - **said / carried out**, for a controller: its ``controller.decided`` words, numbers taken out, once per run (a
    block serving two goals writes each line once per goal), and per ``out`` port the commands acted on as each kind of
    port records them. A block another block also commands records only its last commander, so its row says ``shared
    with`` and counts nothing; a goal (a setpoint) records nothing, said ``not recorded``."""

from __future__ import annotations

import dataclasses
from bisect import bisect_right
from fnmatch import fnmatchcase

from .leases import ENDED, EXPIRED, TAKEN
from .state import decision_kind

DAY = 86400.0
ROWS = (("what it works", ("takes", "on", "in")), ("what it may move", ("out", "actions", "max", "min")),
        ("what it may use", ("tools", "read", "read-only", "network", "workdir", "workspace")),
        ("what it costs and how long", ("model", "timeout", "max-cost")), ("how it is answered", ("parse", "goal", "until")))
OWN_MODULE = {"judge": "ergostat.intent.judge"}
OWN_KEYS = ("judge", "kinds", "model", "max-cost", "threshold")


def _plain(v):
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {k: _plain(x) for k, x in dataclasses.asdict(v).items() if x not in (None, [], {}, "") and x is not False}
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_plain(x) for x in v]
    return v if isinstance(v, (str, int, float, bool)) or v is None else str(v)


def _value(spec, b, k: str):
    a = spec.agents.get(b.agent) if b.agent else None
    got = {"takes": b.takes, "on": b.on, "in": {p: str(r) for p, r in b.inputs.items()} or None,
           "out": {p: [str(r) for r in rs] for p, rs in b.outputs.items()} or None, "max": b.max, "min": b.min,
           "model": b.params.get("model") or (a.model if a else None), "timeout": b.timeout,
           "max-cost": spec.budget.max_cost if spec.budget is not None else None}
    return _plain(got[k] if k in got else b.params.get(k))


def spec_rows(p, spec, b, lo: float, hi: float) -> list:
    """Its specification, as ``[shown, [[key, value], ...]]`` groups, keys not written left out."""
    if b.builtin:
        from .web.agent_spec import _doc
        mod = OWN_MODULE.get(b.type)
        pol = b.params.get("intent")
        keys = [[k, _plain(b.params.get(k, getattr(pol, k.replace("-", "_"), None)))] for k in OWN_KEYS]
        return [["computed by", [["module", f"ergostat's own: {mod}" if mod else f"ergostat's built-in {b.type}"],
                                 *([["what it does", _doc(mod)]] if mod and _doc(mod) else [])]],
                ["its keys", [kv for kv in keys if kv[1] not in (None, "", [], {})]]]
    out = [[shown, [[k, v] for k in keys if (v := _value(spec, b, k)) not in (None, "", [], {})]] for shown, keys in ROWS]
    wrote: dict[str, int] = {}
    for e in p.events.query(n=None, source=b.name, since=lo, until=hi):
        wrote[e["type"]] = wrote.get(e["type"], 0) + 1
    out.append(["what its runs wrote (from the record)", sorted(([t, n] for t, n in wrote.items()), key=lambda r: -r[1])])
    return [g for g in out if g[1]]


def rung_of(model, name: str) -> str | None:
    a = model.agents.get(name)
    return a.kind if a is not None else None


def spans(p, model, name: str) -> list[dict]:
    """Its rung per span of versions, oldest first: ``rung`` (None: not in the model), ``first``/``last`` (the
    versions' places in the record, 1 the oldest kept), ``version`` (the first's hash), ``at`` and ``seq`` (where the
    span begins; 0: before anything recorded). A version recorded before rungs were kept is ``not recorded``, but the
    newest when it is the model loaded now."""
    from .history import version
    evs, now = p.events.query(n=None, type="model.changed"), version(model)
    out: list[dict] = []
    for i, e in enumerate(evs, 1):
        d = e["data"]
        rs = d.get("rungs")
        r = rs.get(name) if isinstance(rs, dict) else rung_of(model, name) if i == len(evs) and d.get("version") == now \
            else "not recorded"
        if out and out[-1]["rung"] == r:
            out[-1]["last"] = i
        else:
            out.append({"rung": r, "first": i, "last": i, "version": d.get("version"), "at": e["time"], "seq": e["seq"]})
    r = rung_of(model, name)                                   # the model loaded now, not recorded yet: what is
    if not evs or (evs[-1]["data"].get("version") != now and out[-1]["rung"] != r):   # recorded so far is not its
        out.append({"rung": r, "first": None, "last": None, "version": now, "at": None, "seq": None if evs else 0})
    out[0]["seq"] = 0                                          # what came before the oldest version kept: its span's
    return out


def _of_kind(spec, kind: str, item) -> bool:
    k = spec.items.get(kind)
    return k is not None and isinstance(item, str) and fnmatchcase(item, k.id)


def may_did(p, spec, b, lo: float, hi: float, span) -> dict:
    """Each span's tally of its lease ends in the window against ``takes.to`` (``span(seq)``: the span's index)."""
    to = list(b.takes.to)
    tallies: dict[int, dict] = {}

    def row(i: int) -> dict:
        return tallies.setdefault(i, {"to": dict.fromkeys(to, 0), "other": {}, "unattributed": 0})
    taken = {e["data"].get("run"): e for e in p.events.query(n=None, type=TAKEN, since=lo - DAY, until=hi)}
    for e in p.events.query(n=None, type=f"{ENDED},{EXPIRED}", since=lo, until=hi):
        d, run = e["data"], e["data"].get("run")
        t = taken.get(run)
        if t is None and e["type"] == ENDED:                     # taken earlier: looked for by its item
            t = next((x for x in p.events.query(n=None, type=TAKEN, item=e.get("item"), until=hi)
                      if x["data"].get("run") == run), None)
        block = t["data"].get("block") if t is not None else d.get("block")
        if block is None:                                          # its take not in the record: shown, never dropped
            if _of_kind(spec, b.takes.kind, e.get("item")):
                row(span(e["seq"]))["unattributed"] += 1
            continue
        if block != b.name:
            continue
        r, state = row(span((t or e)["seq"])), d.get("state")
        if e["type"] == ENDED and d.get("how") == "ack" and state in r["to"]:
            r["to"][state] += 1
            continue
        why = "expired" if e["type"] == EXPIRED else "a dead letter" if state == "dead" else \
            f"given back to {state}" if d.get("how") == "nack" else f"left {state}"
        r["other"][why] = r["other"].get(why, 0) + 1
    return lambda i: (lambda r: {"to": list(r["to"].items()), "other": sorted(r["other"].items(), key=lambda kv: -kv[1]),
                                 "unattributed": r["unattributed"]})(row(i))


def said_done(p, spec, b, lo: float, hi: float, span) -> dict:
    """Each span's tally of what a controller said (once per run) and, per ``out`` port, the commands acted on."""
    said: dict[int, dict] = {}
    seen: set = set()
    for e in p.events.query(n=None, type="controller.decided", source=b.name, since=lo, until=hi):
        k = decision_kind(e["data"].get("decision"))
        if (e.get("causedby") or e["id"], k) in seen:
            continue
        seen.add((e.get("causedby") or e["id"], k))
        s = said.setdefault(span(e["seq"]), {})
        s[k] = s.get(k, 0) + 1
    acted: dict[int, dict] = {}
    rows = []
    for port, refs in b.outputs.items():
        for r in refs:
            key, note = f"{port}: {r}", None
            if r.kind == "block":
                others = sorted(c.name for c in spec.commanders_of(r.name) if c.name != b.name)
                note = f"shared with {', '.join(others)}" if others else None
                evs = [] if others else [e for e in p.events.query(n=None, type="block.commanded", item=r.name,
                                                                    since=lo, until=hi) if e["data"].get("from") == b.name]
            elif r.kind == "flow":
                evs = [e for e in p.events.query(n=None, type="valve.opened", source=b.name, since=lo, until=hi)
                       if e["data"].get("flow") == r.name]
            elif r.kind == "auxiliary":
                evs = p.events.query(n=None, type="auxiliary.set", item=r.name, source=b.name, since=lo, until=hi)
            else:
                evs, note = [], "not recorded"
            rows.append([key, note])
            for e in evs:
                a = acted.setdefault(span(e["seq"]), {})
                a[key] = a.get(key, 0) + 1
    return lambda i: {"said": sorted(said.get(i, {}).items(), key=lambda kv: -kv[1]),
                      "carried": [{"port": k, "n": None if note else acted.get(i, {}).get(k, 0), "note": note}
                                  for k, note in rows]}


def means(p, model, name: str, lo: float, hi: float) -> dict | None:
    """``means`` of ``/api/agents/NAME``: its specification (a narrow AI), its rung's spans with each one's counts."""
    spec = getattr(model, "spec", None)
    b = spec.blocks.get(name) if spec is not None else None
    if b is None:
        return None
    sp = spans(p, model, name)
    starts = [s["seq"] if s["seq"] is not None else float("inf") for s in sp]
    span = lambda seq: max(bisect_right(starts, seq) - 1, 0)    # noqa: E731
    counts = (may_did if b.takes is not None else said_done)(p, spec, b, lo, hi, span)
    for i, s in enumerate(sp):
        s["counts"] = counts(i)
    return {"spec": spec_rows(p, spec, b, lo, hi) if rung_of(model, name) == "narrow-ai" else None,
            "work": "items" if b.takes is not None else "controller", "spans": sp}
