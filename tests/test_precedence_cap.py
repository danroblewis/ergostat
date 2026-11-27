"""A dependency beyond the graph's cap (``precedence.MOST_PULLED``) is read by id: its real status decides whether its
dependent waits, whatever ``PYTHONHASHSEED`` is; one that cannot be read at all blocks, and is named."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace

from ergostat import model as mdl
from ergostat import precedence as pr
from ergostat.leases.ready import unblocked
from ergostat.spec import items as its
from ergostat.store import Project

MODEL = """
projections:
  ticket:
    id: ticket/*
    states: [todo, doing, done]
    on: {ticket.opened: todo, ticket.started: doing, ticket.done: done}
    relations: {blocked_by: [ticket, part]}
  part:
    id: part/*
    states: [open, made]
    on: {part.opened: open, part.made: made}
messages:
  done: {ticket: [done], part: [made]}
blocks:
  dev:
    type: program
    run: "true"
    takes: {projection: ticket, at: [todo], to: [done], unblocked: true}
"""

N = pr.MOST_PULLED + 5          # more dependencies than the graph holds: the last ones (by id) are cut from it


def project(tmp_path) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def record(tmp_path, last_open: bool = False, never: bool = False) -> Project:
    """ticket/w blocked by N parts, every one made except, with ``last_open``, the last; with ``never``, also by a
    part never recorded; and ticket/free, blocked by nothing."""
    p = project(tmp_path)
    ev, t = p.events, time.time() - 1000
    deps = [f"part/p{n:03d}" for n in range(N)]
    for n, d in enumerate(deps):
        ev.add("part.opened", item=d, at=t + n / 1000)
        if not (last_open and n == N - 1):
            ev.add("part.made", item=d, at=t + 1 + n / 1000)
    ev.add("ticket.opened", item="ticket/free", at=t + 2)
    ev.add("ticket.opened", item="ticket/w", data={"blocked_by": deps + (["part/zz-never"] if never else [])}, at=t + 3)
    return p


def dispatched(p) -> list[str]:
    spec, b = p.model.spec, p.model.spec.blocks["dev"]
    got = [i for i in its.project(p.events, spec, "ticket") if i.state in b.takes.at]
    return sorted(i.id for i in unblocked(SimpleNamespace(p=p, spec=spec), b, got))


def graph(p) -> dict:
    return {x["id"]: x for x in pr.build(p.events, p.model.spec, ["ticket"], time.time(), time.time())["items"]}


def test_a_finished_dependency_beyond_the_cap_does_not_block(tmp_path):
    p = record(tmp_path)
    g = graph(p)
    assert f"part/p{N - 1:03d}" not in g                     # cut from the graph...
    assert g["ticket/w"]["waiting"] == [] and g["ticket/w"]["status"] == "unblocked"     # ...and read by id
    assert dispatched(p) == ["ticket/free", "ticket/w"]


def test_the_result_does_not_depend_on_the_hash_seed(tmp_path):
    record(tmp_path)
    code = textwrap.dedent(f"""
        import sys; sys.path.insert(0, {os.path.dirname(__file__)!r})
        from pathlib import Path
        import test_precedence_cap as t
        p = t.project(Path({str(tmp_path)!r}))
        g = t.graph(p)
        print(t.dispatched(p), sorted(g), g["ticket/w"]["waiting"])
    """)
    seen = set()
    for seed in ("0", "1", "7", "12345"):
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                           env={**os.environ, "PYTHONHASHSEED": seed})
        assert r.returncode == 0, r.stderr
        assert r.stdout.startswith("['ticket/free', 'ticket/w']"), (seed, r.stdout)
        seen.add(r.stdout)
    assert len(seen) == 1                                    # the same graph, the same eligibility, under every seed


def test_an_unfinished_dependency_beyond_the_cap_blocks_and_is_named(tmp_path):
    p = record(tmp_path, last_open=True)
    g = graph(p)
    last = f"part/p{N - 1:03d}"
    assert last not in g
    assert g["ticket/w"]["waiting"] == [last] and g["ticket/w"]["status"] == "blocked"
    assert dispatched(p) == ["ticket/free"]


def test_a_systems_graph_draws_another_kinds_dependencies_as_stubs_and_counts_them_all(tmp_path):
    p = record(tmp_path, last_open=True)
    g = pr.build(p.events, p.model.spec, ["ticket"], time.time(), time.time(), own=["ticket"])
    last = f"part/p{N - 1:03d}"
    assert sorted(x["id"] for x in g["items"]) == ["ticket/free", "ticket/w"]       # no part a full item
    assert len(g["outside"]) == pr.MOST_PULLED and g["capped"]["outside"] == N - pr.MOST_PULLED
    assert last not in {x["id"] for x in g["outside"]}                              # cut from the stubs...
    w = next(x for x in g["items"] if x["id"] == "ticket/w")
    assert w["waiting"] == [last] and w["status"] == "blocked"                      # ...and its status still counts


def test_an_unreadable_dependency_blocks_and_is_named(tmp_path):
    p = record(tmp_path, never=True)
    g = graph(p)
    assert g["ticket/w"]["waiting"] == ["part/zz-never"] and g["ticket/w"]["status"] == "blocked"
    assert dispatched(p) == ["ticket/free"]
