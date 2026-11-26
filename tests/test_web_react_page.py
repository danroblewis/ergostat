"""The page (the React app in ergostat/web/ui, built into static/app) is served at / and at every page path, with the
run's token for its writes; the pages removed (Model, Check, Guide) and the old /ui prefix are no page any more."""

from __future__ import annotations

import re
import urllib.error
import urllib.request

import pytest

from ergostat import web
from ergostat.web import server as ws


@pytest.fixture
def url(project):
    server, url = web.serve(project, 0)
    yield url
    server.shutdown()
    server.server_close()


def get(url: str) -> tuple[int, str, dict]:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


@pytest.mark.skipif(not (ws.STATIC / "app" / "index.html").is_file(), reason="the React page is not built")
@pytest.mark.parametrize("path", ["/", "/dashboard", "/goals", "/item/a%2Fb", "/diagram?view=blocks", "/agent/x",
                                  "/items/ticket", "/record", "/loops"])
def test_the_page_is_served_with_the_token_at_every_page_path(url, path):
    code, body, _ = get(url + path)
    assert code == 200
    assert re.search(r'name="ergostat-token" content="[^"]+"', body)
    assert '<div id="root"></div>' in body and "/static/app/assets/" in body
    assert "?v=" not in body        # its files are named by their hash; a ?v= would load its entry twice


@pytest.mark.parametrize("path", ["/static/index.html", "/static/util.js", "/static/style.css"])
def test_the_old_pages_files_are_gone(url, path):
    assert get(url + path)[0] == 404


@pytest.mark.parametrize("path", ["/ui", "/ui/goals", "/model", "/check", "/guide", "/fit"])
def test_the_pages_removed_are_addresses_the_model_may_name(url, path):
    code, body, _ = get(url + path)            # the page, which says nothing is there unless the model names it
    assert code == 200 and 'name="ergostat-token"' in body


@pytest.mark.parametrize("path", ["/api/projects", "/api/coherence", "/api/exercised", "/api/guide", "/api/fit"])
def test_the_answers_only_the_removed_pages_read_are_gone(url, path):
    assert get(url + path)[0] == 404


@pytest.mark.skipif(not (ws.STATIC / "app" / "index.html").is_file(), reason="the React page is not built")
def test_the_apps_files_are_kept_for_good_and_a_markdown_file_is_drawn_with_its_styles(url, project):
    _, body, _ = get(url + "/")
    asset = re.search(r'src="(/static/app/assets/[^"]+\.js)"', body).group(1)
    code, _, headers = get(url + asset)
    assert code == 200 and headers.get("Cache-Control") == ws.FOREVER
    (project.model.path.parent / "notes.md").write_text("# Notes\n\nSome *words*.\n")
    req = urllib.request.Request(url + "/api/file/notes.md", headers={"Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=10) as r:
        page = r.read().decode()
    assert re.search(r'<link rel="stylesheet" href="/static/app/assets/[^"]+\.css">', page)
    assert "/static/marked.min.js?v=" in page and "/static/highlight.min.js?v=" in page
