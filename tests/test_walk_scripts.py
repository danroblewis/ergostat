"""scripts/demo_up.py starts one demo left running and stops it; scripts/walk.py walks a page in Chromium from a JSON
list of steps (dev/records/research-design-queues-walk-and-demo-scripts.md). The browser tests need Playwright
(``uv run --with playwright==1.63.0``), like the four browser files."""

from __future__ import annotations

import functools
import importlib.util
import json
import os
import subprocess
import sys
import threading
import types
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.ports import free_port

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def script(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_up_refuses_unknown_and_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEMO_UP_STATE", str(tmp_path / "state"))
    up = script("demo_up")
    copied = []
    monkeypatch.setattr(up, "fresh_copy", lambda d: copied.append(d) or tmp_path)
    for bad in ("no-such-demo", "..", "../examples/the-job", "the-job/../big", "/tmp", str(ROOT / "examples" / "the-job"),
                "remote-pair", "README.md", ".", "", "the-job/", "the-job\n"):
        for what in ("stop", "start"):
            with pytest.raises(SystemExit) as e:
                up.main([what, bad])
            assert "refused" in str(e.value), (what, bad)
    assert copied == [] and not (tmp_path / "state").exists()        # nothing copied, no state written
    assert up.demo_dir("the-job") == up.DEMOS / "the-job"            # (and a real one is taken)
    for name in ("the-job", "ticket-factory", "image-squeeze", "roadmap", "software-factory", "big"):
        assert (up.demo_dir(name) / "ergostat.yaml").is_file()
    with pytest.raises(SystemExit, match="refused: port"):
        up.main(["start", "the-job", "--port", "8790"])
    assert copied == []


@pytest.mark.slow
def test_demo_up_starts_and_stops_the_job(tmp_path):
    env = {**os.environ, "DEMO_UP_STATE": str(tmp_path / "state")}
    up = lambda *a: subprocess.run([sys.executable, str(SCRIPTS / "demo_up.py"), *a], capture_output=True,  # noqa: E731
                                   text=True, timeout=180, env=env, cwd=ROOT)
    port = free_port()
    r = up("start", "the-job", "--port", str(port))
    try:
        assert r.returncode == 0, r.stdout + r.stderr
        got = json.loads(r.stdout.strip().splitlines()[-1])
        assert set(got) == {"demo", "url", "copy", "log"} and got["demo"] == "the-job"
        assert got["url"].endswith(f":{port}") and got["copy"].startswith("/tmp/")
        assert Path(got["copy"], "ergostat.yaml").is_file() and Path(got["copy"]) != ROOT / "examples" / "the-job"
        with urllib.request.urlopen(f"{got['url']}/api/status", timeout=30) as resp:
            assert resp.status == 200 and json.loads(resp.read())
        again = up("start", "the-job", "--port", str(free_port()))
        assert again.returncode == 1 and "refused" in again.stderr and "already running" in again.stderr
    finally:
        s = up("stop", "the-job")
    assert s.returncode == 0, s.stdout + s.stderr
    with pytest.raises(OSError):
        urllib.request.urlopen(f"{got['url']}/api/status", timeout=5)
    assert up("stop", "the-job").returncode == 1                       # (stopped: nothing left to stop)


@pytest.mark.slow
@pytest.mark.parametrize("demo", ["ticket-factory", "image-squeeze", "roadmap", "software-factory", "big"])
def test_demo_up_starts_and_stops_each_named_demo(tmp_path, demo):
    env = {**os.environ, "DEMO_UP_STATE": str(tmp_path / "state")}
    up = lambda *a: subprocess.run([sys.executable, str(SCRIPTS / "demo_up.py"), *a], capture_output=True,  # noqa: E731
                                   text=True, timeout=180, env=env, cwd=ROOT)
    r = up("start", demo)
    try:
        assert r.returncode == 0, r.stdout + r.stderr
        url = json.loads(r.stdout.strip().splitlines()[-1])["url"]
        with urllib.request.urlopen(f"{url}/api/status", timeout=30) as resp:
            assert resp.status == 200
    finally:
        s = up("stop", demo)
    assert s.returncode == 0, s.stdout + s.stderr


PAGE = """<!doctype html><html><body>
<button id="b" onclick="document.getElementById('out').textContent = 'clicked'">go</button>
<p id="out">not yet</p><p id="hov" onmouseover="this.textContent = 'hovered'">hover me</p>
<input id="i" onkeydown="if (event.key === 'Enter') document.getElementById('typed').textContent = this.value">
<p id="typed"></p><p id="w"></p><p id="mode"></p><p id="late"></p>
<div style="height: 3000px"></div><p id="bottom">the bottom</p>
<img src="http://127.0.0.1:1/missing.png">
<script>
  console.error("boom");
  const w = () => document.getElementById('w').textContent = 'width ' + innerWidth;
  w(); addEventListener('resize', w);
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change',
    (e) => document.getElementById('mode').textContent = e.matches ? 'dark' : 'light');
  setTimeout(() => document.getElementById('late').innerHTML = '<b id="arrived">arrived</b>', 300);
</script></body></html>"""


@pytest.fixture
def page_url(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(PAGE)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
    server.shutdown()
    server.server_close()


def walk(*args, steps) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "walk.py"), json.dumps(steps), *args], capture_output=True,
                          text=True, timeout=120, cwd=ROOT)


def test_walk_runs_steps_against_a_local_page(tmp_path, page_url):
    pytest.importorskip("playwright.sync_api")
    shots = tmp_path / "shots"
    shots.mkdir()
    steps = [{"goto": page_url}, {"wait": "#arrived"}, {"wait": 50}, {"size": [1000, 700]}, {"dark": True},
             {"click": "#b"}, {"hover": "#hov"}, {"fill": ["#i", "hello"]}, {"press": ["#i", "Enter"]},
             {"press": "Tab"}, {"scroll": [0, 400]}, {"scroll": "#bottom"}, {"shot": "page-1.png"},
             {"shot": "whole.png", "full": True}, {"text": "body"}]
    r = walk("--shots", str(shots), steps=steps)
    assert r.returncode == 0, r.stdout + r.stderr
    assert sum(ln.startswith("ok   ") for ln in r.stdout.splitlines()) == len(steps) and "FAIL" not in r.stdout
    text = r.stdout.split("ok   15 text\n", 1)[1]
    for said in ("clicked", "hovered", "hello", "width 1000", "dark", "arrived"):
        assert said in text, said
    assert sorted(p.name for p in shots.iterdir()) == ["page-1.png", "whole.png"]
    assert all(p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" for p in shots.iterdir())
    assert not any(p.suffix == ".png" for p in tmp_path.iterdir()) and not list(ROOT.glob("*.png"))
    assert "\n  console: boom\n" in r.stdout and "console errors: 2\n" in r.stdout    # (and the image's, Chromium's)
    assert "failed requests: 1\n  GET http://127.0.0.1:1/missing.png" in r.stdout


def test_walk_text_is_cut(tmp_path, page_url):
    pytest.importorskip("playwright.sync_api")
    (tmp_path / "site" / "long.html").write_text("<p>" + "x" * 9000 + "</p>")
    r = walk(steps=[{"goto": page_url.replace("index", "long")}, {"text": "p"}])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "x" * 6000 + "\n[... cut at 6000 of 9000 characters]" in r.stdout and "x" * 6001 not in r.stdout


def test_walk_refuses_bad_shot_names(tmp_path, capsys):
    w = script("walk")
    shots = tmp_path / "shots"
    shots.mkdir()
    for bad in ("../x.png", "a/b.png", "/tmp/x.png", "X.png", "x.jpg", ".x.png", "-x.png", "a" * 65 + ".png",
                "x.png/", "x.png\n", "", 3, None):
        assert w.main([json.dumps([{"shot": bad}]), "--shots", str(shots)]) == 2, bad
        assert "refused" in capsys.readouterr().err
    assert list(shots.iterdir()) == [] and list(tmp_path.iterdir()) == [shots]
    assert w.problems([{"shot": "a" * 64 + ".png"},{"shot": "x-1_2.b.png"}], shots) == []
    assert w.problems([{"shot": "x.png"}], None) == ["step 1: a shot needs --shots DIR"]
    assert w.main([json.dumps([{"shot": "x.png"}]), "--shots", str(tmp_path / "nope")]) == 2   # it must exist
    assert not (tmp_path / "nope").exists()
    assert w.main([json.dumps([{"jump": 1}])]) == 2 and w.main([json.dumps([{"click": "a", "hover": "b"}])]) == 2
    assert w.main(['{"goto": "x"}']) == 2


class FakeChromium:
    def __init__(self):
        self.launched: list[dict] = []

    def launch(self, **kw):
        self.launched.append(kw)
        page = types.SimpleNamespace(set_default_timeout=lambda t: None, on=lambda *a: None)
        return types.SimpleNamespace(new_page=lambda **kw: page, close=lambda: None)


def test_walk_proxy_only_off_loopback(monkeypatch):
    w = script("walk")
    assert w.launch_options({}) == {"args": ["--no-proxy-server"]}      # nothing set: no proxy for any host
    assert w.launch_options({"HTTP_PROXY": "http://p:1"}) == {"args": ["--no-proxy-server"]}
    got = w.launch_options({"HTTPS_PROXY": "http://egress.internal:3128"})
    assert got == {"proxy": {"server": "http://egress.internal:3128", "bypass": "127.0.0.1,localhost"}}
    got = w.launch_options({"https_proxy": "http://u:p%40@egress.internal:3128"})
    assert got["proxy"]["server"] == "http://egress.internal:3128" and got["proxy"]["username"] == "u"
    # and the walk launches Chromium with exactly these
    chromium = FakeChromium()
    pw = types.SimpleNamespace(chromium=chromium)

    class Ctx:
        def __enter__(self):
            return pw

        def __exit__(self, *a):
            return False
    monkeypatch.setitem(sys.modules, "playwright.sync_api", types.SimpleNamespace(sync_playwright=Ctx))
    assert w.walk([], None, (1440, 900), 1000, {"HTTPS_PROXY": "http://egress.internal:3128"}) == 0
    assert w.walk([], None, (1440, 900), 1000, {}) == 0
    assert chromium.launched == [{"proxy": {"server": "http://egress.internal:3128", "bypass": "127.0.0.1,localhost"}},
                                 {"args": ["--no-proxy-server"]}]


def test_walk_exit_code_on_failed_step(page_url):
    pytest.importorskip("playwright.sync_api")
    r = walk("--timeout", "1500", steps=[{"goto": page_url}, {"click": "#missing"}, {"click": "#b"}, {"text": "#out"}])
    assert r.returncode == 2, r.stdout + r.stderr
    assert "FAIL 2 click: TimeoutError" in r.stdout and "ok   3 click" in r.stdout          # it went on
    assert "ok   4 text\nclicked" in r.stdout
    assert walk(steps=[{"goto": page_url}, {"text": "#out"}]).returncode == 0
