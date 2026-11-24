"""Acceptance: an agent's own page, /agent/NAME (agent.js): what it is by its rung (its prompt and wrapper, its program,
its law, its ask, how it decides), its definition as written, its place, what it did; a name with no agent says so;
it fits a phone; and every agent of every example opens with no console error, its first section its rung's.

It needs Playwright and a Chromium:

    uv run --with playwright==1.63.0 python scripts/named_tests.py tests/test_agent_page.py"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from tests.ports import free_port

ROOT = Path(__file__).resolve().parent.parent
SECTION = ["What they are asked", "Its prompt", "Its specification", "How it decides", "Its program", "Its law", "Its law"]
NOT_SHOWN = r"/private/tmp|\.venv|SPEC §"
EXAMPLES = sorted(p.parent.relative_to(ROOT / "examples").as_posix()          # the nested demos too (remote-pair/*)
                  for p in (ROOT / "examples").glob("**/ergostat.yaml") if "run" not in p.parts)


def serve(tmp: Path, example: str, edit=None):
    d = tmp / example
    shutil.copytree(ROOT / "examples" / example, d, ignore=shutil.ignore_patterns("run", "__pycache__", ".ergostat"))
    if edit:
        edit(d)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp / "home")},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 120
    while True:
        try:
            urllib.request.urlopen(url + "/api/status", timeout=2)
            break
        except Exception:
            if time.monotonic() > deadline or proc.poll() is not None:
                proc.kill()
                pytest.fail(f"{example}'s page never answered")
            time.sleep(0.2)
    return proc, url


@pytest.fixture(scope="module")
def tf(tmp_path_factory):
    proc, url = serve(tmp_path_factory.mktemp("tf"), "ticket-factory")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


def banded(d: Path) -> None:
    """The goal work serves given a tolerance, so its implied relay has a band: it releases at the goal's bound, not
    at its threshold (the example's goal has none, and then its law has no 'releases at')."""
    f = d / "steps" / "03-work.yaml"
    f.write_text(f.read_text().replace('    hold: "<= 0"\n', '    hold: "<= 0"\n    tolerance: 2\n', 1))


@pytest.fixture(scope="module")
def tf_band(tmp_path_factory):
    proc, url = serve(tmp_path_factory.mktemp("tfb"), "ticket-factory", banded)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def df(tmp_path_factory):
    proc, url = serve(tmp_path_factory.mktemp("df"), "docs-fresh")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def agents(url: str) -> dict:
    with urllib.request.urlopen(url + "/api/agents", timeout=30) as r:
        return json.load(r)


def opened(browser, url: str, name: str, width: int = 1400):
    pg = browser.new_page(viewport={"width": width, "height": 900})
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    pg.goto(f"{url}/agent/{urllib.parse.quote(name, safe='')}")
    pg.wait_for_selector(".agent-page section h2, .agent-page .no-agent", timeout=30000)
    return pg


def first_h2(pg) -> str:
    return pg.eval_on_selector(".agent-page h2", "e => e.textContent")


def test_an_ai_agents_page_shows_its_prompt_rendered_and_its_wrapper_highlighted(browser, tf):
    pg = opened(browser, tf, "work")
    assert first_h2(pg) == "Its prompt"
    pg.wait_for_selector("#what-it-is .md")
    prompt = pg.inner_text("#what-it-is .md")
    assert "You are a software engineer" in prompt and not re.search(r"(?m)^\s*#", prompt)   # Markdown, not its source
    assert "prompts/work.md" in pg.inner_text("#what-it-is")
    slots = pg.eval_on_selector_all("#what-it-is mark.slot", "els => els.map((e) => [e.textContent, e.title])")
    assert ["{key}", "filled per item"] in slots, slots
    assert pg.eval_on_selector("#what-it-is details.wrapper", "d => d.open") is False      # closed until opened
    assert pg.inner_text("#what-it-is details.wrapper > summary") == "Its wrapper"
    files = pg.eval_on_selector_all("#what-it-is details.wrapper details.agent-file", """ds => ds.map((d) =>
        [d.querySelector('summary').textContent, !!d.querySelector('code.hljs .hljs-keyword, code.hljs .hljs-string')])""")
    assert ["bin/step.py", True] in files, files                                         # highlighted, not plain
    assert "takes" in pg.inner_text("#what-it-is dl") and "ticket" in pg.inner_text("#what-it-is dl")
    head = pg.inner_text(".agent-page .meta")
    assert "A ai" in head and "located-worked" in head and "started per item by its lease" in head, head
    assert "steps/03-work.yaml:" in pg.inner_text("#its-definition")
    assert pg.eval_on_selector("#its-definition pre.code code", "c => c.classList.contains('hljs')")
    assert "work:" in pg.inner_text("#its-definition pre") and "prompts/work.md" in pg.inner_text("#its-definition pre")
    place = pg.inner_text("#its-place")
    assert re.search(r"working \d+ tickets?", place) and "holds" not in place, place
    assert pg.get_attribute("#its-place a:text-is('Show on Blocks')", "href").startswith("/diagram?view=blocks&around=block/work")
    assert pg.get_attribute("#its-place a.goal", "href") == "/goals?select=located-worked"
    assert [h for h in pg.eval_on_selector_all(".agent-page h2", "es => es.map((e) => e.textContent)")] == \
        ["Its prompt", "Its definition", "Its place", "What it did"]
    assert not pg.errors, pg.errors
    pg.goto(f"{tf}/agent/nope")
    pg.wait_for_selector(".no-agent")
    assert "no agent nope" in pg.inner_text(".no-agent")
    assert pg.get_attribute(".no-agent a", "href") == "/agents"
    pg.close()


def test_an_implied_rules_page_shows_its_law_as_blocks_does(browser, tf, tf_band):
    pg = opened(browser, tf, "keep-located-worked")                      # an ideal relay: its threshold, no band
    assert first_h2(pg) == "Its law" and "threshold" in pg.inner_text("#what-it-is dl")
    assert "releases at" not in pg.inner_text("#what-it-is")
    pg.close()
    tf = tf_band                                                          # its goal with a tolerance: a relay with a band
    pg = opened(browser, tf, "keep-located-worked")
    assert first_h2(pg) == "Its law"
    assert pg.eval_on_selector_all("#what-it-is math", "ms => ms.length") >= 1
    law = pg.inner_text("#what-it-is")
    assert "releases at" in law and "hysteresis" in law, law
    says = pg.inner_text("#what-it-is .law-says")
    assert pg.get_attribute("#what-it-is .implied-by a", "href") == "/agent/work"
    assert "implied by work" in pg.inner_text("#what-it-is .implied-by")
    assert "not written: ergostat put it in front of work" in pg.inner_text("#its-definition")
    assert not pg.errors, pg.errors
    pg.goto(f"{tf}/diagram?view=blocks&open=*")                           # the Blocks panel of the same block
    pg.wait_for_function("() => S.graph?.nodes?.some((n) => n.id === 'blk:keep-located-worked')", timeout=60000)
    pg.evaluate("() => { openBlock(S.graph.nodes.find((n) => n.id === 'blk:keep-located-worked')); }")
    pg.wait_for_selector("#detail p.what")
    assert pg.inner_text("#detail p.what") == says
    pg.close()


def test_a_programs_page_names_ergostats_own_module(browser, tf):
    fixer = next(n for n in agents(tf) if n.endswith("fixer"))
    pg = opened(browser, tf, fixer)
    assert first_h2(pg) == "Its program"
    text = pg.inner_text(".agent-page")
    assert "ergostat's own: ergostat." in text, text
    assert not re.search(NOT_SHOWN, text) and sys.executable not in text
    assert not pg.errors, pg.errors
    pg.close()


def test_a_person_is_asked_and_a_decision_says_how_it_decides(browser, tf, df):
    person = next(n for n, a in agents(tf).items() if a["rung"] == 0)
    pg = opened(browser, tf, person)
    assert first_h2(pg) == "What they are asked"
    assert pg.eval_on_selector_all("#what-it-is .md", "es => es.length") == 1   # the ask, as Markdown
    assert re.search(r"Nothing is asked of them now|Asked now", pg.inner_text("#what-it-is"))
    assert not pg.errors, pg.errors
    pg.close()
    pg = opened(browser, df, "page-picker")
    assert first_h2(pg) == "How it decides"
    said = pg.inner_text("#what-it-is")
    assert pg.eval_on_selector_all("#what-it-is ol.decisions li", "ls => ls.length") or \
        "no decisions in the window" in said, said
    assert "What it said in the window" in said and "Commands acted on" in said, said   # labelled apart
    assert re.search(r"out: block\.doc-writer\s*\n?\s*\d+", said), said                # counted, not an answer set
    assert not pg.query_selector("#what-it-is ul.answers"), said
    assert not pg.errors, pg.errors
    pg.close()


@pytest.fixture(scope="module")
def at(tmp_path_factory):
    proc, url = serve(tmp_path_factory.mktemp("at"), "alert-triage")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


def test_a_narrow_ais_page_shows_its_prompt_rendered_and_its_specification_rows(browser, at):
    pg = opened(browser, at, "triage")
    assert first_h2(pg) == "Its specification"
    assert "N narrow-ai" in pg.inner_text(".agent-page .meta")
    pg.wait_for_selector("#what-it-is .md")
    assert "prompts/triage.md" in pg.inner_text("#what-it-is") and pg.inner_text("#what-it-is .md").strip()
    heads = pg.eval_on_selector_all("#what-it-is h3", "es => es.map((e) => e.textContent)")
    assert heads[:3] == ["what it works", "what it may move", "what it costs and how long"], heads
    rows = pg.inner_text("#what-it-is")
    assert "takes" in rows and "dismissed" in rows and "flow.alerts-dismissed" in rows and "timeout" in rows, rows
    assert not pg.errors, pg.errors
    pg.close()


def test_a_decisions_page_counts_its_declared_answers_and_flags_the_rest(browser, tmp_path, monkeypatch):
    from ergostat import model as mdl
    from ergostat.store import Project
    from tests.test_agent_means import MODEL, seed_approver
    d = tmp_path / "approver"
    (d / "bin").mkdir(parents=True)
    (d / "bin" / "x.py").write_text("print('x')\n")
    (d / "ergostat.yaml").write_text(MODEL)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    seed_approver(Project(mdl.load(d)))                           # the record the page reads, before it starts
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        pg = opened(browser, url, "approve")
        assert first_h2(pg) == "How it decides"
        pg.wait_for_selector("#what-it-is ul.answers")
        rows = pg.eval_on_selector_all("#what-it-is ul.answers li", "ls => ls.map((l) => [l.className, l.textContent])")
        assert ["answer", "approved (2)"] in rows and ["answer", "denied (1)"] in rows, rows
        assert ["answer never", "deferred never given"] in rows, rows                     # declared, never given
        assert ["answer other", "other: a dead letter (1)"] in rows, rows                 # outside them: flagged
        assert ["answer other", "other: given back to new (1)"] in rows, rows
        assert any(c == "answer unattributed" and t.startswith("unattributed: 1 request") for c, t in rows), rows
        assert not pg.errors, pg.errors
        pg.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)


NO_SPEC = [   # what is shown for a text, the reference to a SPEC section only taken out, never another word or a line
    ("($ERGOSTAT_ITEM: ergostat's SPEC §9.5), so no two runs", "($ERGOSTAT_ITEM), so no two runs"),
    ("# ergostat's built-in one (SPEC §12e, the template `modelling`), as", "# ergostat's built-in one (the template `modelling`), as"),
    ("a sensor may record any event, SPEC §9.3 limits only runs started by", "a sensor may record any event, limits only runs started by"),
    ("    use: modelling   # its work (SPEC §12e)\n    every: 1h", "    use: modelling   # its work\n    every: 1h"),
    ("held to what the owner meant (ergostat's SPEC §12i). A", "held to what the owner meant. A"),
    ("laws (SPEC §12b:\n  a rule", "laws (\n  a rule"),
    ("my notes (SPEC §12h follow-ups)", "my notes (follow-ups)"),
    ("(`intent.yaml`, SPEC §12i, §12g)", "(`intent.yaml`)"),
    ("def f(x):\n    return g()  # (see SPEC §4f)\n", "def f(x):\n    return g()  #\n"),
    ("no reference (SPEC), f()", "no reference (SPEC), f()"),
]


def test_only_the_spec_reference_is_taken_out_of_what_is_shown(browser, tf):
    pg = opened(browser, tf, "work")
    got = pg.evaluate("(cases) => cases.map(([t]) => [noSpec(t), specRefs(t)])", NO_SPEC)
    assert [g for g, _ in got] == [want for _, want in NO_SPEC]
    assert [n for _, n in got] == [1, 1, 1, 1, 1, 1, 1, 1, 1, 0]
    pg.close()


def test_a_file_shown_keeps_its_own_words_and_says_what_was_left_out(browser, tmp_path):
    proc, url = serve(tmp_path, "the-job")
    try:
        name = next(n for n in agents(url) if n.endswith("mention-triager"))     # a program: python3 bin/prepare.py
        pg = opened(browser, url, name)
        pg.evaluate("() => document.querySelectorAll('.agent-page details').forEach((d) => { d.open = true; })")
        box = pg.locator("details.agent-file:has(summary:text-is('bin/prepare.py'))")
        shown = box.locator("pre").inner_text()
        assert "($ERGOSTAT_ITEM), so no two runs prepare one item" in shown, shown
        assert "SPEC §" not in shown
        assert re.search(r"\d+ references? to ergostat's specification left out", box.inner_text())
        pg.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.mark.parametrize("name", ["work", "keep-located-worked", "approve"])
def test_at_phone_width_the_page_does_not_scroll_sideways(browser, tf, name):
    pg = opened(browser, tf, name, width=390)
    pg.evaluate("() => document.querySelectorAll('.agent-page details').forEach((d) => { d.open = true; })")   # its code shown
    pg.wait_for_timeout(600)
    assert pg.evaluate("() => document.scrollingElement.scrollWidth") <= 390
    page = pg.evaluate("() => { const p = document.querySelector('.agent-page'); return [p.scrollWidth, p.clientWidth]; }")
    assert page[0] <= page[1], page                                      # its code scrolls in its own box, not the page
    assert not pg.errors, pg.errors
    pg.close()


def test_a_row_on_agents_goes_to_its_page_and_the_panel_links_it(browser, tf):
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    pg.goto(f"{tf}/agents")
    pg.click("tr.click:has(b:text-is('work')) td:nth-child(3)")
    pg.wait_for_function("() => location.pathname === '/agent/work'")
    pg.wait_for_selector(".agent-page h2:text-is('Its prompt')")
    assert pg.get_attribute("#nav a[aria-current=page]", "href").startswith("/agents")
    pg.evaluate("() => { openAgent('work'); }")
    pg.wait_for_selector("#detail a.agent-page-link")
    assert pg.get_attribute("#detail a.agent-page-link", "href") == "/agent/work"
    pg.close()


@pytest.mark.slow
@pytest.mark.parametrize("example", EXAMPLES)
def test_every_agent_of_every_example_opens(browser, tmp_path, example):
    """The render sweep: each agent's page opened in turn, with no console error, its first section its rung's, and
    none of an interpreter's, a temporary folder's or a SPEC section's text."""
    proc, url = serve(tmp_path, example)
    try:
        listed = agents(url)
        pg = browser.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(f"{url}/agents")
        pg.wait_for_selector(".page h1")
        folder = str(tmp_path.resolve())
        for name, a in listed.items():
            pg.evaluate("(n) => navigate(`/agent/${encodeURIComponent(n)}`)", name)
            pg.wait_for_function("""(n) => document.querySelector('.agent-page h1')?.textContent === n
                && document.querySelector('.agent-page section h2')""", arg=name, timeout=30000)
            assert first_h2(pg) == SECTION[a["rung"]], (example, name)
            text = pg.eval_on_selector(".agent-page", "e => e.textContent")     # closed disclosures too
            bad = re.search(f"{NOT_SHOWN}|{re.escape(folder)}", text)
            assert not bad, (example, name, text[max(0, bad.start() - 80):bad.end() + 80])
            assert not errors, (example, name, errors)
        pg.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
