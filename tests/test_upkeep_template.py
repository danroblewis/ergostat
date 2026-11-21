"""``use: upkeep`` (SPEC §2a, *Upkeep*): ergostat's item-index files a stock held under a goal, tidied by a program on
the rule rung (``library/run/upkeep.py``) instead of by the engine; the delete interlock stays in ``itemindex``."""

from __future__ import annotations

import json
import os
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat import upkeep_measures as um
from ergostat.library.run import common
from ergostat.library.run import upkeep as uk
from ergostat.numbers import measures as ms
from ergostat.spec import itemindex as ii
from ergostat.spec import read
from ergostat.spec.ir import is_measure
from ergostat.store import Project

HEX = "0123456789abcdef"
KINDS = """
items:
  ticket:
    id: ticket/*
    states: [{states}]
    on: {{ticket.started: doing, ticket.done: done}}
storage:
  events: sqlite
"""
UPKEEP = "uses:\n  upkeep:\n    use: upkeep\n"


def _yaml(root: Path, states: str, upkeep: bool, extra: str = "") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ergostat.yaml").write_text(f"name: {root.name}\n" + textwrap.dedent(KINDS.format(states=states))
                                        + (UPKEEP + extra if upkeep else ""))
    return root


def _cold() -> None:
    for ix in list(ii._OPEN.values()):
        ix.close()
    ii._OPEN.clear()


def _age(d: Path) -> None:
    """Every file in ``d`` unchanged for two hours: past ``TIDY_AGE``."""
    old = time.time() - 2 * ii.TIDY_AGE
    for p in d.iterdir():
        if p.is_file() and not p.is_symlink():
            os.utime(p, (old, old))


def _files(d: Path, n: int, age: float = 2 * ii.TIDY_AGE) -> list[Path]:
    """``n`` index files (empty), each a different age, all older than ``age``."""
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(n):
        p = d / f"{HEX[i] * 16}.db"
        p.write_bytes(b"")
        t = time.time() - age - i * 60
        os.utime(p, (t, t))
        out.append(p)
    return out


def _tidy(state: Path, keep, monkeypatch) -> int:
    monkeypatch.setenv("ERGOSTAT_STATE_DIR", str(state))
    return uk.main(["tidy", "--keep", str(keep)])


def test_upkeep_expands_to_the_index_files_loop(tmp_path):
    root = _yaml(tmp_path / "u", "open, doing, done", True)
    spec, ps = read(root / "ergostat.yaml")
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps]
    mine = lambda xs: {n for n, x in xs.items() if x.system == "upkeep"}   # noqa: E731
    assert mine(spec.stocks) == {"index-files", "retired-index-files"}
    assert mine(spec.flows) == {"index-files-made", "index-files-tidied", "retired-index-files-removed"}
    assert mine(spec.goals) == {"index-files-few", "no-retired-index-files"}
    assert mine({n: b for n, b in spec.blocks.items() if not b.implied}) == {"index-tidier"}   # (and its goal's comparator)
    assert [s.builtin for s in spec.stocks["index-files"].sensors.values()] == ["ergostat.upkeep.index-files"]
    assert [s.builtin for s in spec.stocks["retired-index-files"].sensors.values()] == ["ergostat.upkeep.retired-index-files"]
    assert spec.stocks["index-files"].unit == "files"
    assert [s.changes["what"] for s in spec.flows["index-files-made"].sensors.values()] == ["rises"]
    assert [s.changes["what"] for s in spec.flows["index-files-tidied"].sensors.values()] == ["falls"]
    few, none = spec.goals["index-files-few"], spec.goals["no-retired-index-files"]
    assert (few.of.name, few.hold.op, few.hold.value) == ("index-files", "<=", 6)
    assert (none.of.name, none.hold.op, none.hold.value) == ("retired-index-files", "<=", 0)
    b = spec.blocks["index-tidier"]
    assert b.type == "program" and b.every == 600
    assert b.params["run"].endswith("-m ergostat.library.run upkeep tidy --keep 6")
    assert any(r.kind == "goal" and r.name == "index-files-few" for r in b.reads())
    assert "index-files-tidied" in {r.name for rs in b.outputs.values() for r in rs}
    assert ii.upkept(spec) and not ii.upkept(read(_yaml(tmp_path / "n", "open, doing, done", False) / "ergostat.yaml")[0])


def test_the_index_files_measure_counts_live_and_retired_files(tmp_path):
    state = tmp_path / "state"
    live = _files(state / "items", 4)
    live[3].with_suffix(".retired").touch()                      # the fourth is retired
    (state / "items" / "notes.db").touch()                       # not an index file: not counted
    p = SimpleNamespace(events=SimpleNamespace(path=str(state / "events.db")))
    assert is_measure("ergostat.upkeep.index-files") and is_measure("ergostat.upkeep.retired-index-files")
    assert ms.measure(p, "ergostat.upkeep.index-files") == 3
    assert ms.measure(p, "ergostat.upkeep.retired-index-files") == 1
    nowhere = SimpleNamespace(events=SimpleNamespace(path=":memory:"))    # a record kept nowhere on disk
    assert um.measure(nowhere, "ergostat.upkeep.index-files") is None
    assert ms.measure(nowhere, "ergostat.upkeep.retired-index-files") is None
    empty = SimpleNamespace(events=SimpleNamespace(path=str(tmp_path / "fresh" / "events.db")))   # no items folder
    assert ms.measure(empty, "ergostat.upkeep.index-files") is None


def test_tidy_keeps_n_and_removes_retired_files(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state"
    got = _files(state / "items", 10)
    retired = got[0]                                              # the newest of them: retired goes whatever its age
    retired.with_suffix(".retired").touch()
    assert _tidy(state, 6, monkeypatch) == 0
    left = sorted(p.name for p in (state / "items").glob("*.db"))
    assert left == sorted(p.name for p in got[1:7]), "the six most recently changed live files are left"
    lines = [json.loads(x) for x in capsys.readouterr().out.strip().splitlines()]
    assert lines == [{"out": "flow.index-files-tidied", "moved": 3, "left": 6, "held": 0, "young": 0},
                     {"out": "flow.retired-index-files-removed", "moved": 1}], "each flow moved by what it lost"
    assert not list((state / "items").glob("*.lock")), "the lock files of what went went with them"
    assert _tidy(tmp_path / "none", 6, monkeypatch) == 1, "no items folder: an error, never a clean result"
    assert "cannot be listed" in capsys.readouterr().err


def test_the_tidier_block_moves_its_two_flows_through_the_engine(tmp_path):
    """The block run by the engine as the model has it: each of its two outputs moved by its line, nothing refused."""
    from ergostat.spec.engine import Engine
    root = _yaml(tmp_path / "e", "open, doing, done", True)
    p = Project(mdl.load(root))
    got = _files(Path(p.dir) / "items", 9)
    got[0].with_suffix(".retired").touch()
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["index-tidier"], "test")
    assert not p.events.query(n=None, type="agent.refused"), p.events.query(n=None, type="agent.refused")
    opened = {e["data"]["flow"]: e["data"]["amount"] for e in p.events.query(n=None, type="valve.opened")}
    assert opened == {"index-files-tidied": 2, "retired-index-files-removed": 1}, opened
    assert len(ii.files(Path(p.dir) / "items")[0]) == 6


def test_tidy_never_opens_an_index(tmp_path, monkeypatch):
    root = _yaml(tmp_path / "p", "open, doing, done", True)
    proj = Project(mdl.load(root))
    proj.events.add("ticket.opened", item="ticket/1")
    ix = ii.index_for(proj.events, proj.model.spec, False)
    items = ix.path.parent
    _cold()
    _files(items, 8)
    _age(items)

    def boom(*a, **k):
        raise AssertionError("the tidier went through the project or an index")
    monkeypatch.setattr(ii.Index, "__init__", boom)
    monkeypatch.setattr(ii, "index_for", boom)
    monkeypatch.setattr(common, "project", boom)
    monkeypatch.setattr(ii.sqlite3, "connect", boom)
    before = {p.name for p in items.iterdir()}
    assert _tidy(items.parent, 2, monkeypatch) == 0
    after = {p.name for p in items.iterdir()}
    assert not {n for n in after - before if n.endswith((".db", "-wal", "-shm"))}
    assert len([n for n in after if n.endswith(".db")]) == 2


def test_tidy_checks_age_again_inside_the_lock(tmp_path, monkeypatch):
    state = tmp_path / "state"
    got = _files(state / "items", 3)
    take = ii._take

    def written_meanwhile(path):                                 # another process opens, writes and closes it
        now = time.time()
        os.utime(str(path), (now, now))
        return take(path)
    monkeypatch.setattr(ii, "_take", written_meanwhile)
    assert _tidy(state, 1, monkeypatch) == 0
    assert all(p.exists() for p in got), "a file changed between the look and the lock is kept"
    wal = Path(str(got[1]) + "-wal")                              # a write that touched only the WAL
    wal.touch()
    old = time.time() - 2 * ii.TIDY_AGE
    os.utime(wal, (old, old))

    def wal_written(path):
        if Path(str(path) + "-wal").exists():
            os.utime(str(path) + "-wal", None)
        return take(path)
    monkeypatch.setattr(ii, "_take", wal_written)
    _age(state / "items")
    oldest = old - ii.TIDY_AGE                                    # got[1] the oldest: the one file over keep 2
    for p in (got[1], wal):
        os.utime(p, (oldest, oldest))
    assert _tidy(state, 2, monkeypatch) == 0
    assert got[1].exists(), "a write to the WAL alone counts as a change"


def test_tidy_deletes_only_index_names_under_items(tmp_path, monkeypatch):
    state = tmp_path / "state"
    items = state / "items"
    _files(items, 2, age=0)
    old = time.time() - 10 * ii.TIDY_AGE                          # the strangers are the oldest of all
    outside = tmp_path / "outside.db"
    outside.write_text("theirs")
    notes, link, sub = items / "notes.db", items / f"{'a' * 16}.db", items / "sub" / f"{'b' * 16}.db"
    notes.write_text("notes")
    link.symlink_to(outside)
    sub.parent.mkdir()
    sub.write_text("deep")
    for p in (outside, notes, sub):
        os.utime(p, (old, old))
    os.utime(link, (old, old), follow_symlinks=False)             # the link itself old too: only its kind keeps it
    assert _tidy(state, 1, monkeypatch) == 0
    assert notes.exists() and link.is_symlink() and outside.read_text() == "theirs" and sub.exists()
    assert ii._tidy(items, 1) and notes.exists() and link.is_symlink() and sub.exists(), "the engine's own tidy too"


def test_a_lock_file_that_cannot_be_opened_counts_as_held(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state"
    got = _files(state / "items", 2)
    got[1].with_suffix(".lock").mkdir()                           # its lock cannot be opened: never taken as free
    assert _tidy(state, 1, monkeypatch) == 0
    assert got[1].exists() and '"held": 1' in capsys.readouterr().out


@pytest.mark.parametrize("n", [0, 500])
def test_keep_out_of_range_is_refused_at_load_and_at_run(tmp_path, monkeypatch, n, capsys):
    root = _yaml(tmp_path / "u", "open, doing, done", True, f"    with: {{index-files: {n}}}\n")
    _, ps = read(root / "ergostat.yaml")
    errs = [str(p) for p in ps if p.level == "error"]
    assert errs and all("upkeep" in e and "index-files" in e for e in errs), errs
    _files(tmp_path / "s" / "items", 3)
    for keep in (65, 0, -1):
        assert _tidy(tmp_path / "s", keep, monkeypatch) == 2
    assert len(list((tmp_path / "s" / "items").glob("*.db"))) == 3
    assert _tidy(tmp_path / "s", 64, monkeypatch) == 0


def _fold(root: Path, i: int, upkeep: bool, proj: Project):
    _yaml(root, f"open, doing, done, x{i}", upkeep)
    spec = mdl.load(root).spec
    return ii.index_for(proj.events, spec, False), spec


@pytest.mark.parametrize("upkeep", [True, False])
def test_with_upkeep_the_engine_does_not_tidy_and_without_it_does(tmp_path, upkeep):
    root = tmp_path / f"p{int(upkeep)}"
    _yaml(root, "open, doing, done", upkeep)
    proj = Project(mdl.load(root))
    proj.events.add("ticket.opened", item="ticket/1")
    items = None
    for i in range(8):
        ix, _ = _fold(root, i, upkeep, proj)                      # each a change of the item kinds: a new fold
        items = ix.path.parent
        _cold()                                                   # nobody holds them: only the age and the count say
        _age(items)
    n = len(list(items.glob("*.db")))
    assert n == (8 if upkeep else ii.KEPT_FILES), n


def test_tidying_stopped_piles_files_up_and_nothing_breaks(tmp_path):
    root = tmp_path / "p"
    _yaml(root, "open, doing, done", True)
    proj = Project(mdl.load(root))
    for j in range(5):
        proj.events.add("ticket.opened", item=f"ticket/{j}")
    proj.events.add("ticket.started", item="ticket/1")
    proj.events.add("ticket.done", item="ticket/2")
    items = None
    for i in range(10):
        ix, spec = _fold(root, i, True, proj)
        fresh = ii.Index(tmp_path / f"fresh{i}" / f"{'f' * 16}.db", spec, False)
        fresh.catch_up(proj.events)
        with ix.lock, fresh.lock:
            assert [(x.id, x.state) for x in ix.items("ticket")] == [(x.id, x.state) for x in fresh.items("ticket")]
        fresh.close()
        items = ix.path.parent
        _cold()
        _age(items)
    assert len(ii.files(items)[0]) == 10
