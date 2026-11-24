"""Story H5 by keyboard only (R9 piece 6): find the goal that is off and read why, without a mouse, in Dynamics and in
Blocks. From page load, on a seeded project whose one goal (short-backlog) is off inside the closed system desk: Tab
to the diagram, arrow to desk, I into it, arrow to the goal's gap (Dynamics' excess, Blocks' Σ), Enter opens its panel
and its first line is read from the accessibility tree, Escape gives the focus back; then Shift+Tab to the nav, Enter
on Goals, Tab to its first row's name. After every key the focus is on screen and is the kind of thing the step
expects; the run is under 40 keys. It skips where tests/test_diagram_rendering.py does (no Playwright, no Chromium)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import urllib.request

import pytest

try:                                   # skipped as tests/test_diagram_rendering.py is, but at the test, so the file collects
    from tests.test_diagram_rendering import IN_SVG, READY, browser, drawn, free_port, goal_named  # noqa: F401 (a fixture)
    from tests.test_diagram_rendering import playwright as pw
except pytest.skip.Exception as e:
    WHY = str(e)

    @pytest.fixture
    def browser():
        pytest.skip(WHY)

KEYS_MOST = 40
# the focused element: its accessible name (aria-label, else its text), and whether it has a box on the screen
FOCUS = ("() => { const a = document.activeElement, r = a.getBoundingClientRect(); return { body: a === document.body, "
         "name: (a.getAttribute('aria-label') || a.textContent || '').trim().replace(/\\s+/g, ' '), "
         "seen: r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth }; }")
# per view: the system's name, the first part within it, the gap's name, the panel's first line
WANT = {"view=dynamics": (r"^system desk\b", r"^disturbance arriving\b", r"^auxiliary (excess|gap) backlog\b",
                          r"- text: (Excess|Gap)"),
        "view=blocks": (r"^block desk\b", r"^input r ?short-backlog\b", r"^sum Σ short-backlog\b", r"- text: summing junction")}


@pytest.mark.parametrize("view", list(WANT))
def test_story_h5_the_off_goal_found_and_read_by_keyboard_alone(browser, tmp_path, monkeypatch, view):  # noqa: F811
    system, first, gap, first_line = WANT[view]
    d, port = goal_named(tmp_path, monkeypatch, True), free_port()   # short-backlog off, inside the closed system desk
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url, went = f"http://127.0.0.1:{port}", []
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1500, "height": 1000})

        def key(k, name, until=None, most=1):
            """Press k (up to ``most`` times, until the focus's name matches ``name``); each time, the focus is seen."""
            for _ in range(most):
                pg.keyboard.press(k)
                if until:
                    pg.wait_for_function(until, timeout=60000)
                on = pg.evaluate(FOCUS)
                went.append((k, on["name"][:50]))
                assert on["seen"] and not on["body"], (view, went, "the focus is not on screen", on)
                if re.search(name, on["name"]):
                    return
            raise AssertionError((view, went, f"never reached {name}"))

        drawn(pg, url, view, 1)
        key("Tab", system, most=30)                      # into the diagram: its one tab stop, the first part (desk)
        if not re.search(system, pg.evaluate(FOCUS)["name"]):
            key("Shift+ArrowRight", system, most=4)
        key("i", first, until=f"() => S.here === 'desk' && ({READY})() && ({IN_SVG})(document.activeElement)")
        if view == "view=dynamics":                      # the disturbance, along its pipe to the stock, its connector, the gap
            key("ArrowRight", r"^stock backlog\b")
            key("ArrowDown", r"^connector line from backlog to short-backlog\b")
        key("ArrowRight", gap)                           # (Blocks: the reference, along the signal to Σ)
        key("Enter", ".", until="() => !document.querySelector('#detail').hidden && document.activeElement?.closest('#detail')")
        said = pg.locator("#detail").aria_snapshot().splitlines()   # a landmark (Q75), then the panel's lines
        assert len(said) > 1 and said[0].startswith("- complementary") and re.fullmatch(first_line, said[1].strip()), said[:6]
        assert "short-backlog" in "\n".join(said), (view, said[:12])
        key("Escape", gap, until="() => document.querySelector('#detail').hidden")
        key("Shift+Tab", r"^Goals$", most=20)            # back to the nav
        key("Enter", r"^Goals$", until="() => location.pathname === '/goals' && document.querySelector('tr.click') && "
                                       "document.querySelector('#nav [aria-current=page]')?.textContent === 'Goals'")   # (Q75)
        key("Tab", r"short-backlog", most=10)            # on to the first row's name
        assert pg.evaluate("() => document.activeElement.matches('tr.click:first-child td:first-child button.name')"), went
        assert len(went) < KEYS_MOST, (view, len(went), went)
        pg.close()
    except pw.TimeoutError as e:
        raise AssertionError((view, went)) from e
    finally:
        proc.terminate()
        proc.wait(10)
