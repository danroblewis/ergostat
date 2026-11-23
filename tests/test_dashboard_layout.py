"""Acceptance: the Dashboard's grid. The engine (``DashLayout``) is pure and is run in the page over random sequences;
the rest uses real pointer, touch and keyboard input on the real panels.js, with only the server faked.

    uv run --with playwright==1.63.0 python -m pytest tests/test_dashboard_layout.py -v
"""

from __future__ import annotations

import base64
import json
import os

import pytest

from tests.test_dashboard_page import browser, context, encoded, opened_plain, site  # noqa: F401

SHOTS = os.environ.get("DASHBOARD_SHOTS")


def panel(i, size="m", form="line", tall=False, **more):
    return {"id": f"p{i}", "title": f"Panel {i}", "form": form, "size": size, "tall": tall, "display": {},
            "queries": [{"id": "a", "source": "counts", "agg": "last", "kind": f"k{i}"}], **more}


MIXED = [panel(0, "s", "stat"), panel(1, "s", "stat"), panel(2, "s", "stat"), panel(3, "m", tall=True), panel(4, "m"),
         panel(5, "m"), panel(6, "l"), panel(7, "s"), panel(8, "full"), panel(9, "m"), panel(10, "m", tall=True), panel(11, "s")]


def page_of(browser, site, panels=MIXED, width=1440, height=900, **kw):  # noqa: F811
    ctx = context(browser, width, height, **kw)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded({'title': 'Grid', 'panels': panels})}")
    settled(pg)
    return ctx, pg


def settled(pg):
    pg.wait_for_function("() => !document.getAnimations().some((a) => a.effect?.target?.classList?.contains('dash-cell'))")


def layouts(pg):
    return pg.evaluate("() => Object.fromEntries(dashboardDraft().panels.map((p) => [p.id, p.layout]))")


def assert_sound(pg):
    """No two panels (or rows) overlap, in the draft or on the screen."""
    assert pg.evaluate("() => !DashLayout.overlaps(dashItems(dashboardDraft()))")
    assert pg.evaluate("""() => {
      const r = [...document.querySelectorAll('.dash-cell')].map((c) => c.getBoundingClientRect());
      return !r.some((a, i) => r.slice(i + 1).some((b) =>
        a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1));
    }""")


def head(pg, pid):
    b = pg.locator(f'[data-panel="{pid}"] .panel-head').bounding_box()
    return b["x"] + 12, b["y"] + b["height"] / 2


def units(pg):
    return pg.evaluate("""() => { const u = dashUnits(); return { left: u.r.left, top: u.r.top, col: u.col, row: u.row }; }""")


def drag(pg, start, to, steps=10, drop=True):
    pg.mouse.move(*start)
    pg.mouse.down()
    pg.mouse.move(start[0] + 6, start[1] + 6, steps=2)
    pg.mouse.move(*to, steps=steps)
    pg.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    if drop:
        pg.mouse.up()
        settled(pg)


def test_the_engine_never_overlaps_moves_only_what_is_hit_and_only_down(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site)
    got = pg.evaluate("""() => {
      let seed = 12345;
      const rnd = (n) => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed % n; };
      const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
      const hits = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
      const under = (items) => { const rows = items.filter((r) => r.row).sort((a, b) => a.y - b.y);
        return Object.fromEntries(items.filter((x) => !x.row).map((x) => [x.id, rows.filter((r) => r.y < x.y).pop()?.id ?? null])); };
      let steps = 0;
      for (let round = 0; round < 60; round++) {
        const withRows = round % 2 === 1;
        const made = Array.from({ length: 2 + rnd(23) }, (_, i) => ({ id: `n${i}`, x: 0, y: 0, w: 3 + rnd(10), h: 3 + rnd(12) }));
        let items = DashLayout.pack(made);
        if (withRows) items = DashLayout.arrange([...items.map((x) => ({ id: x.id, layout: x })),
          ...Array.from({ length: 1 + rnd(3) }, (_, i) => ({ id: `r${i}`, row: true, layout: { y: rnd(40) } }))]);
        for (let k = 0; k < 40; k++) {
          const panels = items.filter((x) => !x.row), it = panels[rnd(panels.length)];
          const to = { x: rnd(14) - 1, y: rnd(40) - 1, w: 1 + rnd(14), h: 1 + rnd(16) };
          const next = rnd(2) ? DashLayout.move(items, it.id, to) : DashLayout.resize(items, it.id, to);
          if (DashLayout.overlaps(next)) return `overlap at ${round}.${k}`;
          if (next.some((x) => x.x < 0 || x.x + x.w > 12 || x.y < 0 || x.w < 3 || x.h < 1)) return `out of bounds at ${round}.${k}`;
          if (next.length !== items.length) return "lost a panel";
          const was = new Map(items.map((x) => [x.id, x])), now = new Map(next.map((x) => [x.id, x]));
          const moved = next.filter((x) => x.id !== it.id && !same(x, was.get(x.id)));
          for (const m of moved) {
            const o = was.get(m.id);
            if (m.x !== o.x || m.w !== o.w || m.h !== o.h || m.y < o.y) return `moved other than down at ${round}.${k}`;
            // without rows, each that moved was covered where it stood by the panel placed or by one pushed
            const by = [it.id, ...moved.map((x) => x.id)].filter((id) => id !== m.id);
            if (!withRows && !by.some((id) => hits(now.get(id), o))) return `pushed unhit at ${round}.${k}`;
          }
          const a = under(items), b = under(next);                     // a row stays a break: no other panel changes row
          if (Object.keys(a).some((id) => id !== it.id && a[id] !== b[id])) return `crossed a row at ${round}.${k}`;
          items = next;
          steps++;
        }
      }
      const base = DashLayout.pack([{ id: "a", w: 6, h: 7 }, { id: "b", w: 6, h: 4 }, { id: "c", w: 6, h: 4 }]);
      if (!same(DashLayout.move(base, "a", { x: 6, y: 3 }), DashLayout.move(base, "a", { x: 6, y: 3 }))) return "not deterministic";
      return steps;
    }""")
    assert got == 2400
    ctx.close()


def grid3(**more):
    """A 3x3 grid of panels a third wide, each placed: ``g{row}{column}``, counted from 1."""
    return [panel(0, "s", id=f"g{r + 1}{c + 1}", title=f"Row {r + 1} column {c + 1}",
                  layout={"x": 4 * c, "y": 7 * r, "w": 4, "h": 7}, **more) for r in range(3) for c in range(3)]


def boxes(pg):
    """Where each panel is on the screen."""
    return pg.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.dash-cell')].map((c) => {
      const r = c.getBoundingClientRect();
      return [c.dataset.panel, [r.left, r.top, r.width, r.height].map(Math.round)]; }))""")


def test_removing_a_panel_from_a_3x3_grid_moves_no_other(browser, site):  # noqa: F811
    """Done 1: the panel at (1,2) (first row, second column) removed, every other keeps its exact place."""
    ctx, pg = page_of(browser, site, grid3())
    was, seen = layouts(pg), boxes(pg)
    assert was["g12"] == {"x": 4, "y": 0, "w": 4, "h": 7}
    pg.get_by_role("button", name="Edit", exact=True).click()
    pg.wait_for_selector(".dash-grid.editing")
    settled(pg)
    seen = boxes(pg)
    pg.locator('[data-panel="g12"]').focus()
    pg.keyboard.press("Delete")
    settled(pg)
    now = layouts(pg)
    assert "g12" not in now
    assert now == {k: v for k, v in was.items() if k != "g12"}
    assert now["g22"] == {"x": 4, "y": 7, "w": 4, "h": 7}                      # the one below it stays down
    assert boxes(pg) == {k: v for k, v in seen.items() if k != "g12"}
    pg.reload()
    pg.wait_for_selector(".dash-cell")
    assert layouts(pg) == now
    assert pg.errors == []
    ctx.close()


def test_resizing_a_panel_smaller_moves_nothing_else(browser, site):  # noqa: F811
    """Done 2: a panel made narrower and shorter, by keyboard and by its corner; nothing else moves."""
    ctx, pg = page_of(browser, site, grid3(), height=1400)
    was = layouts(pg)
    pg.locator('[data-panel="g22"]').focus()
    pg.keyboard.press("Enter")
    pg.keyboard.press("Shift+ArrowLeft")
    pg.keyboard.press("Shift+ArrowUp")
    pg.keyboard.press("Shift+ArrowUp")
    pg.keyboard.press("Enter")
    settled(pg)
    now = layouts(pg)
    assert now["g22"] == {"x": 4, "y": 7, "w": 3, "h": 5}
    assert {k: v for k, v in now.items() if k != "g22"} == {k: v for k, v in was.items() if k != "g22"}
    u = units(pg)
    b = pg.locator('[data-panel="g11"] .dash-handle').bounding_box()
    start = (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    drag(pg, start, (start[0] - u["col"], start[1] - 3 * u["row"]))
    after = layouts(pg)
    assert after["g11"] == {"x": 0, "y": 0, "w": 3, "h": 4}
    assert {k: v for k, v in after.items() if k != "g11"} == {k: v for k, v in now.items() if k != "g11"}
    assert_sound(pg)
    ctx.close()


def test_a_drop_that_overlaps_pushes_only_what_it_overlaps(browser, site):  # noqa: F811
    """Done 3: the top-left panel dropped on the middle one: the middle and the one under it go down, nothing else
    moves, the place it left stays empty, and nothing overlaps."""
    ctx, pg = page_of(browser, site, grid3(), height=1400)
    was = layouts(pg)
    u = units(pg)
    sx, sy = head(pg, "g11")
    cell = pg.locator('[data-panel="g11"]').bounding_box()
    drag(pg, (sx, sy), (u["left"] + 4 * u["col"] + sx - cell["x"], u["top"] + 7 * u["row"] + sy - cell["y"]))
    now = layouts(pg)
    assert now["g11"] == {"x": 4, "y": 7, "w": 4, "h": 7}
    assert now["g22"] == {"x": 4, "y": 14, "w": 4, "h": 7}
    assert now["g32"] == {"x": 4, "y": 21, "w": 4, "h": 7}
    assert {k: v for k, v in now.items() if k not in ("g11", "g22", "g32")} == \
        {k: v for k, v in was.items() if k not in ("g11", "g22", "g32")}
    assert not any(v["x"] == 0 and v["y"] == 0 for v in now.values())            # the gap stays
    assert_sound(pg)
    ctx.close()


ROWED = {"title": "Rows", "rows": [{"id": "r1", "title": "First", "layout": {"y": 0}},
                                   {"id": "r2", "title": "Second", "layout": {"y": 9}}],
         "panels": [panel(1, "m", layout={"x": 0, "y": 1, "w": 6, "h": 7}), panel(2, "m", layout={"x": 6, "y": 1, "w": 6, "h": 7}),
                    panel(3, "m", layout={"x": 0, "y": 10, "w": 6, "h": 7}), panel(4, "m", layout={"x": 6, "y": 12, "w": 6, "h": 7})]}


def rows_of(pg):
    return pg.evaluate("() => Object.fromEntries((dashboardDraft().rows || []).map((r) => [r.id, r.layout.y]))")


def test_rows_fold_open_drag_with_their_panels_and_are_a_break(browser, site):  # noqa: F811
    """Done 4: a row folds and opens (giving back every place), is dragged with its panels, and is a guaranteed break:
    a panel above it grown pushes the row and its panels down together, and made small again moves nothing back."""
    ctx = context(browser, 1440, 1400)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(ROWED)}")
    settled(pg)
    assert pg.locator(".dash-row").count() == 2
    was, rows = layouts(pg), rows_of(pg)
    assert rows == {"r1": 0, "r2": 9}

    pg.locator('[data-panel="r1"] .dash-row-toggle').click()
    settled(pg)
    assert pg.locator('[data-panel="p1"]').count() == 0 and pg.locator('[data-panel="p2"]').count() == 0
    assert rows_of(pg) == {"r1": 0, "r2": 1}
    assert layouts(pg) == {"p3": {**was["p3"], "y": 2}, "p4": {**was["p4"], "y": 4}}
    assert pg.locator('[data-panel="r1"] .dash-row-toggle').get_attribute("aria-expanded") == "false"
    assert pg.evaluate("() => document.activeElement.dataset.act") == "toggle"
    pg.locator('[data-panel="r1"] .dash-row-toggle').click()
    settled(pg)
    assert layouts(pg) == was and rows_of(pg) == rows
    assert pg.locator('[data-panel="p1"] canvas').count() == 1

    pg.get_by_role("button", name="Edit", exact=True).click()
    pg.wait_for_selector(".dash-grid.editing")
    settled(pg)
    pg.locator('[data-panel="p1"]').focus()                       # the break: p1 grown into the next row pushes it whole
    pg.keyboard.press("Enter")
    for _ in range(4):
        pg.keyboard.press("Shift+ArrowDown")
    pg.keyboard.press("Enter")
    settled(pg)
    grown = layouts(pg)
    assert grown["p1"]["h"] == 11 and rows_of(pg) == {"r1": 0, "r2": 12}
    assert grown["p3"]["y"] == 13 and grown["p4"]["y"] == 15 and grown["p2"] == was["p2"]
    pg.keyboard.press("Enter")
    for _ in range(4):
        pg.keyboard.press("Shift+ArrowUp")
    pg.keyboard.press("Enter")
    settled(pg)
    assert rows_of(pg) == {"r1": 0, "r2": 12}                     # editing a panel never moves the next row up
    assert {k: layouts(pg)[k] for k in ("p3", "p4")} == {k: grown[k] for k in ("p3", "p4")}
    assert_sound(pg)

    before = layouts(pg)                                         # the second row dragged above the first, its panels along
    u = units(pg)
    g = pg.locator('[data-panel="r2"] .dash-grip').bounding_box()
    start = (g["x"] + g["width"] / 2, g["y"] + g["height"] / 2)
    drag(pg, start, (start[0], u["top"] + 2))
    after, rows = layouts(pg), rows_of(pg)
    assert rows["r2"] == 0 and rows["r1"] > after["p4"]["y"]
    for pid, row in (("p3", "r2"), ("p4", "r2"), ("p1", "r1"), ("p2", "r1")):
        old = 12 if row == "r2" else 0
        assert after[pid]["y"] - rows[row] == before[pid]["y"] - old and after[pid]["x"] == before[pid]["x"]
    pg.locator('[data-panel="r1"]').get_by_role("button", name="Row up").click()
    settled(pg)
    assert rows_of(pg)["r1"] == 0
    assert_sound(pg)
    assert pg.errors == []
    ctx.close()


def labelled(values):
    """A fake /api/query whose every query answers with one series per value (a query's label's values)."""
    def answer(route):
        text = route.request.url.split("q=")[1].split("&")[0]
        asked = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
        now = 1795400000.0
        route.fulfill(json={"now": now, "since": now - asked["since"], "until": now, "step": 60, "results": [
            {"id": q["id"], "times": [now - 120, now - 60, now],
             "series": [{"name": v, "values": [1.0, 2.0, 3.0]} for v in values], "unit": "", "capped": 0, "read_log": False}
            for q in asked["queries"]]})
    return answer


def test_a_panel_repeated_by_a_label_follows_its_values_within_its_row(browser, site):  # noqa: F811
    """Done 5: repeated by its query's label, 5 values are 5 panels, laid out in its row; 3 after two go, and nothing
    outside its row moves, nor the row below."""
    values = [f"v{i}" for i in range(5)]
    draft = {"title": "Repeat", "rows": [{"id": "r1", "title": "By value", "layout": {"y": 7}},
                                         {"id": "r2", "title": "After", "layout": {"y": 22}}],
             "panels": [panel(1, "m", layout={"x": 0, "y": 0, "w": 6, "h": 7}),
                        panel(2, "s", repeat={"query": "a"}, layout={"x": 0, "y": 8, "w": 4, "h": 7}),
                        panel(3, "m", layout={"x": 0, "y": 23, "w": 6, "h": 7}), panel(4, "m", layout={"x": 6, "y": 23, "w": 6, "h": 7})]}
    ctx = context(browser, 1440, 1600)
    ctx.route("**/api/query?*", labelled(values))
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(draft)}")
    pg.wait_for_function("() => document.querySelectorAll('.dash-cell.is-copy').length === 4")
    settled(pg)
    copies = pg.evaluate("""() => [...document.querySelectorAll('[data-panel^="p2"]')].map((c) =>
      [c.dataset.panel, c.getAttribute('aria-label'), c.style.getPropertyValue('--x'), c.style.getPropertyValue('--y')])""")
    assert sorted(c[0] for c in copies) == ["p2", "p2~v1", "p2~v2", "p2~v3", "p2~v4"]
    assert {(c[2], c[3]) for c in copies} == {("0", "8"), ("4", "8"), ("8", "8"), ("0", "15"), ("4", "15")}
    outside = {k: v for k, v in boxes(pg).items() if not k.startswith("p2")}
    assert layouts(pg) == {p["id"]: p["layout"] for p in draft["panels"]}       # the copies are not in the draft
    assert pg.evaluate("() => DASH.cells.get('p2~v3').drawn")

    values[:] = ["v0", "v2", "v4"]
    pg.evaluate("() => dashRefresh()")
    pg.wait_for_function("() => document.querySelectorAll('[data-panel^=\"p2\"]').length === 3")
    settled(pg)
    assert sorted(pg.evaluate("() => [...document.querySelectorAll('[data-panel^=\"p2\"]')].map((c) => c.dataset.panel)")) == \
        ["p2", "p2~v2", "p2~v4"]
    assert {k: v for k, v in boxes(pg).items() if not k.startswith("p2")} == outside
    assert pg.errors == []
    ctx.close()


def test_a_panel_repeated_by_a_variable_asks_once_per_value_and_keeps_its_room(browser, site):  # noqa: F811
    """A variable's values each get a panel asking its own query; when a repeat outgrows its row it pushes the row
    below down, and keeps that room when values go (the engine, directly)."""
    draft = {"title": "Vars", "vars": {"kind": ["k1", "k2", "k3"]},
             "panels": [{**panel(1, "s", repeat={"var": "kind"}, layout={"x": 0, "y": 0, "w": 4, "h": 7}),
                         "queries": [{"id": "a", "source": "counts", "agg": "last", "kind": "$kind"}]}]}
    ctx = context(browser, 1440, 1000)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(draft)}")
    pg.wait_for_function("() => document.querySelectorAll('.dash-cell').length === 3")
    assert sorted(q["kind"] for q in pg.evaluate("() => window.__asked")) == ["k1", "k2", "k3"]
    got = pg.evaluate("""() => {
      const items = [{ id: "s", x: 0, y: 1, w: 4, h: 7 }, { id: "r", row: true, x: 0, y: 8, w: 12, h: 1 },
                     { id: "o", x: 0, y: 9, w: 6, h: 7 }];
      const five = DashLayout.spread(items, "s", ["c1", "c2", "c3", "c4"]);
      const three = DashLayout.spread(items, "s", ["c1", "c2"], five.lines);
      const y = (r, id) => r.items.find((x) => x.id === id).y;
      return [five.lines, y(five, "r"), y(five, "o"), y(three, "r"), y(three, "o"), DashLayout.overlaps(five.items)];
    }""")
    assert got == [2, 15, 16, 15, 16, False]
    assert pg.errors == []
    ctx.close()


def test_a_tall_panel_leaves_no_hole_beside_it(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site, [panel(0, "m", tall=True), panel(1, "m"), panel(2, "m")])
    got = layouts(pg)
    assert (got["p1"]["x"], got["p1"]["y"]) == (6, 0) and (got["p2"]["x"], got["p2"]["y"]) == (6, 7)
    ctx.close()


@pytest.mark.parametrize("bad", [{"x": 1e308, "y": 1e308, "w": 1e308, "h": 1e308}, {"x": "a", "y": None, "w": -4, "h": 0}, [1, 2], 7])
def test_a_crafted_layout_is_bounded(browser, site, bad):  # noqa: F811
    ctx, pg = page_of(browser, site, [panel(0, layout=bad), panel(1, layout=bad), panel(2)])
    assert_sound(pg)
    # kept where it says (nothing rises), within the bound on a place
    assert all(0 <= x["x"] and x["x"] + x["w"] <= 12 and x["h"] <= 48 and x["y"] <= 2000 + 2 * 48 for x in layouts(pg).values())
    assert pg.errors == []
    ctx.close()


def test_crafted_rows_variables_and_repeats_are_bounded(browser, site):  # noqa: F811
    bad = {"title": "Bad", "vars": {f"v{i}": [str(n) for n in range(30)] + [None, {}, 3] for i in range(9)},
           "rows": [{"id": "r", "title": "x" * 300, "layout": {"y": 1e308}, "collapsed": i % 2 == 0, "span": 1e308,
                     "panels": [{"id": "h", "layout": {"y": -5}}]} for i in range(18)] + [7, None, []],
           "panels": [{"id": f"p{i}", "form": "line", "repeat": {"var": "v1"} if i == 0 else {"query": "a"} if i == 1 else 7,
                       "queries": [{"id": "a", "source": "counts", "agg": "last", "kind": "k"}]} for i in range(34)]}
    ctx = context(browser, 1440, 900)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(bad)}")
    got = pg.evaluate("""() => { const d = dashboardDraft();
      return { rows: d.rows.length, held: dashHeld(d), vars: Object.keys(d.vars).length,
               most: Math.max(...Object.values(d.vars).map((v) => v.length)),
               ids: new Set([...d.panels, ...d.rows, ...d.rows.flatMap((r) => r.panels || [])].map((x) => x.id)).size,
               all: d.panels.length + d.rows.length + d.rows.reduce((n, r) => n + (r.panels?.length || 0), 0),
               cells: document.querySelectorAll('[data-panel^="p0"]').length, title: d.rows[0].title.length,
               drawn: document.querySelectorAll('.dash-cell:not(.dash-row)').length }; }""")
    assert got["rows"] == 16 and got["held"] <= 32 and got["vars"] == 8 and got["most"] == 24 and got["drawn"] <= 64
    assert got["ids"] == got["all"] and got["cells"] == 24 and got["title"] == 200
    assert_sound(pg)
    assert pg.errors == []
    ctx.close()


def test_drag_by_the_header_with_a_placeholder_and_others_moving(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site)
    was = layouts(pg)
    u = units(pg)
    start = head(pg, "p4")
    to = (u["left"] + 12 + was["p3"]["x"] * u["col"], u["top"] + 8 + was["p3"]["y"] * u["row"])
    drag(pg, start, to, drop=False)
    assert pg.locator(".dash-slot").count() == 1 and pg.locator(".dash-cell.is-held").count() == 1
    settled(pg)
    if SHOTS:
        pg.screenshot(path=f"{SHOTS}/layout-dragging.png")
    pg.mouse.up()
    settled(pg)
    assert pg.locator(".dash-slot").count() == 0
    assert layouts(pg) != was
    assert_sound(pg)
    assert "draft=" in pg.url
    kept = layouts(pg)
    pg.reload()
    pg.wait_for_selector(".dash-cell")
    assert layouts(pg) == kept
    assert pg.errors == []
    ctx.close()


def test_escape_cancels_a_drag(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site)
    was = layouts(pg)
    x, y = head(pg, "p0")
    drag(pg, (x, y), (x + 500, y + 400), drop=False)
    pg.keyboard.press("Escape")
    pg.mouse.up()
    settled(pg)
    assert layouts(pg) == was and pg.locator(".dash-slot").count() == 0
    assert_sound(pg)
    ctx.close()


def test_a_click_on_a_header_moves_nothing_and_selects_nothing(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site)
    was = layouts(pg)
    x, y = head(pg, "p3")
    pg.mouse.click(x, y)
    drag(pg, (x, y), (x + 300, y + 200))
    assert pg.evaluate("() => String(getSelection())") == ""
    assert layouts(pg) != was
    ctx.close()


def test_a_drag_on_the_plot_is_the_charts_not_the_grids(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site)
    was = layouts(pg)
    b = pg.locator('[data-panel="p3"] .panel-canvas').bounding_box()
    drag(pg, (b["x"] + 40, b["y"] + 40), (b["x"] + 200, b["y"] + 90))
    assert layouts(pg) == was and pg.locator(".dash-slot").count() == 0
    ctx.close()


@pytest.mark.parametrize("edge,dw,dh", [(".dash-edge-r", 2, 0), (".dash-edge-b", 0, 3), (".dash-handle", 2, 3)])
def test_resize_from_each_edge_keeps_the_chart(browser, site, edge, dw, dh):  # noqa: F811
    ctx, pg = page_of(browser, site, height=1400)                                  # the pointer stays clear of auto-scroll
    pg.wait_for_selector('[data-panel="p3"] canvas')
    pg.evaluate("""() => { window.__canvas = document.querySelector('[data-panel="p3"] canvas');
                           window.__width = window.__canvas.getBoundingClientRect().width; }""")
    was = layouts(pg)["p3"]
    u = units(pg)
    b = pg.locator(f'[data-panel="p3"] {edge}').bounding_box()
    start = (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    drag(pg, start, (start[0] + dw * u["col"], start[1] + dh * u["row"]))
    now = layouts(pg)["p3"]
    assert (now["w"], now["h"]) == (min(12 - was["x"], was["w"] + dw), was["h"] + dh)
    assert_sound(pg)
    assert pg.evaluate("() => window.__canvas.isConnected")                        # moved and resized, never made again
    if dw:
        pg.wait_for_function("""() => document.querySelector('[data-panel="p3"] canvas')
                                .getBoundingClientRect().width > window.__width + 20""")
    ctx.close()


def test_the_keyboard_moves_and_resizes_with_focus_kept_and_each_step_said(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site)
    was = layouts(pg)
    cell = pg.locator('[data-panel="p7"]')
    cell.focus()
    pg.keyboard.press("Enter")
    assert "lifted" in pg.locator(".dash-live").inner_text()
    pg.keyboard.press("ArrowLeft")
    assert "column" in pg.locator(".dash-live").inner_text()
    pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Shift+ArrowRight")
    pg.keyboard.press("Shift+ArrowDown")
    assert pg.evaluate("() => document.activeElement.dataset.panel") == "p7"
    pg.keyboard.press("Escape")
    assert layouts(pg) == was
    assert pg.evaluate("() => document.activeElement.dataset.panel") == "p7"

    pg.keyboard.press("Enter")
    pg.keyboard.press("Shift+ArrowRight")
    pg.keyboard.press("Shift+ArrowDown")
    pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Enter")
    settled(pg)
    now = layouts(pg)["p7"]
    assert (now["w"], now["h"]) == (was["p7"]["w"] + 1, was["p7"]["h"] + 1)
    assert "Put down" in pg.locator(".dash-live").inner_text()
    assert pg.evaluate("() => document.activeElement.dataset.panel") == "p7"
    assert_sound(pg)
    ctx.close()


def test_auto_scroll_while_dragging_near_the_bottom(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site, height=600)
    top = "dashScroller().scrollTop"
    assert pg.evaluate(top) == 0
    x, y = head(pg, "p0")
    drag(pg, (x, y), (x + 40, 596), drop=False)
    pg.wait_for_function(f"() => {top} > 40")
    pg.mouse.up()
    settled(pg)
    assert_sound(pg)
    ctx.close()


def test_a_phone_is_one_column_in_reading_order_and_drags_to_reorder(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site, width=390, height=844)
    def tops():
        return pg.evaluate("""() => dashboardDraft().panels.map((p) => Math.round(
          document.querySelector(`[data-panel="${p.id}"]`).getBoundingClientRect().top))""")
    assert tops() == sorted(tops())
    assert pg.evaluate("""() => new Set([...document.querySelectorAll('.dash-cell')]
                                        .map((c) => Math.round(c.getBoundingClientRect().left))).size""") == 1
    assert pg.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    ids = pg.evaluate("() => dashboardDraft().panels.map((p) => p.id)")
    x, y = head(pg, ids[0])
    b = pg.locator(f'[data-panel="{ids[1]}"]').bounding_box()
    drag(pg, (x, y), (x, y + b["height"] * 0.6))
    now = pg.evaluate("() => dashboardDraft().panels.map((p) => p.id)")
    assert now[:2] == [ids[1], ids[0]]
    assert tops() == sorted(tops())
    if SHOTS:
        pg.screenshot(path=f"{SHOTS}/layout-390.png")
    ctx.close()


def test_touch_holds_to_lift_and_drags_to_reorder(browser, site):  # noqa: F811
    ctx = context(browser, 390, 844)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded({'title': 'Grid', 'panels': MIXED})}")
    settled(pg)
    ids = pg.evaluate("() => dashboardDraft().panels.map((p) => p.id)")
    x, y = head(pg, ids[0])
    send = pg.context.new_cdp_session(pg)
    send.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
    def touch(kind, px=None, py=None):
        send.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [] if px is None else [{"x": px, "y": py}]})
    touch("touchStart", x, y)
    pg.wait_for_selector(".dash-cell.is-held", timeout=2000)
    b = pg.locator(f'[data-panel="{ids[1]}"]').bounding_box()
    for k in range(1, 9):
        touch("touchMove", x, y + b["height"] * 0.6 * k / 8)
        pg.wait_for_timeout(24)
    touch("touchEnd")
    settled(pg)
    assert pg.evaluate("() => dashboardDraft().panels.map((p) => p.id)")[:2] == [ids[1], ids[0]]
    ctx.close()


def test_a_version_one_draft_is_placed_and_any_sequence_stays_sound(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site)
    assert all(set(x) == {"x", "y", "w", "h"} for x in layouts(pg).values())
    assert_sound(pg)
    for pid, dx, dy in (("p1", 420, 300), ("p8", 200, -300), ("p5", -300, 500), ("p10", 500, -200)):
        pg.evaluate("(id) => document.querySelector(`[data-panel=\"${id}\"]`).scrollIntoView({ block: 'center' })", pid)
        x, y = head(pg, pid)
        drag(pg, (x, y), (max(10, x + dx), max(70, min(880, y + dy))))
        assert_sound(pg)
    assert pg.evaluate("() => document.documentElement.scrollHeight <= innerHeight + 1")   # only the page's own pane scrolls
    assert pg.evaluate("""() => { const g = document.querySelector('.dash-grid'), r = g.getBoundingClientRect();
      const last = Math.max(...[...document.querySelectorAll('.dash-cell')].map((c) => c.getBoundingClientRect().bottom));
      return Math.abs(last - r.bottom) <= 1; }""")                                  # no room left over from a drag
    if SHOTS:
        pg.evaluate("() => { dashScroller().scrollTop = 0; }")
        pg.screenshot(path=f"{SHOTS}/layout-1440.png")
    assert pg.errors == []
    ctx.close()
