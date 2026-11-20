"""scripts/demo_check.py's check that an item folds as it did before changesets (``items_as_before``): it compares an
item's fold with its events' data at the same moment. The page folds an item as it stood at the engine's latest
snapshot (``/api/items/ID`` folds up to ``until=snap["at"]``), while ``/api/events`` reads the record up to now, so a
workspace event written after the snapshot (an acquire, a hold) made the check flake on a running demo."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent


def demo_check():
    spec = importlib.util.spec_from_file_location("demo_check_under_test", ROOT / "scripts" / "demo_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ITEM = "ergostat.workspace/code-3"
ACQUIRED = {"pool": "code", "slot": 3, "dir": "/w/code/3", "item": "ticket/SCRUM-1", "branch": "b", "how": "fresh",
            "run": "r1", "lease": 1, "acquired": 10.0}
HELD = {"pool": "code", "slot": 3, "dir": "/w/code/3", "item": "ticket/SCRUM-1", "branch": "b", "run": "r1", "lease": 1,
        "why": "its lease ended"}


def page(record: list[dict], snap_at: float, fields: dict | None = None):
    """A fake of the page's two endpoints: the item folded up to the snapshot, the record up to now."""
    def get(url: str):
        if "/api/events?" in url:
            return [e for e in record if unquote(url.split("item=")[1].split("&")[0]) == e["item"]]
        if url.endswith("/api/items"):
            return {"items": [{"id": ITEM, "kind": "ergostat.workspace"}]}
        upto = [e for e in record if e["time"] <= snap_at]
        got: dict = {}
        for e in upto:
            got.update(e["data"])
        return {"fields": fields if fields is not None else got, "last": max(e["time"] for e in upto),
                "events": len(upto), "refused": []}
    return get


def record() -> list[dict]:
    return [{"id": "a", "seq": 1, "time": 10.0, "type": "ergostat.workspace.acquired", "item": ITEM, "data": ACQUIRED},
            {"id": "h", "seq": 2, "time": 20.0, "type": "ergostat.workspace.held", "item": ITEM, "data": HELD}]


def test_an_event_after_the_snapshot_is_not_a_difference(monkeypatch):
    """The page's snapshot was taken at 15: the hold at 20 is in the record but not yet in the page's fold. Both sides
    are read as of the fold, so the item folds as before."""
    dc = demo_check()
    monkeypatch.setattr(dc, "get", page(record(), snap_at=15.0))
    assert dc.items_as_before("http://x", None) == []


def test_a_real_difference_is_still_found_and_named_by_its_first_key(monkeypatch):
    dc = demo_check()
    wrong = {**ACQUIRED, **HELD, "branch": "other"}
    monkeypatch.setattr(dc, "get", page(record(), snap_at=25.0, fields=wrong))
    got = dc.items_as_before("http://x", None)
    assert len(got) == 1
    assert got[0].startswith(f"item {ITEM}: folds differently than before: branch: now \"other\", before \"b\"")


def test_first_diff_names_a_missing_key_and_counts_the_rest():
    dc = demo_check()
    assert dc.first_diff({"a": 1, "b": 2}, {"a": 1}) == "b: now 2, before missing"
    assert dc.first_diff({"a": 1, "c": 3}, {"a": 2, "b": 2}) == "a: now 1, before 2 (and 2 more keys)"
    assert dc.first_diff({"a": 1}, {"a": 1}) == "no key differs"
