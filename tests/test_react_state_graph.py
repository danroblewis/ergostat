"""A projection's list page draws its states as the graph its items made (SPEC §5a, *The projection's page*): an arrow
for each move that happened, with how many times, none for one that never did; the arrivals as an entry; the
finishing states marked; a chip still filters the list.

    uv run --with playwright==1.63.0 python -m pytest -q tests/test_react_state_graph.py
"""

from __future__ import annotations

import time

import pytest

from ergostat import model as mdl
from ergostat import web
from ergostat.store import Project
from tests.test_react_pages import EXAMPLE, WAIT, browser, opened, project_with_items, settled  # noqa: F401

pytestmark = pytest.mark.skipif(not __import__("ergostat.web.server", fromlist=["STATIC"]).STATIC.joinpath(
    "app", "index.html").is_file(), reason="the React page is not built")

STATES = ["made", "checked", "refused", "superseded", "verified"]
CHANGE = """
  change:
    query: key.startswith('change/')
    fields:
      state:
        values: [made, checked, refused, superseded, verified]
    finished: [refused, superseded, verified]
    events:
""" + "".join(f"""      {s}:
        when: type == 'change.{s}'
        state: set('{s}')
""" for s in STATES[1:]) + """      other:
        when: true
"""


@pytest.fixture(scope="module")
def branched(tmp_path_factory):
    p = project_with_items(tmp_path_factory.mktemp("state-graph") / EXAMPLE)
    text = p.model.path.read_text()
    p.model.path.write_text(text.replace("projections:\n", "projections:\n" + CHANGE.lstrip("\n"), 1))
    p = Project(mdl.load(p.model.path.parent))
    now = time.time() - 600
    for i in range(10):
        p.events.add("change.made", item=f"change/{i}", at=now + i)
        p.events.add("change.checked", item=f"change/{i}", at=now + 100 + i)
        p.events.add("change.refused" if i < 3 else "change.superseded", item=f"change/{i}", at=now + 200 + i)
    p.events.add("change.made", item="change/x", at=now + 300)
    server, url = web.serve(p, 0)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


def test_the_list_header_draws_the_moves_made_not_the_declared_order(browser, branched):
    pg = opened(browser, branched + "/change")
    g = pg.locator(".projection-bar .state-graph")
    g.locator(".sg-edge").first.wait_for(timeout=WAIT)
    edges = {(e.get_attribute("data-from"), e.get_attribute("data-to")): int(e.get_attribute("data-n"))
             for e in g.locator(".sg-edge").all()}
    assert edges == {("made", "checked"): 10, ("checked", "refused"): 3, ("checked", "superseded"): 7}   # a branch: two
    assert g.locator(".sg-entry[data-to=made] text").text_content().strip() == "11"                        # the arrivals
    assert g.locator(".stbox.final[data-state=refused]").count() == 1                                # an end, marked
    assert g.locator(".stbox.final[data-state=superseded]").count() == 1
    assert g.locator(".sg-canvas .stbox.unreached[data-state=verified]").count() == 1                # never reached: in its place
    assert g.locator(".sg-edge[data-to=verified], .sg-edge[data-from=verified]").count() == 0      # with no arrow
    assert "not reached yet" not in g.inner_text()                                                    # no line of its own
    box = {s: g.locator(f".sg-canvas .stbox[data-state={s}]").bounding_box() for s in ("made", "checked", "refused", "superseded", "verified")}
    assert box["made"]["x"] < box["checked"]["x"] < box["refused"]["x"] == box["superseded"]["x"]    # left to right, side by side
    assert box["verified"]["x"] >= box["refused"]["x"]                                                # an end: the last column
    g.locator(".stbox[data-state=superseded]").click()                                              # a chip filters the list
    pg.wait_for_url("**state=superseded**", timeout=WAIT)
    assert settled(pg) == []
    pg.close()
    pg = opened(browser, branched + "/ticket")                       # every projection's header: the ticket's, in a line
    g = pg.locator(".projection-bar .state-graph")
    g.locator(".sg-edge").first.wait_for(timeout=WAIT)
    edges = {(e.get_attribute("data-from"), e.get_attribute("data-to")) for e in g.locator(".sg-edge").all()}
    assert edges == {("opened", "working"), ("working", "done")}
    pg.close()
