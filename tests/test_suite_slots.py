"""The kept slot (dev/bin/slots.py): while approved gaps wait and no queue run holds its slot, a suite run in [suites]
slot does not take the last of the machine's slots; the merge queue's own wait counts that slot as its own."""

from __future__ import annotations

import fcntl
import json
import re
import sys
import threading
import time

import pytest

from tests.test_factory import ROOT, module


@pytest.fixture
def fx(tmp_path, monkeypatch):
    """fac and slots, loaded fresh, on a fake load: ``running`` suites seen by ps, ``approved`` gaps in the record."""
    fac = module("fac")
    monkeypatch.setitem(sys.modules, "fac", fac)
    slots = module("slots")
    monkeypatch.setitem(sys.modules, "slots", slots)
    state = {"running": 0, "approved": [{"id": "gap/a"}]}

    def items(kind, st=None):
        if isinstance(state["approved"], Exception):
            raise state["approved"]
        return state["approved"] if (kind, st) == ("gap", "approved") else []

    monkeypatch.setattr(fac, "suites_running", lambda: state["running"])
    monkeypatch.setattr(fac, "items", items)
    monkeypatch.setattr(fac, "renew", lambda *a: None)
    cfg = {"paths": {"run": str(tmp_path / "run"), "queue_lock": str(tmp_path / "queue.lock")},
           "suites": {"slot": "env", "slots": 6, "unit": "echo ran",
                      "build": "sh -c 'echo ran; sleep 3'"}, "load": {"wait": True, "wait_poll": 0.05}}
    return fac, slots, cfg, state, tmp_path


def start(fac, cfg, tmp, n: int, name: str = "unit") -> tuple[threading.Thread, object]:
    """One implementor suite (``name``, in the slot) on a thread of its own; its log."""
    log = tmp / f"log{n}.txt"
    t = threading.Thread(target=fac.suite, args=(cfg, name, tmp, log), daemon=True)
    t.start()
    return t, log


def ran(log) -> bool:
    return log.exists() and "ran" in log.read_text()


def test_the_last_slot_is_kept_for_the_queue_while_approved_gaps_wait(fx):
    fac, slots, cfg, state, tmp = fx
    state["running"] = 5                                     # five of six taken: the sixth is the queue's
    t, log = start(fac, cfg, tmp, 1)
    t.join(1.0)
    assert t.is_alive() and not ran(log)                     # waiting, never started
    queue = tmp / "run" / "queue.json"
    queue.write_text(json.dumps({"running": {"pre": "x", "gaps": ["gap/b"], "at": time.time()}}))
    t.join(0.5)
    assert t.is_alive() and not ran(log)                     # a `running` left with the lock free: a dead run's
    with open(tmp / "queue.lock", "a") as lock:              # a queue run holds its slot: the kept one is not needed
        fcntl.flock(lock, fcntl.LOCK_EX)
        t.join(10)
        fcntl.flock(lock, fcntl.LOCK_UN)
    assert not t.is_alive() and ran(log)
    queue.unlink()
    state["running"] = 4                                     # two free: two sessions look at once, only one passes
    a, la = start(fac, cfg, tmp, 2, "build")                 # (each runs 3 s: the first still running)
    b, lb = start(fac, cfg, tmp, 3, "build")
    time.sleep(1.0)
    assert [ran(la), ran(lb)].count(True) == 1 and (a.is_alive() or b.is_alive())
    state["approved"] = OSError("the record cannot be read")    # unreadable: approved gaps counted as waiting
    time.sleep(0.5)
    assert [ran(la), ran(lb)].count(True) == 1
    state["approved"] = []                                   # landed: the waiting one goes
    a.join(10)
    b.join(10)
    assert ran(la) and ran(lb)
    assert list((tmp / "run" / "slots").iterdir()) == []     # each suite's file removed as it ended


def test_the_slot_is_free_to_implementors_when_nothing_is_approved(fx):
    fac, slots, cfg, state, tmp = fx
    state["running"], state["approved"] = 5, []
    t, log = start(fac, cfg, tmp, 1)
    t.join(10)
    assert not t.is_alive() and ran(log)                     # the last slot taken: nothing waits for the queue
    state["approved"] = [{"id": "gap/a"}]
    state["running"] = 4                                     # with a slot to spare, approved gaps hold nothing back
    t, log = start(fac, cfg, tmp, 2)
    t.join(10)
    assert not t.is_alive() and ran(log)


def test_the_slots_have_a_ceiling_and_the_queue_waits_only_for_the_kept_one(fx, monkeypatch):
    fac, slots, cfg, state, tmp = fx
    for bad in (0, 33, True, "6", 6.0):
        with pytest.raises(ValueError, match=r"\[suites\] slots"):
            fac.slot_count({"suites": {"slots": bad}})
    state["running"] = 5                                     # implementors at most slots - 1: the queue's wait passes
    assert fac.wait_quiet(cfg, most=fac.slot_count(cfg)) < 1.0
    text = (ROOT / "dev" / "bin" / "queue.py").read_text()
    assert "fac.wait_quiet(cfg, most=fac.slot_count(cfg))" in text
    hold = re.search(r"machine-quiet:\s*\n\s*auxiliary: suites-running\s*\n\s*hold: \"<= (\d+)\"",
                     (ROOT / "dev" / "model" / "interlock.yaml").read_text())
    assert hold and int(hold[1]) >= fac.SLOTS - 1           # implementor suites alone keep machine-quiet on
