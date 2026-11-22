"""The model behind the picture, as Markdown (export_api.py, GET /api/export): Dynamics as a variable table, the flows
per stock and the loop list; Blocks as a row per control loop; and the two Export menu entries that download them."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.store import Project
from ergostat.web.export_api import side_list
from ergostat.web.server import Live, api

ROOT = Path(__file__).resolve().parent.parent
SMALL = """\
name: small
purpose: an inbox kept short
systems:
  desk:
    description: where the files wait
stocks:
  inbox:
    unit: files
    system: desk
    sensor:
      run: echo 3
      every: 5s
flows:
  arrivals:
    to: inbox
    rate: 2
    system: desk
  processed:
    from: inbox
    system: desk
auxiliaries:
  pressure:
    unit: files
    equation: stock.inbox * 2
goals:
  inbox-short:
    stock: inbox
    hold: "<= 20"
blocks:
  worker:
    type: program
    goal: inbox-short
    run: echo 1
    out: flow.processed
"""


def tables(md: str) -> dict[str, list[dict]]:
    """Each Markdown table under its ``##`` heading, as rows keyed by the header: it fails unless every table has a
    header, a ``---`` separator, and rows of the header's width (an escaped ``\\|`` is not a column)."""
    out, heading, lines = {}, None, md.splitlines()
    split = lambda ln: [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", ln.strip())[1:-1]]  # noqa: E731
    i = 0
    while i < len(lines):
        if lines[i].startswith("## "):
            heading = lines[i][3:]
        elif lines[i].startswith("|"):
            head = split(lines[i])
            assert re.fullmatch(r"\|( --- \|)+", lines[i + 1]) and lines[i + 1].count("---") == len(head), lines[i + 1]
            rows, i = [], i + 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = split(lines[i])
                assert len(cells) == len(head), (head, lines[i])
                rows.append(dict(zip(head, cells, strict=True)))
                i += 1
            out[heading] = rows
            continue
        i += 1
    return out


def live_of(d: Path, text: str | None = None) -> Live:
    if text is not None:
        (d / "ergostat.yaml").write_text(text)
    (d.parent / "state").mkdir(exist_ok=True)
    return Live(Project(mdl.load(d), directory=d.parent / "state"))


def drawn_parts(g: dict) -> list[str]:
    return sorted(n["label"] for n in g["nodes"] if n["kind"] in ("stock", "auxiliary", "valve", "disturbance"))


def test_the_dynamics_document_has_a_row_per_part_drawn_and_the_side_lists_loops(tmp_path):
    (tmp_path / "m").mkdir()
    live = live_of(tmp_path / "m", SMALL)
    got = api(live, "export", {"view": ["dynamics"], "format": ["json"]})
    md, t = got["markdown"], tables(got["markdown"])
    assert md.startswith("# small: the model (system dynamics)\n\nan inbox kept short\n"), md[:200]
    assert "- System: everything" in md and "- Moment: " in md and "- Window: " in md
    assert re.fullmatch(r"small-all-dynamics-\d{4}-\d\d-\d\d\.md", got["file"]), got["file"]
    g = api(live, "graph", {"view": ["dynamics"]})
    rows = {r["name"]: r for r in t["Variables"]}
    assert sorted(rows) == drawn_parts(g) and len(t["Variables"]) == len(rows)
    assert rows["inbox"]["kind"] == "stock" and rows["inbox"]["unit"] == "files"
    assert "sensor main, every 5 s" in rows["inbox"]["equation or sensor"], rows["inbox"]
    assert rows["pressure"]["kind"] == "auxiliary" and rows["pressure"]["equation or sensor"] == "stock.inbox * 2"
    flows = {n["label"]: n for n in g["nodes"] if n["kind"] in ("valve", "disturbance")}
    assert rows["processed"]["equation or sensor"] == flows["processed"]["equation"]      # the panel's words
    assert rows["arrivals"]["equation or sensor"] == "2 per hour, declared: a constant"
    assert any(r["kind"] == "goal" for r in t["Variables"])
    assert t["Flows per stock"] == [{"stock": "inbox", "in": "arrivals", "out": "processed"}]
    loops = [r["name"] for r in t["Feedback loops"]]
    assert loops and loops == [c["name"] for c, _ in side_list(g)]
    assert all(r["goal it closes"] == "inbox-short" and r["polarity"] in ("R", "B", "?") for r in t["Feedback loops"])


def test_the_blocks_document_has_a_row_per_goal_in_view_with_the_panels_law(tmp_path):
    (tmp_path / "m").mkdir()
    live = live_of(tmp_path / "m", SMALL)
    md = api(live, "export", {"view": ["blocks"], "system": ["desk"]})["markdown"]
    assert md.startswith("# small: the control loops (block diagram)") and "- System: desk" in md
    g = api(live, "graph", {"view": ["blocks"], "system": ["desk"]})
    rows = tables(md)["Control loops"]
    assert [r["goal"] for r in rows] == list(g["loops"]) == ["inbox-short"]
    r = rows[0]
    ctl = "keep-inbox-short"                                   # (goal: on the worker: the on-off controller it implies)
    says = next(n["says"] for n in api(live, "graph", {"view": ["blocks"], "open": ["*"]})["nodes"] if n["id"] == f"blk:{ctl}")
    assert r["controller and its law"] == f"{ctl}: {' '.join(says.split())}", (r, says)
    assert "on-off controller" in says and r["actuator"] == "worker (sets processed)", r
    assert r["reference"] == "inbox ≤ 20" and r["measured output"] == "y inbox (measured)"
    assert r["sensor and period"] == "sensor main, every 5 s" and r["process"].endswith("not identified")


def test_a_small_spec_with_no_loops_still_gives_tables(tmp_path):
    (tmp_path / "m").mkdir()
    live = live_of(tmp_path / "m", "name: bare\nstocks:\n  pile:\n    unit: things\n")
    t = tables(api(live, "export", {"view": ["dynamics"]})["markdown"])
    assert [r["name"] for r in t["Variables"]] == ["pile"] and t["Feedback loops"] == []
    assert tables(api(live, "export", {"view": ["blocks"]})["markdown"])["Control loops"] == []


def test_software_factory_product_dynamics_matches_what_is_drawn():
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:                     # (a copy: the example is never written to)
        d = Path(tmp) / "software-factory"
        shutil.copytree(ROOT / "examples" / "software-factory", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
        live = live_of(d)
        q = {"view": ["dynamics"], "system": ["product"]}
        t = tables(api(live, "export", q)["markdown"])
        g = api(live, "graph", q)
        assert sorted(r["name"] for r in t["Variables"]) == drawn_parts(g) and len(t["Variables"]) > 3
        assert [r["name"] for r in t["Feedback loops"]] == [c["name"] for c, _ in side_list(g)]
        assert t["Feedback loops"], "the product's loops close through the factory"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """The small model's page, served (not run)."""
    d = tmp_path_factory.mktemp("export") / "m"
    d.mkdir()
    (d / "ergostat.yaml").write_text(SMALL)
    with __import__("socket").socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(d.parent / "home")},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        else:
            pytest.fail("the page never answered")
        yield url, d
    finally:
        proc.terminate()
        proc.wait(10)


def test_the_endpoint_answers_markdown_for_curl_and_refuses_another_view(site):
    url, _ = site
    with urllib.request.urlopen(url + "/api/export?view=dynamics&format=md&system=desk", timeout=30) as r:
        assert r.headers["Content-Type"].startswith("text/markdown")
        body = r.read().decode()
    assert body.startswith("# small: the model") and "- System: desk" in body and tables(body)["Variables"]
    for bad in ("view=process", "view=dynamics&format=pdf"):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(url + "/api/export?" + bad, timeout=30)
        assert e.value.code == 400


@pytest.fixture(scope="module")
def browser():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:
            b = p.chromium.launch(channel="chrome")
        yield b
        b.close()


READY = "() => typeof S !== 'undefined' && S.graph && document.querySelectorAll('svg.canvas g.node').length > 0"


def download(pg, entry: str) -> tuple[str, str]:
    pg.locator(".zoom .menu-btn", has_text="Export").click()
    with pg.expect_download() as d:
        pg.locator(".menu-item", has_text=entry).click()
    return d.value.suggested_filename, Path(d.value.path()).read_text()


def test_the_export_menu_downloads_the_model_and_the_loops(browser, site):
    url, _ = site
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{url}/diagram?view=dynamics&system=desk")
    pg.wait_for_function(READY, timeout=120000)
    pg.wait_for_selector(".side .looprow")
    name, md = download(pg, "Model (Markdown)")
    assert re.fullmatch(r"small-desk-dynamics-\d{4}-\d\d-\d\d\.md", name), name
    t = tables(md)
    parts = pg.evaluate("() => S.graph.nodes.filter((n) => ['stock', 'auxiliary', 'valve', 'disturbance'].includes(n.kind))"
                        ".map((n) => n.label).sort()")
    assert sorted(r["name"] for r in t["Variables"]) == parts
    side = pg.evaluate("() => [...document.querySelectorAll('.side .looprow[data-loop]')].map((r) => r.dataset.loop)")
    assert [r["name"] for r in t["Feedback loops"] if r["drawn"] == "drawn"] == side and side
    assert len(t["Feedback loops"]) == int(pg.locator(".side h3", has_text="Feedback loops").locator(".muted").inner_text())
    pg.goto(f"{url}/diagram?view=blocks")
    pg.wait_for_function(READY + " && S.graph.kind === 'blocks'", timeout=120000)
    pg.wait_for_selector(".side .looprow")
    name, md = download(pg, "Loops (Markdown)")
    assert re.fullmatch(r"small-all-blocks-\d{4}-\d\d-\d\d\.md", name), name
    rows = tables(md)["Control loops"]
    assert [r["goal"] for r in rows] == pg.evaluate("() => [...document.querySelectorAll('.side .looprow')].map((r) => r.dataset.loop)")
    pg.evaluate("() => openBlock(S.graph.nodes.find((n) => n.id === 'blk:keep-inbox-short'))")       # its panel (blocks.js)
    law = " ".join(pg.locator("#detail p.what").first.inner_text().split())
    # the panel's words, its y_inbox drawn as a subscript (rich(): y and a <sub>inbox</sub>, so "yinbox" as text)
    assert rows[0]["controller and its law"].replace("y_", "y") == f"keep-inbox-short: {law}", (rows[0], law)
    assert "y_inbox" in rows[0]["controller and its law"]
    assert pg.locator(".menu-item", has_text="Model (Markdown)").count() == 0
    assert not errors, errors
    pg.close()


def test_a_snapshot_file_says_it_cannot_export_the_model(browser, tmp_path):
    from ergostat.web.snapshot import build
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "ergostat.yaml").write_text(textwrap.dedent(SMALL))
    f = tmp_path / "snapshot.html"
    f.write_text(build(Project(mdl.load(tmp_path / "m"))))
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    said: list[str] = []
    pg.on("dialog", lambda d: (said.append(d.message), d.dismiss()))
    pg.goto(f.as_uri() + "#/diagram?view=dynamics")
    pg.wait_for_function(READY, timeout=120000)
    pg.locator(".zoom .menu-btn", has_text="Export").click()
    pg.locator(".menu-item", has_text="Model (Markdown)").click()
    for _ in range(50):
        if said:
            break
        pg.wait_for_timeout(100)
    assert said and "snapshot file cannot export the model" in said[0], said
    pg.close()
