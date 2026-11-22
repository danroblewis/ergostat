"""A precedence relation's ``starts_at`` (SPEC §5a, *Relations*): a target in a named state does not block, for
status and for ``takes: {unblocked: true}``; the critical path stays finish-to-start."""

from __future__ import annotations

import textwrap
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat import precedence as pr
from ergostat.leases.ready import unblocked
from ergostat.spec import items as its
from ergostat.store import Project

T0 = 1_700_000_000.0

MODEL = """
items:
  gap:
    id: gap/*
    states: [ready, doing, review, fix, approved, merged]
    on: {gap.opened: ready, gap.started: doing, gap.reviewed: review, gap.failed: fix, gap.approved: approved,
         gap.merged: merged}
    relations:
      depends_on: {kind: gap, starts_at: [approved]}
messages:
  done: {gap: [merged]}
blocks:
  dev:
    type: program
    run: "true"
    takes: {kind: gap, at: [ready], to: [merged], unblocked: true}
"""


def project(tmp_path) -> Project:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def record(tmp_path, dep_at: str) -> Project:
    """Finished gaps (100 s doing, 100 s review, 300 s approved); gap/a moved to ``dep_at``; gap/b depends on it."""
    p = project(tmp_path)
    ev = p.events
    for n in range(3):
        g = f"gap/old{n}"
        for e, dt in (("opened", 0), ("started", 10), ("reviewed", 110), ("approved", 210), ("merged", 510)):
            ev.add(f"gap.{e}", item=g, at=T0 + dt + n)
    t = T0 + 1000
    ev.add("gap.opened", item="gap/a", at=t)
    for e in ("started", "reviewed", "approved") + (("failed",) if dep_at == "fix" else ()):
        t += 1
        ev.add(f"gap.{e}", item="gap/a", at=t)
    ev.add("gap.opened", item="gap/b", data={"depends_on": "gap/a"}, at=t + 1)
    return p


def taken(p) -> list[str]:
    spec, b = p.model.spec, p.model.spec.blocks["dev"]
    got = [i for i in its.project(p.events, spec, "gap") if i.state in b.takes.at]
    return [i.id for i in unblocked(SimpleNamespace(p=p, spec=spec), b, got)]


def test_starts_at_lets_a_dependent_start_on_an_approved_target(tmp_path):
    p = record(tmp_path, "approved")
    assert p.model.spec.items["gap"].relations["depends_on"].starts_at == ["approved"]
    assert taken(p) == ["gap/b"]
    pr._CACHE.clear()
    assert taken(record(tmp_path / "fix", "fix")) == []                 # its dependency in fix: not taken


def test_starts_at_leaves_the_critical_path_finish_to_start(tmp_path):
    p = record(tmp_path, "approved")
    now = T0 + 1010
    g = pr.build(p.events, p.model.spec, ["gap"], now, now)
    by = {x["id"]: x for x in g["items"]}
    assert by["gap/b"]["status"] == "unblocked" and by["gap/b"]["waiting"] == []
    assert by["gap/a"]["ef"] - now == pytest.approx(293)               # 300 s in approved, 7 s of it gone
    assert by["gap/b"]["es"] - now == pytest.approx(293)               # the dependent is projected after it ends
    assert g["critical"] == ["gap/a", "gap/b"]
    assert g["kinds"][0]["relations"]["depends_on"]["starts_at"] == ["approved"]
    q = record(tmp_path / "fix", "fix")
    by = {x["id"]: x for x in pr.build(q.events, q.model.spec, ["gap"], now, now)["items"]}
    assert by["gap/b"]["status"] == "blocked" and by["gap/b"]["waiting"] == ["gap/a"]


@pytest.mark.parametrize("dep_at, waits", [("approved", []), ("fix", ["gap/a"])])
def test_starts_at_in_the_items_api_and_past_the_graph(tmp_path, monkeypatch, dep_at, waits):
    p = record(tmp_path, dep_at)
    spec = p.model.spec
    b = next(i for i in its.project(p.events, spec, "gap") if i.id == "gap/b")
    rel = its.related(p.events, spec, b, spec.items["gap"])
    assert rel["waiting"] == waits and rel["relations"]["depends_on"]["starts_at"] == ["approved"]
    monkeypatch.setattr(pr, "_cached", lambda *a: {"items": []})      # gap/b past the graph's caps: read alone
    assert taken(p) == ([] if waits else ["gap/b"])
