"""The React page (ergostat/web/ui, built into static/app) is served at /ui and every path under it, with the run's
token for its writes, as the old page is at its own paths; the old page is unchanged."""

from __future__ import annotations

import re
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


def get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.read().decode()


@pytest.mark.skipif(not (ws.STATIC / "app" / "index.html").is_file(), reason="the React page is not built")
@pytest.mark.parametrize("path", ["/ui", "/ui/", "/ui/goals", "/ui/item/a%2Fb", "/ui/diagram?view=blocks"])
def test_the_react_page_is_served_with_the_token_at_every_path_under_ui(url, path):
    code, body = get(url + path)
    assert code == 200
    assert re.search(r'name="ergostat-token" content="[^"]+"', body)
    assert '<div id="root"></div>' in body and "/static/app/assets/" in body
    assert "?v=" not in body        # its files are named by their hash; a ?v= would load its entry twice


def test_the_old_page_is_still_served_at_its_own_paths(url):
    code, body = get(url + "/goals")
    assert code == 200 and "/static/util.js" in body and 'id="root"' not in body
