"""Acceptance: a refresh that changed nothing changes nothing on the page, and one that did changes only what
differs. An item with a long history, a transcript (Markdown, highlighted code, tool calls that open) and a
page scrolled to its middle: across refreshes with nothing new, no DOM mutation at all and the scroll where it
was; with a new event, one row added, the reader's place kept, and what they opened still open. The same for
the Items page and the Record.

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_page_refresh.py -v -s
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.request
import zlib
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = "image-squeeze"
SPEED = 4                      # every poll's wait shortened this much: the item page asks every second
ITEM = "session/s1"
INIT = f"window.ERGOSTAT_POLL_SPEED = {SPEED};"

# every change to the page under <body>, kept in the page: what was added and removed, and where
OBSERVE = """() => {
  window.__mo?.disconnect();
  window.__muts = [];
  window.__mo = new MutationObserver((rs) => { for (const r of rs) window.__muts.push({
    type: r.type, target: r.target.nodeName, attr: r.attributeName,
    added: [...r.addedNodes].map((n) => n.nodeName), removed: [...r.removedNodes].map((n) => n.nodeName) }); });
  window.__mo.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
}"""


def free_port() -> int:
    """One of 8791-8799 (8790 is the owner's)."""
    for port in range(8791, 8800):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    pytest.skip("no free port in 8791-8799")


def transcript() -> str:
    """A Claude Code session: prompts, replies in Markdown with code, tool calls with what came back."""
    lines, t = [], "2026-11-18T10:00:00Z"
    for i in range(14):
        lines.append({"type": "user", "uuid": f"u{i}", "timestamp": t,
                      "message": {"role": "user", "content": f"Step {i}: squeeze the **PNG** fixtures and say what changed."}})
        lines.append({"type": "assistant", "uuid": f"a{i}", "timestamp": t, "message": {"role": "assistant", "content": [
            {"type": "text", "text": f"## Step {i}\n\nI read `squeeze.py` and ran the tests.\n\n"
                                     "```python\ndef squeeze(img, q=80):\n    return img.convert('P', palette=q)\n```\n\n"
                                     "- the ratio went from 0.61 to 0.58\n- no test failed\n"},
            {"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {"command": f"pytest -q tests/test_{i}.py"}}]}})
        lines.append({"type": "user", "uuid": f"r{i}", "timestamp": t, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "content": f"{i + 3} passed in 0.4s"}]}})
    return "\n".join(json.dumps(x) for x in lines) + "\n"


def png(w: int = 480, hgt: int = 240) -> bytes:
    """An image to show in a field: a page re-made each refresh loaded it again, with no height meanwhile."""
    raw = b"".join(b"\0" + bytes(v for x in range(w) for v in (x * 255 // w, y * 255 // hgt, 160)) for y in range(hgt))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))   # noqa: E731
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, hgt, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def add_events(d: Path, home: Path, code: str) -> None:
    pre = f"""
import time
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
p = Project(mdl.load(Path({str(d)!r})))
"""
    subprocess.run([sys.executable, "-c", pre + code], env={**os.environ, "ERGOSTAT_HOME": str(home)}, check=True,
                   capture_output=True)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp(EXAMPLE) / EXAMPLE
    shutil.copytree(ROOT / "examples" / EXAMPLE, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    home = d.parent / "home"
    (d / "sessions").mkdir()
    (d / "sessions" / "s1.jsonl").write_text(transcript())
    (d / "sessions" / "preview.png").write_bytes(png())
    add_events(d, home, f"""
t = time.time() - 4000
p.events.add("session.started", item={ITEM!r}, at=t, data={{"role": "developer", "model": "opus",
             "transcript": "file:sessions/s1.jsonl", "preview": "file:sessions/preview.png"}})
for i in range(1, 61):
    p.events.add("session.progress", item={ITEM!r}, data={{"turns": i, "cost_usd": round(i * 0.07, 2)}}, at=t + i * 50)
for i in range(1, 41):
    p.events.add("hypothesis.proposed", item=f"hypothesis/{{i}}", data={{"title": f"idea {{i}}", "why": "x" * 300}}, at=t + i * 60)
""")
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(home)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            urllib.request.urlopen(url + "/api/status", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("the page never answered")
    yield {"url": url, "dir": d, "home": home}
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:                        # no Chromium here
            pytest.skip(f"no Chromium to drive: {e}")
        yield b
        b.close()


def settle(site, path: str) -> None:
    """Until the answer stops changing (the transcript's lines being recorded, say)."""
    last = None
    for _ in range(40):
        got = urllib.request.urlopen(f"{site['url']}/api/{path}", timeout=5).read()
        if got == last:
            return
        last = got
        time.sleep(1)


def open_page(browser, site, route: str, asks: str):
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    pg.add_init_script(INIT)
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    asked: list[str] = []
    pg.on("requestfinished", lambda r: asked.append(r.url) if f"/api/{asks}" in r.url else None)
    pg.goto(f"{site['url']}/{route}")
    pg.wait_for_timeout(2500)
    return pg, errors, asked


def wait_refreshes(pg, asked: list[str], n: int) -> None:
    """``n`` more answers to the page's own question, and the time to draw each."""
    start = len(asked)
    for _ in range(200):
        if len(asked) - start >= n:
            break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(400)


SCROLLER = "document.querySelector('.page')"


def place(pg) -> dict:
    """Where the reader is: the scroll, and the row or block at the middle of the view and where it sits."""
    return pg.evaluate(f"""() => {{
      const sc = {SCROLLER}, r = sc.getBoundingClientRect();
      const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      window.__anchor = el;
      return {{ scrollTop: sc.scrollTop, scrollY: window.scrollY, anchorTop: el.getBoundingClientRect().top }};
    }}""")


def anchor_now(pg) -> dict:
    return pg.evaluate(f"""() => ({{ connected: window.__anchor.isConnected, top: window.__anchor.getBoundingClientRect().top,
                                     scrollTop: {SCROLLER}.scrollTop, scrollY: window.scrollY }})""")


def muts(pg) -> list[dict]:
    return pg.evaluate("window.__muts")


def added(ms: list[dict], name: str) -> int:
    return sum(m["added"].count(name) for m in ms)


def removed(ms: list[dict], name: str) -> int:
    return sum(m["removed"].count(name) for m in ms)


def test_an_item_page_left_open_changes_nothing_until_something_changes(browser, site):
    settle(site, f"items/{ITEM.replace('/', '%2F')}")
    pg, errors, asked = open_page(browser, site, f"item/{ITEM.replace('/', '%2F')}", f"items/{ITEM.replace('/', '%2F')}")
    pg.wait_for_selector(".convo .turn.tool", timeout=10000)
    # the reader opens a tool call and a field's history, selects a line of a reply, and scrolls to the middle
    pg.evaluate("""() => { const t = document.querySelectorAll('.convo details.tool')[5]; t.open = true;
                           document.querySelector('details.history').open = true;
                           const p = document.querySelectorAll('.convo .md li')[8]; const r = document.createRange();
                           r.selectNodeContents(p); getSelection().removeAllRanges(); getSelection().addRange(r); }""")
    pg.evaluate("() => { document.querySelector('img.pic').__was = true; }")
    pg.evaluate(f"() => {{ const sc = {SCROLLER}; sc.scrollTop = (sc.scrollHeight - sc.clientHeight) / 2; }}")
    pg.wait_for_timeout(300)
    before = place(pg)
    assert before["scrollTop"] > 500, "the page is long enough to scroll"
    pg.evaluate(OBSERVE)
    wait_refreshes(pg, asked, 4)
    after = anchor_now(pg)
    ms = muts(pg)
    still = pg.evaluate("""() => ({ tool: document.querySelectorAll('.convo details.tool')[5].open,
                                    history: document.querySelector('details.history').open, sel: String(getSelection()),
                                    img: document.querySelector('img.pic').__was })""")
    print(f"\nitem page, 4 refreshes with nothing new: {len(ms)} mutations, scrollTop {before['scrollTop']} -> {after['scrollTop']}")
    assert ms == [], ms[:10]
    assert after["scrollTop"] == before["scrollTop"] and after["scrollY"] == before["scrollY"]
    assert still["tool"] and still["history"] and "0.58" in still["sel"] and still["img"], still

    # a new event: the reader is in the middle of the events table, below where its newest row goes
    pg.evaluate(f"""() => {{ const sc = {SCROLLER};
      const rows = [...document.querySelectorAll('table tr')].filter((r) => r.__key && r.cells.length === 4
                                                                    && r.closest('table').querySelector('th')?.textContent === 'when');
      sc.scrollTop += rows[30].getBoundingClientRect().top - sc.getBoundingClientRect().top - sc.clientHeight / 2; }}""")
    pg.wait_for_timeout(300)
    before = place(pg)
    pg.evaluate(OBSERVE)
    add_events(site["dir"], site["home"], f'p.events.add("session.ping", item={ITEM!r}, data={{}})')
    for _ in range(100):
        if pg.evaluate("() => document.body.innerText.includes('Events 62')"):
            break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(500)
    after = anchor_now(pg)
    ms = muts(pg)
    still = pg.evaluate("""() => ({ tool: document.querySelectorAll('.convo details.tool')[5].open,
                                    history: document.querySelector('details.history').open })""")
    print(f"item page, one new event: {len(ms)} mutations, {added(ms, 'TR')} rows added, {removed(ms, 'TR')} removed, "
          f"anchor {before['anchorTop']:.0f} -> {after['top']:.0f}px, scrollTop {before['scrollTop']} -> {after['scrollTop']}")
    pg.close()
    assert not errors, errors
    assert added(ms, "TR") == 1 and removed(ms, "TR") <= 1, ms
    assert not any(n in ("TABLE", "DETAILS", "PRE", "DIV") for m in ms for n in m["added"] + m["removed"]), ms
    assert after["connected"] and abs(after["top"] - before["anchorTop"]) <= 1, (before, after)
    assert after["scrollTop"] > before["scrollTop"], "the row above was made room for"
    assert still["tool"] and still["history"]


def test_the_items_page_changes_only_the_new_row(browser, site):
    pg, errors, asked = open_page(browser, site, "items", "items?")
    pg.wait_for_selector("table.items tr", timeout=10000)
    pg.wait_for_timeout(1500)
    pg.evaluate(f"() => {{ const sc = {SCROLLER}; sc.scrollTop = (sc.scrollHeight - sc.clientHeight) / 2; }}")
    pg.wait_for_timeout(300)
    pg.evaluate("() => { for (const t of document.querySelectorAll('table.items')) t.__was = true; }")
    before = place(pg)
    assert before["scrollTop"] > 200
    pg.evaluate(OBSERVE)
    wait_refreshes(pg, asked, 3)
    after = anchor_now(pg)
    ms = muts(pg)
    print(f"\nitems page, 3 refreshes with nothing new: {len(ms)} mutations, scrollTop {before['scrollTop']} -> {after['scrollTop']}")
    assert ms == [], ms[:10]
    assert after["scrollTop"] == before["scrollTop"]

    before = place(pg)
    pg.evaluate(OBSERVE)
    add_events(site["dir"], site["home"], 'p.events.add("hypothesis.proposed", item="hypothesis/99", data={"title": "idea 99"})')
    for _ in range(100):
        if pg.evaluate("() => document.body.innerText.includes('hypothesis/99')"):
            break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(500)
    after = anchor_now(pg)
    ms = muts(pg)
    kept = pg.evaluate("() => [...document.querySelectorAll('table.items')].every((t) => t.__was)")
    print(f"items page, one new item: {len(ms)} mutations, {added(ms, 'TR')} rows added, {removed(ms, 'TR')} removed, "
          f"anchor {before['anchorTop']:.0f} -> {after['top']:.0f}px")
    pg.close()
    assert not errors, errors
    assert added(ms, "TR") == 1 and removed(ms, "TR") <= 1, ms
    assert kept, "the tables were kept, not drawn again"
    assert after["connected"] and abs(after["top"] - before["anchorTop"]) <= 1, (before, after)


def test_the_record_changes_only_the_new_row_and_keeps_what_is_open(browser, site):
    pg, errors, asked = open_page(browser, site, "record", "events")
    pg.wait_for_selector("td.data details", timeout=10000)
    pg.evaluate("() => { document.querySelectorAll('td.data details')[10].open = true; }")
    pg.evaluate(f"() => {{ const sc = {SCROLLER}; sc.scrollTop = (sc.scrollHeight - sc.clientHeight) / 2; }}")
    pg.wait_for_timeout(300)
    before = place(pg)
    pg.evaluate(OBSERVE)
    wait_refreshes(pg, asked, 3)
    ms = muts(pg)
    after = anchor_now(pg)
    print(f"\nrecord, 3 refreshes with nothing new: {len(ms)} mutations, scrollTop {before['scrollTop']} -> {after['scrollTop']}")
    assert ms == [], ms[:10]
    assert after["scrollTop"] == before["scrollTop"]

    before = place(pg)
    pg.evaluate(OBSERVE)
    add_events(site["dir"], site["home"], 'p.events.add("hypothesis.noted", item="hypothesis/7", data={"note": "z" * 200})')
    for _ in range(100):
        if pg.evaluate("() => document.body.innerText.includes('hypothesis.noted')"):
            break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(500)
    after = anchor_now(pg)
    ms = muts(pg)
    still = pg.evaluate("() => document.querySelectorAll('td.data details[open]').length")
    print(f"record, one new event: {len(ms)} mutations, {added(ms, 'TR')} rows added, {removed(ms, 'TR')} removed, "
          f"anchor {before['anchorTop']:.0f} -> {after['top']:.0f}px")
    pg.close()
    assert not errors, errors
    assert added(ms, "TR") == 1 and removed(ms, "TR") <= 1, ms
    assert still == 1, "the event the reader opened is still open"
    assert after["connected"] and abs(after["top"] - before["anchorTop"]) <= 1, (before, after)


@pytest.mark.parametrize("route,asks", [("loops", "loops"), ("agents", "agents"), ("diagram?view=process&by=events", "graph")])
def test_other_pages_left_open_change_nothing(browser, site, route, asks):
    pg, errors, asked = open_page(browser, site, route, asks)
    pg.wait_for_timeout(1500)
    if route.startswith("diagram"):                       # the process map drawn, its lines routed
        pg.wait_for_function("() => S.layout && !S.layout.routing && document.querySelectorAll('svg.canvas g.node').length > 0")
    pg.evaluate(OBSERVE)
    wait_refreshes(pg, asked, 3)
    ms = muts(pg)
    pg.close()
    print(f"\n{route}, 3 refreshes with nothing new: {len(ms)} mutations")
    assert not errors, errors
    assert ms == [], ms[:10]


def test_the_reader_is_kept_in_place_by_hand_where_the_browser_does_not(browser, site):
    """Without the browser's scroll anchoring (overflow-anchor: none, as in a browser without it), patch()
    measures the reader's place and keeps it."""
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    pg.add_init_script(INIT + " window.ERGOSTAT_ANCHOR_BY_HAND = true;")
    pg.add_init_script("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); "
                       "s.textContent = '* { overflow-anchor: none !important; }'; document.head.append(s); });")
    pg.goto(f"{site['url']}/record")
    pg.wait_for_selector("td.data details", timeout=10000)
    pg.evaluate(f"() => {{ const sc = {SCROLLER}; sc.scrollTop = (sc.scrollHeight - sc.clientHeight) / 2; }}")
    pg.wait_for_timeout(300)
    before = place(pg)
    add_events(site["dir"], site["home"], 'p.events.add("hypothesis.noted", item="hypothesis/8", data={"note": "anchored"})')
    for _ in range(100):
        if pg.evaluate("() => document.body.innerText.includes('anchored')"):
            break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(500)
    after = anchor_now(pg)
    pg.close()
    assert after["connected"] and abs(after["top"] - before["anchorTop"]) <= 1, (before, after)


def test_a_growing_transcript_gains_its_new_turns_and_keeps_what_is_open(browser, site):
    """A session still running: its transcript grows; the new turns are added below, nothing else redrawn."""
    pg, errors, asked = open_page(browser, site, f"item/{ITEM.replace('/', '%2F')}", f"items/{ITEM.replace('/', '%2F')}")
    pg.wait_for_selector(".convo .turn.tool", timeout=10000)
    pg.evaluate("() => { document.querySelectorAll('.convo details.tool')[3].open = true; }")
    pg.evaluate(f"() => {{ const sc = {SCROLLER}; sc.scrollTop = (sc.scrollHeight - sc.clientHeight) / 3; }}")
    pg.wait_for_timeout(300)
    before = place(pg)
    pg.evaluate(OBSERVE)
    more = [{"type": "user", "uuid": "u99", "timestamp": "2026-11-18T10:05:00Z", "message": {"role": "user", "content": "Step 99?"}},
            {"type": "assistant", "uuid": "a99", "timestamp": "2026-11-18T10:05:01Z",
             "message": {"role": "assistant", "content": [{"type": "text", "text": "Done: **all** squeezed."}]}}]
    with open(site["dir"] / "sessions" / "s1.jsonl", "a") as f:
        f.write("".join(json.dumps(x) + "\n" for x in more))
    for _ in range(150):
        if pg.evaluate("() => document.body.innerText.includes('all squeezed')"):
            break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(500)
    after = anchor_now(pg)
    ms = muts(pg)
    still = pg.evaluate("() => document.querySelectorAll('.convo details.tool')[3].open")
    turns = sum(1 for m in ms for n in m["added"] if n == "DIV" and m["target"] == "DIV")
    print(f"\ntranscript, two new lines: {len(ms)} mutations, {turns} turns added, "
          f"removed {sorted({n for m in ms for n in m['removed']})}, anchor {before['anchorTop']:.0f} -> {after['top']:.0f}px")
    pg.close()
    assert not errors, errors
    assert still, "the tool call the reader opened is still open"
    assert not any(n in ("DETAILS", "PRE", "TABLE") for m in ms for n in m["removed"]), ms
    assert turns >= 2, ms
    assert after["connected"] and abs(after["top"] - before["anchorTop"]) <= 1, (before, after)
