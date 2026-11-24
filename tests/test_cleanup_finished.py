"""A finished gap's session folders are removed as soon as it is finished, not after [resources] session_keep_hours
(dev/bin/cleanup.py `finished`; dev/records/sessions-removed-when-approved.md)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "dev" / "bin"
FINISHED = ["approved", "queued", "push-pending", "merged", "closed"]
HOUR = time.time() - 3600                      # older than the ten quiet minutes, younger than the 24 hours kept


def module(name: str):
    spec = importlib.util.spec_from_file_location(name, BIN / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def gap(name: str, state: str, **fields) -> dict:
    return {"id": f"gap/{name}", "state": state, "fields": fields}


def folder(sessions: Path, name: str, at: float = HOUR, claude: bool = False) -> Path:
    """A session folder as agents.clone (or sessions.py, ``claude``) makes it, with a clone in it, every part last
    changed at ``at``."""
    stamp = time.strftime("%Y%m%d%H%M%S", time.localtime(at))
    d = sessions / (f"{name}-implementor-1-claude-0a1b2c3d" if claude else f"{name}-implementor-{stamp}-0a1b2c")
    (d / "work" / ".git" / "objects").mkdir(parents=True)
    (d / "work" / "README.md").write_text("x")
    (d / "work" / ".git" / "index").write_text("x")
    for p in sorted(d.rglob("*"), reverse=True) + [d]:
        os.utime(p, (at, at))
    return d


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "fac", module("fac"))
    cleanup = module("cleanup")
    sessions = tmp_path / "live" / "sessions"
    sessions.mkdir(parents=True)
    cfg = {"paths": {"live": str(tmp_path / "live"), "checkout": str(tmp_path / "checkout"), "run": str(tmp_path / "run")},
           "resources": {"session_keep_hours": 24, "finished_states": FINISHED}}
    monkeypatch.setattr(cleanup.fac, "config", lambda: cfg)
    monkeypatch.setattr(cleanup, "docker", lambda *args: "")                # no container running
    return cleanup, sessions, cfg


def test_a_finished_gaps_folders_are_removed_and_a_working_gaps_kept(factory, monkeypatch, capsys):
    cleanup, sessions, cfg = factory
    gaps = [gap("done-one", "approved"), gap("in-fix", "fix"), gap("in-build", "building"), gap("landed", "merged"),
            gap("done-one-more", "building"),                       # its name begins with a finished gap's
            gap("old-try", "merged", branch="shared"), gap("new-try", "building", continues="shared"),
            gap("held", "queued"), gap("a-very-long-gap-title-that-is-cut-short", "push-pending")]
    monkeypatch.setattr(cleanup.fac, "items", lambda kind: gaps if kind == "gap" else [])
    gone = [folder(sessions, "done-one"), folder(sessions, "done-one", claude=True), folder(sessions, "landed"),
            folder(sessions, "a-very-long-gap-title-that-is"),                      # its branch, cut to 32 (branch_of)
            folder(sessions, "a-very-long-gap-title-that-is-cut-short", claude=True)]  # its id's slug (sessions.py)
    kept = [folder(sessions, "in-fix"), folder(sessions, "in-build"), folder(sessions, "in-fix", claude=True),
            folder(sessions, "done-one-more"), folder(sessions, "shared"), folder(sessions, "research-x"),
            folder(sessions, "held", at=time.time() - 300),                  # touched five minutes ago
            folder(sessions, "landed", claude=True)]
    os.utime(kept[-1] / "work" / ".git" / "index")                         # only its clone's index written now
    (sessions / "held-notes").mkdir()                                       # not a name the factory makes
    assert sorted(cleanup.finished(cfg, gone + kept)) == sorted(gone)     # the choice alone (main checks again)
    assert cleanup.main([]) == 0
    assert [d.name for d in gone if d.exists()] == [] and [d.name for d in kept if not d.exists()] == []
    assert (sessions / "held-notes").is_dir()
    assert f"({len(gone)} of finished gaps" in capsys.readouterr().out
    assert cleanup.counted(cfg) == len(gone) == cleanup.sizes(cfg)["sessions-removed-early"]   # the disk measure
    again = folder(sessions, "landed")
    assert cleanup.main(["--dry-run"]) == 0 and again.exists() and cleanup.counted(cfg) == len(gone)
    assert cleanup.main([]) == 0 and not again.exists() and cleanup.counted(cfg) == len(gone) + 1   # a running count
    record = json.loads((Path(cfg["paths"]["run"]) / "resources" / "cleanup.json").read_text())
    assert record["early"] == 1 and record["early-total"] == len(gone) + 1 and record["since"] <= record["at"]


def test_a_folder_a_running_container_mounts_is_kept(factory, monkeypatch):
    cleanup, sessions, cfg = factory
    monkeypatch.setattr(cleanup.fac, "items", lambda kind: [gap("a", "approved"), gap("b", "approved"),
                                                            gap("c", "approved")])
    a, b, c = folder(sessions, "a"), folder(sessions, "b"), folder(sessions, "c")
    asked = []

    def docker(*args):                                   # two containers: one mounts a's clone, the other b itself
        asked.append(args[0])
        return "0a1\n0b2\n" if args[0] == "ps" else f"{a / 'work'}\n/elsewhere\n\n{b}\n"
    monkeypatch.setattr(cleanup, "docker", docker)
    assert cleanup.mounted() == [(a / "work").resolve(), Path("/elsewhere").resolve(), b.resolve()]
    assert cleanup.main([]) == 0 and a.exists() and b.exists() and not c.exists() and "inspect" in asked
    c = folder(sessions, "c")
    monkeypatch.setattr(cleanup, "docker", lambda *args: "0a1" if args[0] == "ps" else f"{sessions}\n")  # all of them
    assert cleanup.main([]) == 0 and a.exists() and b.exists() and c.exists()


@pytest.mark.parametrize("unread", ["record", "docker", "setting", "unset"])
def test_an_unreadable_record_docker_or_setting_removes_nothing_early(factory, monkeypatch, unread, capsys):
    cleanup, sessions, cfg = factory
    monkeypatch.setattr(cleanup.fac, "items", lambda kind: [gap("a", "approved")])
    if unread == "record":
        monkeypatch.setattr(cleanup.fac, "items", lambda kind: 1 / 0)
    elif unread == "docker":
        def no_docker(*args):
            raise RuntimeError("docker ps: Cannot connect to the Docker daemon")
        monkeypatch.setattr(cleanup, "docker", no_docker)
    elif unread == "setting":
        cfg["resources"]["finished_states"] = "approved"                   # a word, not a list
    else:
        del cfg["resources"]["finished_states"]                            # off unless set
    a = folder(sessions, "a")
    aged = folder(sessions, "z", at=time.time() - 3 * 86400)              # past the keep: removed as before
    assert cleanup.main([]) == 0
    assert a.exists() and not aged.exists() and cleanup.counted(cfg) == 0
    assert ("no session folder removed early" in capsys.readouterr().err) == (unread != "unset")


def test_a_folder_touched_after_it_was_chosen_is_kept_and_not_counted(factory, monkeypatch):
    cleanup, sessions, cfg = factory
    a, b = folder(sessions, "a"), folder(sessions, "b")
    real = cleanup.finished

    def chosen_then_touched(cfg, found, now=None):
        got = real(cfg, found, now)
        (a / "-work").mkdir()                                              # a session begins in it meanwhile
        return got
    monkeypatch.setattr(cleanup.fac, "items", lambda kind: [gap("a", "merged"), gap("b", "merged")])
    monkeypatch.setattr(cleanup, "finished", chosen_then_touched)
    assert cleanup.main([]) == 0 and a.exists() and not b.exists() and cleanup.counted(cfg) == 1


def test_a_count_that_cannot_be_read_says_so(factory):
    cleanup, sessions, cfg = factory
    assert cleanup.counted(cfg) == 0                                       # none removed yet
    (Path(cfg["paths"]["run"]) / "resources").mkdir(parents=True)
    (Path(cfg["paths"]["run"]) / "resources" / "cleanup.json").write_text("{not json")
    assert cleanup.counted(cfg) is None and cleanup.sizes(cfg)["sessions-removed-early"] is None
    cleanup.count(cfg, 2, 0.5)                                             # it starts again, saying since when
    assert cleanup.counted(cfg) == 2
