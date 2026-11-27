"""Areas one stream at a time owns (SPEC §9.5, *Areas*; ``takes: {areas: {touches, holding, map}}``,
dev/records/code-area-ownership.md): off unless declared; an item touching an area another stream holds waits; the
owner says what a stream is (a lane, a field's value, a block); an unreadable field is the worst case."""

from __future__ import annotations

import textwrap
import time

from ergostat import model as mdl
from ergostat.leases import areas
from ergostat.spec import read
from ergostat.spec.engine import Engine
from ergostat.store import Project

PLAIN = """
name: t
projections:
  ticket:
    match:
      key: ticket/*
    states: [todo, doing, fix, done]
    events:
      ticket.opened:
        state: set('todo')
      ticket.started:
        state: set('doing')
      ticket.back:
        state: set('fix')
      ticket.done:
        state: set('done')
    otherwise: rest
blocks:
  dev:
    type: program
    run: "true"
    pool: 4
    takes: {projection: ticket, at: [fix, todo], to: [done]}
  ops:
    type: program
    run: "true"
    pool: 4
    takes: {projection: ticket, at: [fix, todo], to: [done]AREAS}
"""
MAP = ", areas: {touches: files, holding: [doing, fix], map: {queue: {paths: [src/queue.py, src/q/*]}, " \
      "spec: {paths: docs/spec.md, owner: {field: milestone}}, ui: {paths: 'web/*', owner: {block: ops}}}}"


def model(tmp_path, areas_on: bool = True) -> Project:
    text = PLAIN.replace("AREAS", MAP if areas_on else "")
    text = text.replace("to: [done]}\n  ops", f"to: [done]{MAP if areas_on else ''}}}\n  ops")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def dispatcher(p, monkeypatch):
    """The engine's dispatcher, a take recorded (the item moved to doing) instead of run."""
    said: list[str] = []
    e = Engine(p, say=said.append)
    d, taken = e.dispatch, []

    def take(b, it, **_):
        taken.append((b.name, it.id))
        p.events.add("ticket.started", item=it.id)
        return True
    monkeypatch.setattr(d, "take", take)
    return d, taken, said


def tick(d, p, block: str = "dev") -> None:
    d.stale = True
    d.tick_block(p.model.spec.blocks[block], time.time())


def opened(p, items: dict) -> None:
    at = time.time() - 100
    for n, (i, fields) in enumerate(items.items()):
        p.events.add("ticket.opened", item=f"ticket/{i}", data=fields, at=at + n)


def ids(taken) -> list[str]:
    return [i.split("/")[1] for _, i in taken]


def test_off_by_default_existing_models_unchanged(tmp_path, monkeypatch):
    p = model(tmp_path, areas_on=False)
    assert p.model.spec.blocks["dev"].takes.areas is None
    d, taken, said = dispatcher(p, monkeypatch)
    opened(p, {"a": {"files": ["src/queue.py"]}, "b": {"files": ["src/queue.py"]}})
    tick(d, p)
    assert ids(taken) == ["a", "b"]
    assert not [s for s in said if "waits" in s]


def test_a_lane_takes_one_item_at_a_time(tmp_path, monkeypatch):
    """Two items touching the queue area: the first taken, the second waits (said) while the first holds it (doing,
    a holding state no block takes from), and is taken once the first is done; an item touching nothing held goes."""
    p = model(tmp_path)
    d, taken, said = dispatcher(p, monkeypatch)
    opened(p, {"a": {"files": ["src/q/x.py", "README"]}, "b": {"files": "src/queue.py"}, "c": {"files": ["lib.py"]},
               "e": {"files": []}})
    tick(d, p)
    assert ids(taken) == ["a", "c", "e"]
    assert any("ticket/b waits: ticket/a holds queue" in s for s in said)
    tick(d, p)
    assert ids(taken) == ["a", "c", "e"]                      # a still holds it (doing)
    p.events.add("ticket.done", item="ticket/a")
    tick(d, p)
    assert ids(taken) == ["a", "c", "e", "b"]


def test_an_item_already_holding_never_waits(tmp_path, monkeypatch):
    """Two items sent back (fix, a holding state) touching one area both go: each entered before the rule could keep
    it out, so neither waits on the other; a new item touching it waits on both."""
    p = model(tmp_path)
    d, taken, _ = dispatcher(p, monkeypatch)
    opened(p, {"a": {"files": ["src/queue.py"]}, "b": {"files": ["src/queue.py"]}, "c": {"files": ["src/queue.py"]}})
    for i in ("a", "b"):
        p.events.add("ticket.back", item=f"ticket/{i}")
    tick(d, p)
    assert ids(taken) == ["a", "b"]


def test_a_field_owner_batches_its_stream_and_sequences_the_next(tmp_path, monkeypatch):
    p = model(tmp_path)
    d, taken, said = dispatcher(p, monkeypatch)
    opened(p, {"a": {"files": ["docs/spec.md"], "milestone": "m1"}, "b": {"files": ["docs/spec.md"], "milestone": "m2"},
               "c": {"files": ["docs/spec.md"], "milestone": "m1"}, "n": {"files": ["docs/spec.md"]}})
    tick(d, p)
    assert ids(taken) == ["a", "c"]                           # m1 together; m2 and the one with no milestone wait
    assert any("ticket/b waits: ticket/a holds spec" in s for s in said)
    for i in ("a", "c"):
        p.events.add("ticket.done", item=f"ticket/{i}")
    tick(d, p)
    assert ids(taken) == ["a", "c", "b"]                      # m2 now, and n (a stream of its own) after it


def test_a_block_owner_alone_takes_its_area(tmp_path, monkeypatch):
    p = model(tmp_path)
    d, taken, said = dispatcher(p, monkeypatch)
    opened(p, {"a": {"files": ["web/page.js"]}, "b": {"files": ["web/x.css"]}})
    tick(d, p)
    assert taken == []
    assert any("ticket/a is left to block ops" in s for s in said)
    tick(d, p, "ops")
    assert ids(taken) == ["a", "b"]                           # the owner's: no lane among them


def test_an_unreadable_field_is_the_worst_case(tmp_path, monkeypatch):
    """A field that is not a text or a list of texts (or too long), or was never said (or null), touches every area:
    only the block owning one takes it, it waits while any is held, and once held it holds them all. Only an empty
    text or list says it touches nothing."""
    p = model(tmp_path)
    d, taken, said = dispatcher(p, monkeypatch)
    opened(p, {"a": {"files": ["src/queue.py"]}, "u": {"files": {"x": 1}}, "v": {"files": ["x"] * (areas.TOUCHES + 1)},
               "s": {}, "n": {"files": None}})
    tick(d, p)
    assert ids(taken) == ["a"]
    assert all(any(f"ticket/{i}'s files cannot be read" in s for s in said) for i in ("u", "s", "n"))
    assert any("ticket/v is left to block ops" in s for s in said)
    tick(d, p, "ops")
    assert ids(taken) == ["a"]                                # a holds queue: u and v wait at ops too
    p.events.add("ticket.done", item="ticket/a")
    tick(d, p, "ops")
    assert ids(taken) == ["a", "u"]                           # u now holds every area: v waits on it
    opened(p, {"w": {"files": ["lib.py"]}, "z": {"files": ["docs/spec.md"], "milestone": "m1"}})
    tick(d, p)
    assert ids(taken) == ["a", "u", "w"]                      # touching no area: not held by anyone


def test_block_now_follows_the_rule(tmp_path, monkeypatch):
    p = model(tmp_path)
    d, taken, _ = dispatcher(p, monkeypatch)
    opened(p, {"a": {"files": ["src/queue.py"]}, "b": {"files": ["src/queue.py"]}})
    p.events.add("ticket.started", item="ticket/a")
    assert d.once(p.model.spec.blocks["dev"], "by hand") == []                 # b waits: a holds queue
    assert taken == []


def test_lanes_take_only_what_the_areas_let_through(tmp_path, monkeypatch):
    """A block declaring lanes and areas: two items sharing no lane entry would start apart, but they touch one area,
    so the second waits for the first (SPEC §9.5: the areas' rule before the lanes')."""
    lanes = ", lanes: {apart: files, most: 4, within: {cpu: 4, memory: 4g}, each: {cpu: 1, memory: 1g}}"
    p = model(tmp_path)
    text = (tmp_path / "ergostat.yaml").read_text().replace("to: [done], areas:", f"to: [done]{lanes}, areas:", 1)
    (tmp_path / "ergostat.yaml").write_text(text)
    p = Project(mdl.load(tmp_path))
    assert p.model.spec.blocks["dev"].takes.lanes is not None
    d, taken, said = dispatcher(p, monkeypatch)
    opened(p, {"a": {"files": ["src/queue.py"]}, "b": {"files": ["src/q/x.py"]}, "c": {"files": ["lib.py"]}})
    tick(d, p)
    assert ids(taken) == ["a", "c"]
    assert any("ticket/b waits: ticket/a holds queue" in s for s in said)


def test_areas_checked(tmp_path):
    for bad in ("3", "{touches: files}", "{touches: files, map: {}}", "{touches: [x], map: {q: {paths: a}}}",
                "{touches: files, map: {q: {paths: []}}}", "{touches: files, map: {q: {paths: a, owner: crew}}}",
                "{touches: files, map: {q: {paths: a, owner: {field: m, block: dev}}}}",
                "{touches: files, holding: [nowhere], map: {q: {paths: a}}}",
                "{touches: files, map: {q: {paths: a, owner: {block: nobody}}}}",
                "{touches: files, map: {q: {paths: a, later: 1}}}"):
        text = PLAIN.replace("AREAS", "").replace("to: [done]}\n  ops", f"to: [done], areas: {bad}}}\n  ops")
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
        spec, problems = read(tmp_path / "ergostat.yaml")
        assert any("takes.areas" in x.message for x in problems if x.level == "error"), bad
    p = model(tmp_path)
    a = p.model.spec.blocks["dev"].takes.areas
    assert [(x.name, x.owner, x.by) for x in a.map] == [("queue", "lane", ""), ("spec", "field", "milestone"),
                                                       ("ui", "block", "ops")]
    assert a.holding == ("doing", "fix")
