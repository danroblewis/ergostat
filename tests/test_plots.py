"""Acceptance (plots.js): several flows on one axis in one unit, a phase plot's joined path and its marks, a heatmap of a
kind's states, in both themes with no console error; and the bucket alignment the phase plot pairs by. The browser
checks need Playwright: uv run --with playwright==1.63.0 python -m pytest tests/test_plots.py"""

import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests.ports import free_port
from tests.test_series import get
from tests.test_style_tokens import COLOUR

ROOT = Path(__file__).resolve().parent.parent
PAGE = ('<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/static/style.css"><main id="m" style="width:720px"></main>'
        + "".join(f'<script src="/static/{f}.js"></script>' for f in ("elk.bundled", "uplot/uPlot.iife.min", "util", "charts", "plots")))
SEED = """import time, sys; from pathlib import Path; from ergostat import model as mdl; from ergostat.store import Project
p = Project(mdl.load(Path(sys.argv[1]))); now = time.time(); p.events.add("ergostat.started", at=now - 600)
for i in range(6):
    p.measurements.add(p.model.spec.stocks["disk-used"].sensors["main"].series, 50 + 6 * i, at=now - 550 + i * 100)
    p.events.add("valve.opened", item="delete-old-files", data={"amount": 1}, at=now - 560 + i * 100)"""
MOUNT = """async () => {
  const T = Array.from({ length: 12 }, (_, i) => 1.7e9 + i * 60), m = document.getElementById("m");
  m.append(multiChart(await (await fetch("/api/series?refs=flow.logs-written,flow.cleaned&points=6")).json()));
  m.append(phasePlot({ times: T, x: { name: "queue", unit: "items", values: T.map((_, i) => (i === 5 ? null : i)) },
                       y: { name: "done", unit: "items", values: T.map((_, i) => (i * i) % 7), goal: { value: 3 } } }));
  m.append(heatmap(heatOfStates({ kind: "pr", times: T, states: ["open", "review", "merged"],
    counts: { open: T.map((_, i) => (i % 2 ? 4 : 0)), review: T.map(() => 2), merged: T.map(() => 4) } })));
  m.append(heatmap(heatOfGoals([{ goal: "g", unit: "%", times: T, off: [[T[3], T[5]]], e: T.map((_, i) => -i) }])));
  for (let n = 0; n < 100 && [...m.querySelectorAll(".chart-plot")].some((e) => !e.plot); n++) await new Promise((r) => setTimeout(r, 50));
  const plot = (c) => m.querySelector(`.${c} .chart-plot`).plot, one = document.createElement("canvas").getContext("2d");
  const rgb = (t) => { one.fillStyle = tok(t); one.fillRect(0, 0, 1, 1); return [...one.getImageData(0, 0, 1, 1).data].slice(0, 3); };
  const at = (u, x, y) => [...u.ctx.getImageData(Math.round(x), Math.round(y), 1, 1).data].slice(0, 3);
  const near = (a, b) => a.every((v, i) => Math.abs(v - b[i]) < 40);
  const mu = plot("plot-multi"), all = mu.ctx.getImageData(0, 0, mu.width * devicePixelRatio, mu.height * devicePixelRatio).data;
  const hues = ["--g0", "--g1"].map((t) => { const c = rgb(t); let n = 0;
    for (let i = 0; i < all.length; i += 4) if (near([all[i], all[i + 1], all[i + 2]], c)) n++; return n; });
  const ph = plot("plot-phase"), P = (x, y) => at(ph, ph.valToPos(x, "x", true), ph.valToPos(y, "y", true));
  const hm = plot("plot-heat"), cell = (i, k) => at(hm, hm.valToPos(T[i], "x", true), hm.valToPos(3 - k - 0.5, "y", true));
  const want = { 0: (i) => (i % 2 ? "--ink" : "--fill"), 1: () => "--fan-50", 2: () => "--ink" };
  return { chips: [...m.querySelectorAll(".plot-chip")].map((e) => e.textContent), hues,
    first: near(P(0, 0), rgb("--bg")), last: near(P(11, 2), rgb("--ink")), joined: near(P(1.5, 2.5), rgb("--ink")),
    phaseRows: m.querySelectorAll(".plot-phase tbody tr").length,
    heatCols: m.querySelector(".plot-heat").querySelectorAll("thead th").length - 1,
    cells: [0, 1, 2].every((k) => T.every((_, i) => near(cell(i, k), rgb(want[k](i))))),
    off: [4, 8].map((i) => { const g = m.querySelectorAll(".plot-heat .chart-plot")[1].plot;
      return near(at(g, g.valToPos(T[i], "x", true), g.valToPos(1, "y", true) + 1), rgb("--bad")); }),
    goalKey: m.querySelectorAll(".plot-heat .plot-key")[1].textContent,
    named: [...m.querySelectorAll("figure")].map((f) => f.getAttribute("aria-label")) };
}"""


def test_two_refs_share_one_time_base_and_a_reading_lands_in_its_own_bucket(project):
    now = time.time()
    project.events.add("ergostat.started", at=now - 600)
    project.measurements.add("sensor/disk-usage", 77, at=now - 600 + 250)          # bucket 2 of 6, 100 s each
    got = get(project, "series", refs="stock.disk-used,flow.cleaned", points=6)
    w = (got["until"] - got["since"]) / 6
    assert [round(t - got["since"] - (i + 0.5) * w, 2) for i, t in enumerate(got["times"])] == [0] * 6
    assert [len(s["values"]) for s in got["series"]] == [6, 6] and got["series"][0]["values"][2] == 77


def test_plots_js_is_coloured_only_from_tokens():
    assert not COLOUR.search((ROOT / "ergostat/web/static/plots.js").read_text())


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("plots") / "disk-space"
    shutil.copytree(ROOT / "examples" / "disk-space", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    env = {**os.environ, "ERGOSTAT_HOME": str(d.parent / "home")}
    subprocess.run([sys.executable, "-c", SEED, str(d)], env=env, check=True, capture_output=True)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            urllib.request.urlopen(url + "/api/status", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_three_forms_draw_in_each_theme(site, theme):
    sync = pytest.importorskip("playwright.sync_api")
    with sync.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(color_scheme=theme, viewport={"width": 900, "height": 1200})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.route(f"{site}/plots-test", lambda r: r.fulfill(content_type="text/html", body=PAGE))   # the test page
        pg.goto(f"{site}/plots-test")
        got = pg.evaluate(MOUNT)
        b.close()
    names = [c.split(" ")[0] for c in got["chips"]]
    units = {re.sub(r"^.*\d ", "", c) for c in got["chips"]}
    assert names == ["logs-written", "cleaned"] and len(units) == 1 and units.pop().startswith("%/"), got["chips"]
    assert min(got["hues"]) > 20, got["hues"]                       # each line drawn in its own hue
    assert got["first"] and got["last"] and got["joined"] and got["phaseRows"] == 11, got
    assert got["heatCols"] == 3 and got["cells"], got               # one row per state, a cell per bucket
    assert got["off"] == [True, False] and "its own lowest" in got["goalKey"] and "off" in got["goalKey"], got
    assert len(got["named"]) == 4 and all(got["named"]) and not errors, (got["named"], errors)
