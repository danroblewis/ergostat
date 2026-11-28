"""What a projection publishes from its own objects (SPEC §5a, *Emitted events*): ``emit:`` under a projection.

```yaml
projections:
  instance:
    fields:
      state: {values: [pending, running, stopping, stopped]}
      latency_ms: {type: number}
    emit:
      state: transitions          # instance.state-changed {from, to} on every change of state
      slow: latency_ms > 500      # instance.slow when it becomes true, instance.slow-cleared when it stops
```

- **Per object, per change.** After each event is folded into an object, each entry's value is worked out again over
  the object's fields (``key`` its key, ``state`` its state; never the event) and compared with what it was before
  the event: a ``transitions`` entry publishes ``<projection>.<field>-changed`` when the field's value changed; a
  condition publishes ``<projection>.<name>`` when it became true and ``<projection>.<name>-cleared`` when it stopped
  (null, or an expression that raises, is not true). Edge-triggered: nothing while it stays as it was.
- **Live only.** The item index (``itemindex.py``) writes what an event makes it publish into its outbox (``emits``) in
  the transaction that folds the event, for events past its mark (``emit_from``: the record's last ``seq`` when the
  index was made, so a rebuild, after the definition changed, publishes nothing for the past); the engine
  (``Emitter.look``, woken by the write) records them. Each one's id is made from (projection, version, object,
  entry, causing event), so a crash and a replay never records it twice.
- **Inferred.** Its envelope's ``source`` is ``projection:NAME``: what says it was inferred, not observed
  (invariant 11). No projection reads such events unless its ``query:`` names that source (``ItemKind.reads``)."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass

SOURCE = "projection:"           # an emitted event's source: projection:NAME
TRANSITIONS = "transitions"
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DRAIN = 1000                     # emitted events recorded per look (the rest at the next)


@dataclass
class Entry:
    """One ``emit:`` entry: a field's transitions (``field``), or a condition (``value``, reading ``reads``)."""

    name: str
    field: str | None = None
    value: object = None             # handlers.Value: the condition
    reads: tuple = ()                # the fields the condition reads

    def types(self, projection: str) -> list[str]:
        if self.field is not None:
            return [f"{projection}.{self.field}-changed"]
        return [f"{projection}.{self.name}", f"{projection}.{self.name}-cleared"]

    def spec(self):
        return (self.name, TRANSITIONS if self.field is not None else self.value.text)


def emitted(e: dict) -> bool:
    """Whether an event was published by a projection (its source ``projection:NAME``)."""
    s = e.get("source")
    return isinstance(s, str) and s.startswith(SOURCE)


def types_of(kind) -> list[str]:
    """Every type a projection emits."""
    return [t for x in getattr(kind, "emit", None) or [] for t in x.types(kind.name)]


def version(kind, functions_hash: str = "") -> str:
    """The definition's version, as an emitted event says it: of its reading of events and its emit: entries."""
    raw = repr((kind.name, kind.definition(), [x.spec() for x in kind.emit], functions_hash))
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


# ---- compiling

def compile_emit(c, m, what: str, declared: dict, states: list) -> list[Entry]:
    """``emit:``: each entry a field's ``transitions`` or a condition over the object's fields (checked as a computed
    field's ``from:``)."""
    from .handlers import BadExpr, compile_value
    raw = m.get("emit")
    if raw is None:
        return []
    at = m.at("emit") or m.where
    if not isinstance(raw, dict) or not raw:
        c.err(f"{what}.emit: a map of name: transitions (a field with values:) or name: a condition over the object's "
              f"fields (slow: latency_ms > 500)", at, "bad-emit")
        return []
    scope = (*declared, "key", *(("state",) if states and "state" not in declared else ()))
    out: list[Entry] = []
    for name, v in raw.items():
        w = (raw.at(name) if hasattr(raw, "at") else None) or at
        if not isinstance(name, str) or not NAME.match(name):
            c.err(f"{what}.emit: {name!r} is not a name (lowercase letters, digits, _ and -): it names the event "
                  f"type it emits", w, "bad-emit")
            continue
        if v == TRANSITIONS:
            d = declared.get(name)
            if d is None:
                c.err(f"{what}.emit.{name}: transitions of {name}, which is not one of its fields "
                      f"({', '.join(declared) or 'none'})", w, "bad-emit")
            elif d.type.base != "values":
                c.err(f"{what}.emit.{name}: transitions are of a field with values: (its lifecycle); {name} has none",
                      w, "bad-emit")
            else:
                out.append(Entry(name, field=name))
            continue
        if not isinstance(v, str) or not v.strip():
            c.err(f"{what}.emit.{name}: transitions, or a condition over the object's fields (latency_ms > 500)", w,
                  "bad-emit")
            continue
        try:
            val = compile_value(v, {}, scope)
        except BadExpr as e:
            msg = str(e)
            if " is not a name" in msg:
                word = msg.split(" is not a name")[0]
                msg = (f"{word} is the event's: a condition reads the object's fields ({', '.join(declared) or 'none'}) "
                       f"and its key, after each event is folded" if word in ("data", "time", "type", "source", "current")
                       else f"{word} is not one of its fields ({', '.join(declared) or 'none'}) nor its key")
            c.err(f"{what}.emit.{name}: {msg}", w, "bad-emit")
            continue
        if val.call is not None or val.tree is None:
            c.err(f"{what}.emit.{name}: a condition over the object's fields "
                  + (f"({val.call}() folds a field)" if val.call else "(a constant never changes)"), w, "bad-emit")
            continue
        reads = tuple(sorted({n.id for n in ast.walk(val.tree) if isinstance(n, ast.Name) and n.id in scope
                              and n.id != "key"}))
        out.append(Entry(name, value=val, reads=reads))
    return out


def check(c, kind, at) -> None:
    """Two entries publishing one type, or a type the projection's own query would read (a loop), are errors."""
    seen: dict[str, str] = {}
    for x in kind.emit:
        for t in x.types(kind.name):
            if t in seen:
                c.err(f"projection {kind.name}.emit.{x.name}: {t} is published by {seen[t]} too; rename one", at,
                      "emit-collision")
            seen.setdefault(t, x.name)
    for t in seen:
        probe = {"id": "", "time": 0.0, "type": t, "item": f"{kind.name}/x", "source": SOURCE + kind.name, "data": {}}
        try:
            loop = kind.reads(probe)
        except Exception:                                # noqa: BLE001 - a query that cannot read it does not
            loop = False
        if loop:
            c.err(f"projection {kind.name}.emit: its query reads {t}, which it publishes itself: a loop (leave "
                  f"source {SOURCE}{kind.name} out of its query)", at, "emit-loop")
            return


# ---- what an object publishes

def values(kind, it) -> dict:
    """Each entry's value for an object as it stands: a field's value, or whether a condition holds."""
    from .handlers import evaluate
    if it is None:
        return {}
    fields = it.fields if isinstance(it.fields, dict) else {}
    out = {}
    scope = None
    for x in kind.emit:
        if x.field is not None:
            out[x.name] = it.state if x.field == "state" and kind.states else fields.get(x.field)
        else:
            if scope is None:
                scope = {**fields, "key": it.id, **({"state": it.state} if kind.states else {})}
            got = evaluate(x.value, scope)
            out[x.name] = bool(got)
    return out


def changes(kind, before: dict, it, e: dict, version_: str) -> list[dict]:
    """The events an object publishes for event ``e`` having been folded into it (``before``: ``values`` before it),
    as ``add_many`` takes them."""
    from .handlers import own_time
    from .items import display_name
    now = values(kind, it)
    out = []
    head = None
    for x in kind.emit:
        a, b = before.get(x.name), now.get(x.name)
        if x.field is not None:
            if a == b and type(a) is type(b):
                continue
            t, extra = f"{kind.name}.{x.field}-changed", {"field": x.field, "from": a, "to": b}
        else:
            if bool(a) == bool(b):
                continue
            fields = it.fields if isinstance(it.fields, dict) else {}
            t = f"{kind.name}.{x.name}" + ("" if b else "-cleared")
            extra = {"fields": {f: (it.state if f == "state" and kind.states else fields.get(f)) for f in x.reads}}
        if head is None:
            fields = it.fields if isinstance(it.fields, dict) else {}
            at = own_time(kind, e)
            at = at if isinstance(at, (int, float)) else e.get("time")
            head = {"projection": kind.name, "id": it.id,
                    "key": {f: fields.get(f) for f in kind.key} if kind.key else {},
                    "name": display_name(kind, it), "cause": {"id": e.get("id"), "time": at}, "version": version_}
        eid = hashlib.sha1(json.dumps([kind.name, version_, it.id, x.name, e.get("id")]).encode()).hexdigest()[:32]
        out.append({"id": eid, "type": t, "item": it.id, "source": SOURCE + kind.name, "causedby": e.get("id"),
                    "at": head["cause"]["time"], "data": {**head, "entry": x.name, **extra}})
    return out


def folding(kind, version_: str, out: list, live):
    """A fold (``items.fold``'s arguments, one event at a time) that also gathers what each live event (``live(e)``)
    makes the object publish into ``out``."""
    from .items import SNAPSHOT, fold

    def f(id, es, k, it=None, transcript=True):
        e = es[0] if len(es) == 1 else None
        on = e is not None and e["type"] != SNAPSHOT and not str(e["type"]).startswith("ergostat.") and live(e)
        before = values(kind, it) if on else None
        it = fold(id, es, k, it=it, transcript=transcript)
        if on:
            out.extend(changes(kind, before, it, e, version_))
        return it
    return f


def counted(kind, by_key: dict) -> list[dict]:
    """What each entry would have published over these objects' events (no publishing): the review's, per entry, its
    types' counts and the objects that published any."""
    got: list[dict] = []
    ver = getattr(kind, "emit_version", "") or ""
    tally: dict[str, dict] = {x.name: {} for x in kind.emit}
    objs: dict[str, set] = {x.name: set() for x in kind.emit}
    for key, es in by_key.items():
        it, out = None, []
        f = folding(kind, ver, out, lambda e: True)
        for e in sorted(es, key=lambda x: (x["time"], x.get("seq") or 0)):
            it = f(key, [e], kind, it=it)
        for ev in out:
            n = ev["data"]["entry"]
            tally[n][ev["type"]] = tally[n].get(ev["type"], 0) + 1
            objs[n].add(key)
    for x in kind.emit:
        t = x.types(kind.name)
        got.append({"entry": x.name, "kind": TRANSITIONS if x.field is not None else "condition",
                    **({"field": x.field} if x.field is not None else {"when": x.value.text}),
                    "types": {ty: tally[x.name].get(ty, 0) for ty in t}, "count": sum(tally[x.name].values()),
                    "objects": len(objs[x.name])})
    return got


class Emitter:
    """The engine's: what the item index's outbox holds, recorded, each time its loop wakes on a write."""

    def __init__(self, eng):
        self.e = eng
        self.top = -1

    def look(self) -> int:
        spec = self.e.spec
        names = {k.name for k in spec.items.values() if getattr(k, "emit", None)
                 and self.e.own(f"projection.{k.name}", spec)}
        if not names:
            return 0
        top = self.e.p.events.last_seq()
        if top == self.top:
            return 0
        from .itemindex import index_for
        ix = index_for(self.e.p.events, spec, False)
        if ix is None:
            return 0
        n = drain(ix, self.e.p.events, names)
        self.top = -1 if n else top
        return n


def drain(ix, events, names=None) -> int:
    """The index's outbox recorded (``names``: only these projections'), and taken out of it: each event once, by
    its id, however often this runs."""
    with ix.lock:
        only = sorted(names) if names is not None else []
        where = f"where projection in ({','.join('?' * len(only))}) " if names is not None else ""
        mine = ix.guard(lambda: ix.db.execute(f"select n, projection, ev from emits {where}order by n limit ?",
                                              (*only, DRAIN)).fetchall())
        if not mine:
            return 0
        events.add_many([json.loads(r[2]) for r in mine])
        ix.db.executemany("delete from emits where n = ?", [(r[0],) for r in mine])
    return len(mine)
