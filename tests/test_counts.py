"""Counts kept as the record folds (spec/counts.py): what every ``items:`` sensor reads must equal a fresh count of
the item index (``items.measure``), for every example's kinds, every state, with and without ``where:``, every
measure (count, oldest, age) and flows entering and leaving every state over several windows: as events arrive,
when another process folds them, after roll-ups, when built again (a restart), and across a model swap."""

from __future__ import annotations

import random

import pytest

from ergostat import model as mdl
from ergostat.rollup import compact
from ergostat.spec import itemindex
from ergostat.spec import items as its
from ergostat.spec.counts import Counts, transcript_of
from ergostat.spec.ir import Ref, Sensor
from ergostat.store import Project
from tests.test_rollup import BACKENDS, EXAMPLES, T0, _project, _record

KINDED = [e for e in EXAMPLES if mdl.load(e).spec and mdl.load(e).spec.items]


def _sensors(spec) -> list[Sensor]:
    """Every way of counting every kind of the model: its own sensors, and for each kind and state a count, the
    oldest, the age, the same with where:, and flows entering and leaving it over three windows."""
    out = [s for s in spec.sensors() if s.items]
    i = 0
    for k in spec.items.values():
        for states in [None, *([x] for x in k.states), k.states[:2] or None]:
            for where in ({}, {"tier": "a"}, {"tier": ["a", "b"]}):
                for m in ("count", "oldest", "age"):
                    i += 1
                    out.append(Sensor(f"s{i}", Ref("stock", f"x{i}"),
                                      items={"kind": k.name, "where": where, "measure": m, **({"state": states} if states else {})}))
        for st in k.states:
            for key in ("entering", "leaving"):
                for over in (600.0, 3600.0, 86400.0 * 400):
                    for where in ({}, {"tier": "b"}):
                        i += 1
                        out.append(Sensor(f"f{i}", Ref("flow", f"y{i}"), items={"kind": k.name, key: st, "over": over, "where": where}))
    return out


def _tiers(spec, r: random.Random) -> list[dict]:
    """Events that set a field the sensors' where: reads, without moving the item, on each kind's items."""
    out = []
    for k in spec.items.values():
        for j in range(4):
            id = k.id.replace("*", f"r{j}", 1).replace("*", "x")
            for n in range(6):
                out.append({"id": f"{id}-tier{n}", "at": T0 + r.random() * 4 * 3600, "type": "x.tier", "item": id,
                            "source": "test", "data": {"tier": r.choice("abc")}})
    return out


def _fresh(p, sensors, now) -> dict:
    return {s.name: its.measure(p.events, p.model.spec, s, now=now)[0] for s in sensors}


def _kept(p, counts: dict, sensors, now) -> dict:
    spec = p.model.spec
    out = {}
    for tr in (False, True):
        mine = [s for s in sensors if transcript_of(spec, s) == tr]
        assert counts[tr].follow(p.events, spec, mine, now=now)
        out.update({s.name: counts[tr].value(spec, s, now)[0] for s in mine})
    return out


def _same(a: dict, b: dict) -> None:
    bad = {k: (a[k], b[k]) for k in a if abs((a[k] or 0) - (b[k] or 0)) > 1e-9}
    assert not bad, list(bad.items())[:8]


def _end(p) -> float:
    return max(e["time"] for e in p.events.query(n=None)) + 1


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("example", KINDED, ids=lambda p: p.name)
def test_kept_counts_are_a_fresh_count_as_events_arrive_after_rollups_and_a_restart(tmp_path, example, backend):
    p = _project(tmp_path, example, backend)
    spec = p.model.spec
    r = random.Random(example.name + "counts")
    evs = _record(spec, r, n=30) + _tiers(spec, r)
    r.shuffle(evs)
    sensors = _sensors(spec)
    counts = {False: Counts(False), True: Counts(True)}
    step = max(1, len(evs) // 5)
    for i in range(0, len(evs), step):                         # in five parts: each followed, not read whole
        p.events.add_many(evs[i:i + step])
        now = _end(p)
        _same(_kept(p, counts, sensors, now), _fresh(p, sensors, now))
    assert counts[False].builds == 1, "followed, not built again"
    end = _end(p)
    for frac in (0.3, 1.01):                                   # rolled up: built again, and still a fresh count
        compact(p, now=T0 + (end - T0) * frac + p.storage.rollup_after)
        _same(_kept(p, counts, sensors, end), _fresh(p, sensors, end))
    for x in itemindex._OPEN.values():                         # a process that starts: everything read again
        x.close()
    itemindex._OPEN.clear()
    again = {False: Counts(False), True: Counts(True)}
    _same(_kept(p, again, sensors, end), _fresh(p, sensors, end))
    _same(_kept(p, again, sensors, end), _kept(p, counts, sensors, end))


def _ticket(tmp_path, states="[new, doing, done]"):
    (tmp_path / "ergostat.yaml").write_text(f"items:\n  ticket:\n    id: ticket/*\n    states: {states}\n"
                                            "    on: {ticket.started: doing, ticket.done: done, ticket.new: new}\n")
    return Project(mdl.load(tmp_path))


def _moves(p, r: random.Random, n: int, t0: float) -> float:
    t = t0
    for i in range(n):
        t += r.random() * 30
        p.events.add(r.choice(["ticket.started", "ticket.done", "ticket.new", "ticket.noted"]), item=f"ticket/{r.randrange(40)}",
                     source="test", at=t, data={"tier": r.choice("ab")} if r.random() < 0.5 else {})
    return t


def test_moves_another_process_folded_are_counted(tmp_path):
    """The index is shared: what another process folded (its own catch_up) shows in the moves and items it wrote."""
    p = _ticket(tmp_path)
    spec = p.model.spec
    sensors = _sensors(spec)
    counts = {False: Counts(False), True: Counts(True)}
    r = random.Random(3)
    t = _moves(p, r, 50, T0)
    _same(_kept(p, counts, sensors, t + 1), _fresh(p, sensors, t + 1))
    path = itemindex.index_for(p.events, spec, False).path
    other = itemindex.Index(path, spec, False)                 # another process's index on the same file
    for _ in range(4):
        t = _moves(p, r, 40, t)
        other.catch_up(p.events)                               # it folds first: ours only reads its rows
        _same(_kept(p, counts, sensors, t + 1), _fresh(p, sensors, t + 1))
    other.close()
    assert counts[False].builds == 1


def test_a_model_swap_counts_the_new_kinds_and_sensors(tmp_path):
    p = _ticket(tmp_path)
    r = random.Random(5)
    t = _moves(p, r, 120, T0)
    counts = {False: Counts(False), True: Counts(True)}
    sensors = _sensors(p.model.spec)
    _same(_kept(p, counts, sensors, t + 1), _fresh(p, sensors, t + 1))
    _ticket(tmp_path, "[new, doing, review, done]")
    p.model = mdl.load(tmp_path)                               # another set of states: another index
    sensors = _sensors(p.model.spec)
    _same(_kept(p, counts, sensors, t + 1), _fresh(p, sensors, t + 1))
    t = _moves(p, r, 60, t)
    _same(_kept(p, counts, sensors, t + 1), _fresh(p, sensors, t + 1))
    fewer = sensors[: len(sensors) // 3]                       # fewer sensors: another shape, built again
    _same(_kept(p, counts, fewer, t + 1), _fresh(p, fewer, t + 1))


def test_a_window_forgets_moves_past_it_and_counts_what_is_in_it(tmp_path):
    p = _ticket(tmp_path)
    r = random.Random(9)
    t = _moves(p, r, 200, T0)
    sensors = [s for s in _sensors(p.model.spec) if s.of.kind == "flow"]
    counts = {False: Counts(False), True: Counts(True)}
    for now in (t + 1, t + 300, t + 1200, t + 4000):           # the clock moves on: moves fall out of the windows
        _same(_kept(p, counts, sensors, now), _fresh(p, sensors, now))
    w = next(iter(counts[False].windows.values()))
    assert all(m[0] > t + 4000 - w.over - 61 for m in w.moves), "nothing kept past the window"
