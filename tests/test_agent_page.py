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
EXAMPLES = sorted(p.parent.name for p in (ROOT / "examples").glob("*/ergostat.yaml"))


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
    assert not pg.errors, pg.errors
    pg.close()


@pytest.mark.parametrize("name", ["work", "keep-located-worked", "approve"])
def test_at_phone_width_the_page_does_not_scroll_sideways(browser, tf, name):
    pg = opened(browser, tf, name, width=390)
    pg.wait_for_timeout(600)
    assert pg.evaluate("() => document.scrollingElement.scrollWidth") <= 390
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
