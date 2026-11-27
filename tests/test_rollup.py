"""Rolling items up (rollup.py): folding an item's snapshot plus what came after gives the same item
as folding the events it replaced, for every example's kinds, with and without a transcript's lines,
rolled up once and again; the originals are in the archive; the kept fold matches a fresh one."""

from __future__ import annotations

import random
import textwrap
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.rollup import Archive, archived, compact, upkeep
from ergostat.spec import items as its
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted(p for p in (ROOT / "examples").iterdir() if (p / "ergostat.yaml").exists())
BACKENDS = ("sqlite", "segments")
T0 = 1_700_000_000.0


def _value(r: random.Random, depth=0):
    pick = r.randrange(7 if depth < 2 else 5)
    if pick == 5:
        return [_value(r, depth + 1) for _ in range(r.randrange(3))]
    if pick == 6:
        return {f"k{i}": _value(r, depth + 1) for i in range(r.randrange(3))}
    return [None, r.randint(-5, 5), r.random(), "x" * r.randrange(4), True][pick]


def _for_rule(r: random.Random, rule: str):
    """A value its rule folds, mostly; sometimes one it refuses (a sum of text)."""
    if r.random() < 0.05:
        return "not a number" if rule in ("sum", "min", "max") else 7
    return {"sum": r.randint(0, 9), "min": r.randint(0, 99), "max": r.randint(0, 99), "append": _value(r),
            "union": r.choice(["a", "b", "c", 1, 2]), "merge": {f"k{r.randrange(3)}": _value(r)}, "first": _value(r),
            "replace": _value(r)}.get(rule, _value(r))


def _record(spec, r: random.Random, items_per_kind=4, n=60) -> list[dict]:
    """Random events about each kind's items: its moving types and others, plain data folded by its
    rules, patches, whole-document sets, and transcript lines; in an order that interleaves items."""
    from ergostat.transcripts import FIELDS
    out = []
    t = T0
    for k in spec.items.values():
        names = [*k.show, *k.formats, "note", "why", "result"]
        for j in range(items_per_kind):
            id = k.id.replace("*", f"r{j}", 1).replace("*", "x")
            for i in range(n):
                t += r.random() * 60
                form = r.random()
                e = {"id": f"{id}-{i}", "at": t, "type": r.choice([*k.on, "x.y", "x.z"]), "item": id, "source": "test"}
                if form < 0.12:
                    e["type"] = r.choice(["claude.message", "claude.tool-use"])
                    e["data"] = {"messages": {"text": "hi"}, "tokens_out": r.randint(1, 9)} if r.random() < 0.7 else {
                        r.choice(FIELDS): _value(r)}
                elif form < 0.2:
                    e["patch"] = [{"op": "add", "path": f"/{r.choice(names)}", "value": _value(r)}]
                elif form < 0.24:
                    e["set"] = {n_: _value(r) for n_ in r.sample(names, 2)}
                else:
                    keys = r.sample([*names, *k.fold], r.randrange(1, 4))
                    e["data"] = {x: _for_rule(r, k.fold.get(x, "replace")) for x in keys}
                out.append(e)
    r.shuffle(out)                                  # recorded in an order unlike their times, as real writers do
    return out


def _fresh(p, transcript: bool, until=None) -> dict:
    """Every item folded from the record as it is, not from the kept fold."""
    spec = p.model.spec
    by: dict = {}
    for e in p.events.of_items(None, until=until, skip=() if transcript else (its.TRANSCRIPT_TYPES,)):
        by.setdefault(e["item"], []).append(e)
    return {id: _seen(its.fold(id, evs, its.kind_of(spec, id), transcript=transcript)) for id, evs in by.items()}


def _seen(it) -> dict:
    return {**it.as_dict(moves=True), "refused": [(x["event"], x["why"]) for x in it.refused]}


def _project(tmp_path: Path, example: Path, backend: str) -> Project:
    text = (example / "ergostat.yaml").read_text()
    d = tmp_path / example.name
    if not d.exists():
        import shutil
        shutil.copytree(example, d, ignore=shutil.ignore_patterns("run", "outbox", "__pycache__"))
    (d / "ergostat.yaml").write_text(text + f"\nstorage:\n  events: {backend}\n")
    return Project(mdl.load(d))


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("example", [e for e in EXAMPLES if mdl.load(e).spec and mdl.load(e).spec.items], ids=lambda p: p.name)
def test_folding_the_snapshot_and_what_came_after_is_folding_the_originals(tmp_path, example, backend):
    p = _project(tmp_path, example, backend)
    r = random.Random(example.name)
    p.events.add_many(_record(p.model.spec, r))
    end = max(e["time"] for e in p.events.query(n=None))
    want = {tr: _fresh(p, tr) for tr in (False, True)}
    total = p.events.count()
    for frac in (0.3, 0.7, 1.01):                        # rolled up three times, each over the one before
        horizon = T0 + (end - T0) * frac
        got = compact(p, now=horizon + p.storage.rollup_after)
        assert got["items"], f"nothing rolled up at {frac}"
        for tr in (False, True):
            assert _fresh(p, tr) == want[tr], (frac, tr)
            assert {i.id: _seen(i) for i in its.project(p.events, p.model.spec, transcript=tr)} == want[tr]
    assert p.events.count() < total / 3
    for id in want[True]:                                # nothing lost: the archive and the record hold every event
        arc = archived(p, id, n=10_000)
        kept = [e for e in p.events.query(n=None, item=id) if e["type"] != its.SNAPSHOT]
        assert arc["total"] == len(kept) + arc["archived"] == want[True][id]["events"]
        assert len({e["id"] for e in arc["events"]}) == arc["total"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_snapshot_is_a_set_with_its_history_summarised_and_the_full_history_archived(tmp_path, backend):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(f"""
        projections:
          ticket:
            id: ticket/*
            states: [open, done]
            on: {{ticket.done: done}}
            fold: {{spent: sum, notes: append}}
        storage:
          events: {backend}
          rollup: {{after: 1h, projections: {{ticket: 2h}}}}
        """))
    p = Project(mdl.load(tmp_path))
    for i in range(10):
        p.events.add("ticket.worked", item="ticket/1", data={"spent": 1, "notes": f"n{i}", "title": f"t{i}"}, at=T0 + i * 600)
    p.events.add("ticket.done", item="ticket/1", data={"title": "final"}, at=T0 + 20 * 3600)
    before = its.detail(p.events, p.model.spec, "ticket/1")
    got = compact(p, now=T0 + 10 * 3600)
    assert got == {**got, "items": 1, "events": 10}
    snap = p.events.query(n=None, item="ticket/1")[0]
    assert snap["type"] == its.SNAPSHOT and snap["set"] == {"spent": 10, "notes": [f"n{i}" for i in range(10)], "title": "t9"}
    roll = snap["data"]["rollup"]
    assert roll["n"] == 10 and roll["state"] == "open" and roll["archived"]["events"] == 10
    assert roll["fields"]["spent"]["changes"] == 10 and roll["fields"]["title"]["last"]["time"] == T0 + 9 * 600
    after = its.detail(p.events, p.model.spec, "ticket/1")
    for k in ("fields", "state", "moves", "events", "first", "last", "entered", "latest"):
        assert after[k] == before[k], k
    assert after["rollup"]["archived"]["events"] == 10 and after["changes"]["spent"] == 1   # summarised in one entry
    assert after["history"]["spent"][0]["count"] == 10
    full = archived(p, "ticket/1")
    assert full["total"] == 11 and full["archived"] == 10 and [e["data"].get("notes") for e in full["events"][:3]] == ["n0", "n1", "n2"]
    assert list(Archive(p.dir).dir.glob("ticket/*.jsonl.gz"))


def test_the_kept_fold_follows_new_events_and_a_past_moment(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("projections:\n  t:\n    id: t/*\n    states: [a, b]\n    on: {t.b: b}\n")
    p = Project(mdl.load(tmp_path))
    spec = p.model.spec
    for i in range(30):
        p.events.add("t.x", item=f"t/{i % 5}", data={"v": i}, at=T0 + i)
    assert len(its.project(p.events, spec)) == 5
    p.events.add("t.b", item="t/1", at=T0 + 100)
    now = {i.id: i for i in its.project(p.events, spec)}
    assert now["t/1"].state == "b" and now["t/1"].fields == {"v": 26}
    past = {i.id: i for i in its.project(p.events, spec, until=T0 + 20)}
    assert past["t/1"].state == "a" and past["t/1"].fields == {"v": 16}
    its.listing(p.events, spec)                          # a listing changes copies, never the kept fold
    assert {i.id: i for i in its.project(p.events, spec)}["t/1"].n == 7


@pytest.mark.parametrize("backend", BACKENDS)
def test_keep_forgets_an_item_whole_and_rolls_up_a_live_one(tmp_path, backend):
    (tmp_path / "ergostat.yaml").write_text(f"keep: 1d\nprojections:\n  t:\n    id: t/*\nstorage:\n  events: {backend}\n"
                                            "  rollup: never\n")
    p = Project(mdl.load(tmp_path))
    now = T0 + 10 * 86400
    p.events.add("t.x", item="t/old", data={"a": 1}, at=T0)
    p.events.add("t.x", item="t/old", data={"a": 2}, at=T0 + 1)
    p.events.add("t.x", item="t/live", data={"a": 1}, at=T0)
    p.events.add("t.x", item="t/live", data={"b": 1}, at=T0 + 2)
    p.events.add("t.x", item="t/live", data={"c": 1}, at=now - 10)
    p.events.add("agent.ran", item="someone", at=T0)
    p.events.add("model.changed", at=T0)
    upkeep(p, now=now)
    left = {i.id: i for i in its.project(p.events, p.model.spec)}
    assert set(left) == {"t/live"} and left["t/live"].fields == {"a": 1, "b": 1, "c": 1} and left["t/live"].n == 3
    assert [e["type"] for e in p.events.query(n=None)] == [its.SNAPSHOT, "t.x", "model.changed"]


def test_a_transcript_read_again_records_none_of_its_rolled_up_lines(tmp_path):
    import json

    from ergostat.transcripts import Ingester as Transcripts
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        projections:
          session:
            id: session/*
            formats: {transcript: claude-session}
            fold: {messages: append}
        """))
    lines = [{"type": "user", "uuid": f"u{i}", "timestamp": "2023-11-14T22:13:20Z", "message": {"role": "user", "content": f"m{i}"}}
             for i in range(6)]
    (tmp_path / "s.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    p = Project(mdl.load(tmp_path))
    p.events.add("session.started", item="session/1", data={"transcript": "file:s.jsonl"}, at=T0)
    assert Transcripts(p, p.model.spec).once() == 6
    compact(p, now=time.time() + 30 * 86400)
    assert p.events.count() == 1
    more = {**lines[0], "uuid": "u6", "message": {"role": "user", "content": "m6"}}
    with open(tmp_path / "s.jsonl", "a") as f:                                      # it grew: read again, from the start
        f.write(json.dumps(more) + "\n")
    assert Transcripts(p, p.model.spec).once() == 1 and p.events.count() == 2
