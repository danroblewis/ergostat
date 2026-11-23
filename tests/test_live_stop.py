"""A switch waits for the old engine to go: `run --stop` gives up after 10 s, and a start before the exit starts nothing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "dev" / "bin"
if str(BIN) not in sys.path:
    sys.path.append(str(BIN))          # appended: dev/bin/queue.py must not shadow the standard lib

import live  # noqa: E402
import measure  # noqa: E402


def stopping(monkeypatch, codes: list[int]) -> list[tuple]:
    calls: list[tuple] = []

    def engine(cfg, sha, *args, timeout=120):
        calls.append(args)
        return subprocess.CompletedProcess(args, codes[min(len(calls) - 1, len(codes) - 1)])

    monkeypatch.setattr(live, "engine", engine)
    monkeypatch.setattr(live, "target", lambda path: "a" * 40)
    monkeypatch.setattr(live, "live", lambda cfg: Path("/nowhere"))
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    return calls


def test_stop_asks_again_until_the_engine_has_gone(monkeypatch):
    calls = stopping(monkeypatch, [1, 1, 0])
    live.stop({})
    assert calls == [("run", "--stop")] * 3


def test_stop_returns_at_once_when_it_stopped(monkeypatch):
    calls = stopping(monkeypatch, [0])
    live.stop({})
    assert len(calls) == 1


def test_stop_gives_up_at_its_limit(monkeypatch):
    calls = stopping(monkeypatch, [1])
    monkeypatch.setattr(live, "STOP_WAIT", -1)
    live.stop({})
    assert len(calls) == 1


def test_a_reviews_gap_may_be_a_list_of_one():
    assert measure.review_gap({"fields": {"gap": ["gap/a"]}}) == "gap/a"
    assert measure.review_gap({"fields": {"gap": "gap/a"}}) == "gap/a"
    assert measure.review_gap({"fields": {"gap": []}}) is None
    assert measure.review_gap({"fields": {}}) is None


def test_live_only_edits_can_stay_out_of_the_backlog():
    text = (BIN / "live.py").read_text()
    assert 'get("edits_as_gaps", True)' in text
