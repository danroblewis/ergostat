"""Acceptance (dashboard-variables, done 1 and 3, on the real dashboard.js and panels.js, only the server faked): the
variables are shown at the top and kept in the address; changing one asks again only the panels that use it; a panel
repeated by a variable follows the values chosen. (Done 2, the values written in safely, is the server's:
tests/test_dashboard_variables.py.)

    uv run --with playwright==1.63.0 python -m pytest tests/test_dashboard_variables_page.py -v
"""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse

from tests.test_dashboard_page import ITEMS, answer, browser, context, encoded, opened_plain, site  # noqa: F401

HOSTILE = 'b"} or vector(1) #'


def text_panel(i, text, **more):
    return {"id": f"p{i}", "title": f"Panel {i}", "form": "line", "size": "s", "tall": False, "display": {},
            "queries": [{"id": "a", "source": "prom", "text": text}], **more}


def recorded(ctx):
    """Every /api/query request's queries, in order, and every values request."""
    asks, listed = [], []

    def query(route):
        text = route.request.url.split("q=")[1].split("&")[0]
        asks.append(json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))["queries"])
        answer(route)

    def values(route):
        text = route.request.url.split("q=")[1].split("&")[0]
        asked = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
        listed.append(asked)
        route.fulfill(json={"values": ["open", "review"]} if "state" in asked["text"] else
                      {"error": "prom: no such label", "error_kind": "refused"})
    ctx.route("**/api/query?*", query)
    ctx.route("**/api/query/values?*", values)
    return asks, listed


def chosen(pg, name):
    return pg.evaluate(f"() => [...document.querySelector('[data-var=\"{name}\"]').selectedOptions].map((o) => o.value)")


def settle(pg, asks, n):
    pg.wait_for_function("() => !DASH.flights.size")
    pg.wait_for_timeout(300)                                   # (nothing more is asked after a quiet moment)
    assert len(asks) == n, asks[n:] if len(asks) > n else asks


VARS = {"kind": {"type": "custom", "values": ["ticket", HOSTILE]},
        "state": {"type": "query", "source": "prom", "text": "label_values(ergostat_items, state)"},
        "env": {"type": "constant", "value": "prod"}}
DRAFT = {"title": "Vars", "vars": VARS, "panels": [
    text_panel(1, 'sum(ergostat_items{kind="$kind", env="$env"})'),
    text_panel(2, 'sum(ergostat_items{state=~"${state}"})'),
    {**text_panel(3, ""), "queries": [{"id": "a", "source": "counts", "agg": "last", "kind": "k"}]}]}


def test_changing_a_variable_asks_again_only_the_panels_that_use_it(browser, site):  # noqa: F811
    """Done 1: setting $kind asks panel 1 alone, setting $state panel 2 alone; panel 3 uses neither and is never asked
    again. The values are sent beside the text, never written into it here; the address keeps them."""
    ctx = context(browser, 1440, 1000)
    asks, listed = recorded(ctx)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(DRAFT)}")
    settle(pg, asks, 1)
    sent = {q.get("text") or q["source"]: q for q in asks[0]}
    assert len(sent) == 3 and "vars" not in sent["counts"]
    assert sent['sum(ergostat_items{kind="$kind", env="$env"})']["vars"] == {"kind": ["ticket"], "env": ["prod"]}
    assert sent['sum(ergostat_items{state=~"${state}"})']["vars"] == {"state": ["open"]}
    assert listed == [{"source": "prom", "text": "label_values(ergostat_items, state)", "since": 86400, "until": None,
                       "vars": {}}]
    assert pg.locator(".dash-vars [data-var]").count() == 2               # the constant is not shown
    assert pg.locator('.dash-vars [data-var="state"] option').all_inner_texts() == ["open", "review"]

    pg.select_option('[data-var="kind"]', HOSTILE)
    settle(pg, asks, 2)
    [only] = asks[1]
    assert only["text"] == 'sum(ergostat_items{kind="$kind", env="$env"})' and only["vars"]["kind"] == [HOSTILE]
    assert parse_qs(urlparse(pg.url).query)["var-kind"] == [HOSTILE]

    pg.select_option('[data-var="state"]', "review")
    settle(pg, asks, 3)
    assert [q["vars"] for q in asks[2]] == [{"state": ["review"]}]

    pg.select_option('[data-var="state"]', "review")                    # the same again: nothing to ask
    settle(pg, asks, 3)

    pg2 = opened_plain(ctx, pg.url)                                       # the address keeps what was chosen
    pg2.wait_for_function("() => !DASH.flights.size && DASH.got")
    assert chosen(pg2, "kind") == [HOSTILE] and chosen(pg2, "state") == ["review"]
    assert {json.dumps(q.get("vars"), sort_keys=True) for q in asks[-1]} == {
        json.dumps({"kind": [HOSTILE], "env": ["prod"]}, sort_keys=True), json.dumps({"state": ["review"]}), "null"}
    assert pg.errors == [] and pg2.errors == []
    ctx.close()


def test_an_earlier_ask_answering_after_a_variable_changed_does_not_overwrite_the_panel(browser, site):  # noqa: F811
    """A poll's ask still out when $kind is set: the panel asked again alone takes its own answer, and the poll's,
    coming later, is not drawn over it (by the ask's sequence, not by when answers come); the others take the poll's."""
    ctx = context(browser, 1440, 1000)
    recorded(ctx)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(DRAFT)}")
    pg.wait_for_function("() => !DASH.flights.size && DASH.got")
    got = pg.evaluate(f"""async () => {{
      const held = [];
      window.queryPanels = (panels) => new Promise((done) => held.push({{ panels, done }}));
      const said = (panels, word) => new Map(panels.map((p) => [p.id, {{ meta: null, results: [{{ id: "a", word,
        times: [1795399880, 1795399940, 1795400000], series: [{{ name: "x", values: [1, 2, 3] }}] }}] }}]));
      const poll = dashRefresh();
      const set = dashSetVar("kind", [{json.dumps(HOSTILE)}]);
      while (held.length < 2) await new Promise((r) => setTimeout(r, 20));
      held[1].done(said(held[1].panels, "after"));
      await set;
      held[0].done(said(held[0].panels, "before"));
      await poll;
      return {{ asked: held.map((x) => x.panels.map((p) => p.id)),
                word: Object.fromEntries([...DASH.got].map(([id, a]) => [id, a.results[0].word])) }};
    }}""")
    assert got["asked"] == [["p1", "p2", "p3"], ["p1"]]
    assert got["word"] == {"p1": "after", "p2": "before", "p3": "before"}
    assert pg.errors == []
    ctx.close()


def test_a_chained_variable_keeps_its_newest_listing_when_an_earlier_one_answers_later(browser, site):  # noqa: F811
    """$sub is listed by $kind and $leaf by $sub. $kind is set to a, then to b; the listing of $sub for b answers
    first and the one for a last. $sub keeps b's values (by the listing's sequence, not by when it answers), $leaf is
    listed again from $sub's new value, and the panel is asked with values of b's listing."""
    chain = {"title": "Chain", "vars": {
        "kind": {"type": "custom", "values": ["z", "a", "b"]},
        "sub": {"type": "query", "source": "prom", "text": 'label_values(ergostat_items{kind="$kind"}, sub)'},
        "leaf": {"type": "query", "source": "prom", "text": 'label_values(ergostat_items{sub="$sub"}, leaf)'}},
        "panels": [text_panel(1, 'sum(ergostat_items{sub="$sub", leaf="$leaf"})')]}
    ctx = context(browser, 1440, 1000)
    asks, _ = recorded(ctx)

    def values(route):
        text = route.request.url.split("q=")[1].split("&")[0]
        asked = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
        by = asked["vars"].get("sub" if "leaf" in asked["text"] else "kind", ["?"])[0]
        route.fulfill(json={"values": [f"{by}-1", f"{by}-2"]})
    ctx.route("**/api/query/values?*", values)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(chain)}")
    settle(pg, asks, 1)
    assert asks[0][0]["vars"] == {"sub": ["z-1"], "leaf": ["z-1-1"]}
    got = pg.evaluate("""async () => {
      const real = window.fetch, held = [];
      window.fetch = (url, ...more) => {
        const q = new URL(url, location.href).searchParams.get("q");
        if (!String(url).includes("/api/query/values") || !dashDecode(q).text.includes("kind")) return real(url, ...more);
        return new Promise((done) => held.push({ kind: dashDecode(q).vars.kind[0], go: () => done(real(url, ...more)) }));
      };
      const first = dashSetVar("kind", ["a"]);
      const second = dashSetVar("kind", ["b"]);
      while (held.length < 2) await new Promise((r) => setTimeout(r, 20));
      held[1].go();
      await second;
      held[0].go();
      await first;
      window.fetch = real;
      return { order: held.map((x) => x.kind), sub: DASH.options.get("sub"), leaf: DASH.options.get("leaf"),
               shown: [...document.querySelectorAll('[data-var="sub"] option')].map((o) => o.value) };
    }""")
    assert got == {"order": ["a", "b"], "sub": ["b-1", "b-2"], "leaf": ["b-1-1", "b-1-2"], "shown": ["b-1", "b-2"]}
    pg.wait_for_function("() => !DASH.flights.size")
    pg.wait_for_timeout(300)
    assert asks[-1][0]["vars"] == {"sub": ["b-1"], "leaf": ["b-1-1"]}
    assert all(q["vars"]["sub"] != ["a-1"] for a in asks for q in a)
    assert pg.errors == []
    ctx.close()


CHAIN = {"title": "Chain", "vars": {
    "kind": {"type": "custom", "values": ["z", "a", "b"]},
    "sub": {"type": "query", "source": "prom", "text": 'label_values(ergostat_items{kind="$kind"}, sub)'},
    "leaf": {"type": "query", "source": "prom", "text": 'label_values(ergostat_items{sub="$sub"}, leaf)'}},
    "panels": [text_panel(1, 'sum(ergostat_items{sub="$sub", leaf="$leaf"})')]}


def chained_values(ctx):
    def values(route):
        text = route.request.url.split("q=")[1].split("&")[0]
        asked = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
        by = asked["vars"].get("sub" if "leaf" in asked["text"] else "kind", ["?"])[0]
        route.fulfill(json={"values": [f"{by}-1", f"{by}-2"]})
    ctx.route("**/api/query/values?*", values)


def test_a_dependent_choice_not_in_its_new_listing_is_let_go_when_its_parent_changes(browser, site):  # noqa: F811
    """$sub and $leaf are chosen by hand (z-2, z-2-2), then $kind is set to b. Neither old choice is in its new
    listing, so each is let go: $sub shows and takes b-1, $leaf is listed from b-1 and takes b-1-1, the address keeps
    neither old value, and the panel is asked with b's values only. An address naming a $sub its $kind does not
    offer opens the same way, and the address is put right."""
    ctx = context(browser, 1440, 1000)
    asks, _ = recorded(ctx)
    chained_values(ctx)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(CHAIN)}")
    settle(pg, asks, 1)
    pg.select_option('[data-var="sub"]', "z-2")
    pg.wait_for_function("() => DASH.options.get('leaf')?.[0] === 'z-2-1'")
    settle(pg, asks, 2)
    pg.select_option('[data-var="leaf"]', "z-2-2")
    settle(pg, asks, 3)
    assert asks[2][0]["vars"] == {"sub": ["z-2"], "leaf": ["z-2-2"]}
    assert parse_qs(urlparse(pg.url).query)["var-sub"] == ["z-2"]

    pg.select_option('[data-var="kind"]', "b")
    pg.wait_for_function("() => DASH.options.get('leaf')?.[0] === 'b-1-1'")
    settle(pg, asks, 4)
    assert asks[3][0]["vars"] == {"sub": ["b-1"], "leaf": ["b-1-1"]}
    assert chosen(pg, "sub") == ["b-1"] and chosen(pg, "leaf") == ["b-1-1"]
    assert pg.locator('[data-var="sub"] option').all_inner_texts() == ["b-1", "b-2"]
    assert pg.locator('[data-var="leaf"] option').all_inner_texts() == ["b-1-1", "b-1-2"]
    address = parse_qs(urlparse(pg.url).query)
    assert address["var-kind"] == ["b"] and "var-sub" not in address and "var-leaf" not in address

    pg2 = opened_plain(ctx, f"{site}/dashboard?draft={encoded(CHAIN)}&var-kind=b&var-sub=a-2&var-leaf=a-2-1")
    pg2.wait_for_function("() => !DASH.flights.size && DASH.got")
    assert chosen(pg2, "sub") == ["b-1"] and chosen(pg2, "leaf") == ["b-1-1"]
    assert asks[-1][0]["vars"] == {"sub": ["b-1"], "leaf": ["b-1-1"]}
    address = parse_qs(urlparse(pg2.url).query)
    assert address["var-kind"] == ["b"] and "var-sub" not in address and "var-leaf" not in address
    assert all(q["vars"]["sub"][0][0] != "a" for a in asks for q in a)
    assert pg.errors == [] and pg2.errors == []
    ctx.close()


def test_a_panel_repeated_by_a_variable_follows_its_chosen_values(browser, site):  # noqa: F811
    """Done 3: one panel for each value chosen, each asking with its own value; a value let go takes its panel away and
    asks nothing; a value chosen adds its panel, asked alone; the panels kept are not asked again."""
    draft = {"title": "Repeat", "vars": {"kind": {"type": "custom", "values": ["a", "b", "c", "d"], "multi": True}},
             "panels": [text_panel(1, 'sum(ergostat_items{kind="$kind"})', repeat={"var": "kind"},
                                   layout={"x": 0, "y": 0, "w": 3, "h": 7}),
                        {**text_panel(2, ""), "queries": [{"id": "a", "source": "counts", "agg": "last", "kind": "k"}],
                         "layout": {"x": 0, "y": 7, "w": 6, "h": 7}}]}
    ctx = context(browser, 1440, 1000)
    asks, _ = recorded(ctx)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(draft)}&var-kind=a&var-kind=b&var-kind=c")

    def cells():
        return sorted(pg.evaluate("() => [...document.querySelectorAll('.dash-cell')].map((c) => c.getAttribute('aria-label'))"))
    settle(pg, asks, 1)
    assert cells() == ["Panel 1: a", "Panel 1: b", "Panel 1: c", "Panel 2"]
    assert sorted(q["vars"]["kind"][0] for q in asks[0] if q.get("vars")) == ["a", "b", "c"]

    pg.select_option('[data-var="kind"]', ["a", "c"])
    pg.wait_for_function("() => document.querySelectorAll('.dash-cell').length === 3")
    settle(pg, asks, 1)                                                   # b let go: nothing asked
    assert cells() == ["Panel 1: a", "Panel 1: c", "Panel 2"]

    pg.select_option('[data-var="kind"]', ["a", "c", "d"])
    settle(pg, asks, 2)
    assert cells() == ["Panel 1: a", "Panel 1: c", "Panel 1: d", "Panel 2"]
    assert [q["vars"] for q in asks[1]] == [{"kind": ["d"]}]
    pg.wait_for_function("() => DASH.cells.get('p1~d').drawn")
    assert parse_qs(urlparse(pg.url).query)["var-kind"] == ["a", "c", "d"]
    assert pg.errors == []
    ctx.close()


POLL_OFF = """
const realGet = Storage.prototype.getItem;
Storage.prototype.getItem = function (k) { return String(k).endsWith(".every") ? "Off" : realGet.call(this, k); };
"""


def test_the_first_draw_says_who_is_still_waiting_with_the_poll_off(browser, site):  # noqa: F811
    """The first draw asks every panel as new ones (a partial ask); the duration stat's 'still waiting' note comes with
    that ask, not with a later poll: here the poll is Off, so no poll could bring it."""
    ctx = context(browser, 1440, 1000)
    ctx.add_init_script(POLL_OFF)
    now = 1795400000.0
    waiting = [{"id": f"widget/{i}", "kind": "widget", "state": "ready", "entered": now - 3600 * (i + 1)} for i in range(3)]
    ctx.route("**/api/items?*", lambda r: r.fulfill(json={**ITEMS, "items": waiting, "matched": {"widget": 3}})
              if "state=ready" in r.request.url else r.fallback())
    pg = opened_plain(ctx, f"{site}/dashboard")
    pg.wait_for_function("() => DASH.got && !DASH.flights.size")
    assert pg.evaluate("() => DASH.timer") is None                       # the poll is Off
    pg.wait_for_function("() => [...document.querySelectorAll('.panel-note')].some((e) => e.textContent.includes('still waiting: 3'))",
                         timeout=5000)
    assert pg.evaluate("() => window.__queries") == 1                     # one ask, the first draw's
    assert pg.errors == []
    ctx.close()


RETRIES = """
window.__retries = [];
const realSet = window.setTimeout.bind(window);
window.setTimeout = (f, ms, ...more) => { if (ms === 10000) window.__retries.push(location.pathname); return realSet(f, ms, ...more); };
"""


def test_leaving_the_dashboard_mid_ask_schedules_nothing_and_says_nothing(browser, site):  # noqa: F811
    """An ask still out when the page is left (routed to the Dashboard again, then to the Items page) is aborted: its
    failure is not said in the new page's header or panels, and no retry is scheduled for it."""
    ctx = context(browser, 1440, 1000)
    ctx.add_init_script(RETRIES)
    ctx.add_init_script(POLL_OFF)                                        # (a poll's timer would hide a retry)
    held = []
    ctx.route("**/api/query?*", lambda r: held.append(r))                # never answered
    plain = {"title": "t", "panels": [text_panel(1, "sum(up)"), text_panel(2, "sum(up) by (job)")]}
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(plain)}")
    pg.wait_for_function("() => DASH.flights.size > 0")
    other = {"title": "u", "panels": [text_panel(3, "sum(up) by (pod)")]}
    pg.evaluate("(r) => navigate(r)", f"/dashboard?draft={encoded(other)}")   # to another Dashboard, its panels not these
    pg.wait_for_function("() => DASH.cells.has('p3') && DASH.flights.size > 0")
    pg.wait_for_timeout(300)
    said = pg.evaluate("() => document.querySelector('#main').innerText")
    assert "asking again" not in said and "did not answer" not in said, said
    assert pg.evaluate("() => window.__retries") == []

    pg.evaluate("() => navigate('/items')")                               # and left for another page
    pg.wait_for_function("() => location.pathname === '/items'")
    pg.wait_for_timeout(300)
    assert pg.evaluate("() => window.__retries") == []
    assert pg.evaluate("() => DASH.ver.size") == 0
    assert pg.errors == []
    ctx.close()
