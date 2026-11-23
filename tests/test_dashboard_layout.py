"""Acceptance: the Dashboard's grid. The engine (``DashLayout``) is pure and is run in the page over random sequences;
the rest uses real pointer, touch and keyboard input on the real panels.js, with only the server faked.

    uv run --with playwright==1.63.0 python -m pytest tests/test_dashboard_layout.py -v
"""

from __future__ import annotations

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
    """No two panels overlap, in the draft or on the screen, and nothing can rise."""
    assert pg.evaluate("""() => {
      const items = dashItems(dashboardDraft().panels);
      return !DashLayout.overlaps(items) && JSON.stringify(DashLayout.compact(items)) === JSON.stringify(items);
    }""")
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


def test_the_engine_never_overlaps_and_is_stable_and_deterministic(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site)
    got = pg.evaluate("""() => {
      let seed = 12345;
      const rnd = (n) => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed % n; };
      const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
      let steps = 0;
      for (let round = 0; round < 60; round++) {
        const made = Array.from({ length: 2 + rnd(23) }, (_, i) => ({ id: `n${i}`, x: 0, y: 0, w: 3 + rnd(10), h: 3 + rnd(12) }));
        let items = DashLayout.pack(made);
        for (let k = 0; k < 40; k++) {
          const it = items[rnd(items.length)], to = { x: rnd(14) - 1, y: rnd(40) - 1, w: 1 + rnd(14), h: 1 + rnd(16) };
          const over = rnd(2) ? items[rnd(items.length)].id : null;
          const next = rnd(2) ? DashLayout.move(items, it.id, to, over) : DashLayout.resize(items, it.id, to);
          const again = DashLayout.compact(next);
          if (DashLayout.overlaps(next)) return `overlap at ${round}.${k}`;
          if (!same(again, next)) return `not settled at ${round}.${k}`;
          if (next.some((x) => x.x < 0 || x.x + x.w > 12 || x.y < 0 || x.w < 3 || x.h < 3)) return `out of bounds at ${round}.${k}`;
          if (next.length !== items.length) return "lost a panel";
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


def test_a_tall_panel_leaves_no_hole_beside_it(browser, site):  # noqa: F811
    ctx, pg = page_of(browser, site, [panel(0, "m", tall=True), panel(1, "m"), panel(2, "m")])
    got = layouts(pg)
    assert (got["p1"]["x"], got["p1"]["y"]) == (6, 0) and (got["p2"]["x"], got["p2"]["y"]) == (6, 7)
    ctx.close()


@pytest.mark.parametrize("bad", [{"x": 1e308, "y": 1e308, "w": 1e308, "h": 1e308}, {"x": "a", "y": None, "w": -4, "h": 0}, [1, 2], 7])
def test_a_crafted_layout_is_bounded(browser, site, bad):  # noqa: F811
    ctx, pg = page_of(browser, site, [panel(0, layout=bad), panel(1, layout=bad), panel(2)])
    assert_sound(pg)
    assert all(0 <= x["x"] and x["x"] + x["w"] <= 12 and x["h"] <= 48 and x["y"] < 200 for x in layouts(pg).values())
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
