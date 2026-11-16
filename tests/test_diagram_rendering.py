"""Acceptance: the control diagram of every example, drawn in a real browser, in every view (the
whole, everything open, each system opened, each drawn alone), draws no line through a part that
is not one of its ends, no line on top of another (lines merging into or out of one end are a net),
no line far longer than the way it covers, and no page error; and lays out within its time.

And a generated model, 16 systems of 6 loops each (STRESS=systems,loops to change it), each
feeding the next and driving a flow two along: about 400 parts and 500 lines, laid out in about
0.6s; 1,000 lines take about 2s.

It needs Playwright and the Chrome installed on this machine, so the usual run skips it:

    uv run --with playwright python -m pytest tests/test_diagram_rendering.py -v -s
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
AUDIT = (ROOT / "scripts" / "diagram_audit.js").read_text()
EXAMPLES = sorted(p.name for p in (ROOT / "examples").iterdir() if (p / "ergostat.yaml").exists())
READY = "() => typeof S !== 'undefined' && S.layout && S.graphSig && document.querySelectorAll('svg.canvas g.node').length > 0"
TIMED = "async () => { const t = performance.now(); await layoutGraph(S.graph, 1.6, false); return performance.now() - t; }"
LAYOUT_BUDGET_MS = 2500        # one layout of the biggest view, on a laptop; generous, to catch the router going quadratic


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception as e:                        # no Chrome here
            pytest.skip(f"no Chrome to drive: {e}")
        yield b
        b.close()


@pytest.fixture(scope="module", params=EXAMPLES)
def page_of(request, tmp_path_factory):
    """The example's page, served (the model is not run: what is drawn is its structure)."""
    name = request.param
    d = tmp_path_factory.mktemp(name) / name
    shutil.copytree(ROOT / "examples" / name, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    port = free_port()
    env = {**os.environ, "ERGOSTAT_HOME": str(d.parent / "home")}
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/api/status", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail(f"{name}: the page never answered")
    yield name, url
    proc.terminate()
    proc.wait(10)


def drawn(pg, url: str, view: str, n: int) -> None:
    pg.goto(f"{url}/?v={n}#/diagram?{view}")            # a new query: the page loads afresh, no layout carried over
    pg.wait_for_function(READY, timeout=20000)


def test_every_view_draws_cleanly_and_in_time(browser, page_of):
    name, url = page_of
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    drawn(pg, url, "", 0)
    tree = pg.evaluate("() => S.graph.tree || {}")
    views = ["", "open=*", *(f"open={s}" for s in tree), *(f"system={s}" for s in tree)]
    problems, slowest = [], (0.0, "")
    for i, v in enumerate(views):
        drawn(pg, url, v, i + 1)
        r = pg.evaluate(AUDIT)
        problems += [f"[{v or 'whole'}] {k}: {x}" for k in ("through", "overlap", "detour") for x in r[k]]
        ms = pg.evaluate(TIMED)
        slowest = max(slowest, (ms, v or "whole"))
    pg.close()
    print(f"{name}: {len(views)} views, slowest layout {slowest[0]:.0f}ms ({slowest[1]})")
    assert not errors, errors
    assert not problems, f"{name}: " + "\n".join(problems)
    assert slowest[0] < LAYOUT_BUDGET_MS, f"{name}: laying out {slowest[1]} took {slowest[0]:.0f}ms"


def big_model(systems: int = 8, loops: int = 4) -> str:
    """Systems of loops in series, each system feeding the next and driving a flow in the one after it:
    many lines crossing system edges, the case the router works hardest on."""
    out = ["name: stress", "systems:"] + [f"  s{i}:\n    description: system {i}" for i in range(systems)]
    stocks, flows, goals, blocks = ["stocks:"], ["flows:"], ["goals:"], ["blocks:"]
    for i in range(systems):
        for j in range(loops):
            q = f"q{i}-{j}"
            stocks += [f"  {q}:", f"    system: s{i}", "    unit: jobs", "    sensor:", "      manual: true"]
            nxt = f"q{i}-{j + 1}" if j + 1 < loops else (f"q{i + 1}-0" if i + 1 < systems else None)
            flows += [f"  {q}-out:", f"    system: s{i}", f"    from: {q}"] + ([f"    to: {nxt}"] if nxt else [])
            if j == 0:
                flows += [f"  {q}-in:", f"    system: s{i}", f"    to: {q}"]
                if i >= 2:
                    flows += [f"    driven-by: flow.q{i - 2}-{loops - 1}-out"]
            goals += [f"  {q}-low:", f"    system: s{i}", f"    stock: {q}", '    hold: "<= 5"']
            blocks += [f"  w{i}-{j}:", f"    system: s{i}", "    type: program", "    run: echo 1", f"    goal: {q}-low",
                       f"    out: flow.{q}-out"]
    return "\n".join(out + stocks + flows + goals + blocks) + "\n"


def test_a_big_tangled_model_lays_out_in_time_and_cleanly(browser, tmp_path):
    d = tmp_path / "stress"
    d.mkdir()
    (d / "ergostat.yaml").write_text(big_model(*map(int, os.environ.get("STRESS", "16,6").split(","))))
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for i, v in enumerate(("", "open=*", "open=s3", "system=s3")):
            drawn(pg, url, v, i)
            ms = pg.evaluate(TIMED)
            r = pg.evaluate(AUDIT)
            n = pg.evaluate("() => [S.graph.nodes.length, S.graph.edges.length]")
            print(f"stress [{v or 'whole'}]: {n[0]} parts, {n[1]} lines, {ms:.0f}ms; through {len(r['through'])}, "
                  f"overlap {len(r['overlap'])}, detour {len(r['detour'])}")
            assert ms < LAYOUT_BUDGET_MS, f"[{v}] took {ms:.0f}ms"
            assert not r["through"] and not r["detour"], (v, r["through"][:5], r["detour"][:5])
        assert not errors, errors
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)
