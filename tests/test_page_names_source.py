"""The page's announced state and names, read from the scripts' source with no browser: the nav marks its page with
aria-current, the view buttons carry aria-pressed, the glyph controls and repeated links have names, data tables put
their header row in a thead with scoped headers, the side panel is a landmark, and the small targets are 24 px.
The browser test (tests/test_items_page.py::test_the_page_view_and_controls_are_named) checks the drawn pages; this
one runs where Playwright is absent."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"


def src(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_the_nav_marks_the_current_page_and_clears_the_others():
    js = src("util.js")
    assert 'a.setAttribute("aria-current", "page")' in js, "the nav link of the page shown gets no aria-current"
    assert 'a.removeAttribute("aria-current")' in js, "a nav link left keeps its aria-current"


def test_each_diagram_view_button_says_whether_it_is_pressed():
    js = src("diagram.js")
    for view in ("dynamics", "blocks", "process"):
        assert f'"aria-pressed": String(view === "{view}")' in js, f"the {view} view button carries no aria-pressed"


def test_the_items_toggles_say_whether_they_are_pressed():
    assert '"aria-pressed": String(!!on)' in src("pages.js"), "the Items page's toggles carry no aria-pressed"


def test_the_glyph_controls_and_the_sort_button_have_names():
    js = src("diagram.js")
    for label in ("Zoom out", "Zoom in", "More diagram options"):
        assert f'"aria-label", "{label}"' in js or f'"aria-label": "{label}"' in js, f"no '{label}' name"
    pages = src("pages.js")
    assert 'f === "by" ? "author" : f' in pages and '"aria-label": sortName(f)' in pages, "a sort button for by is not 'Sort by author'"


def test_the_repeated_model_links_carry_their_row_name():
    js = src("review.js")
    for word in ("process", "controller", "scope"):
        assert f'`${{g}} {word}`' in js, f"the /model rows' '{word}' links are not named for their row"


def test_the_side_panel_is_a_named_landmark():
    assert re.search(r'h\("aside", \{[^}]*"aria-label": "[^"]+"', src("diagram.js")), "the side panel is not an <aside aria-label>"


def test_data_table_headers_sit_in_a_scoped_thead():
    util = src("util.js")
    body = re.search(r"function headRow\(\.\.\.ths\) \{(.*?)\n\}", util, re.S)
    assert body, "no headRow helper in util.js"
    assert 'setAttribute("scope", "col")' in body.group(1) and 'h("thead"' in body.group(1)
    assert 'setAttribute("aria-sort"' in body.group(1), "a sorted column's order is not on its th"
    for name in ("details.js", "diagram.js", "equations.js", "itemsets.js", "pages.js", "review.js"):
        js = src(name)
        assert not re.search(r'h\("table", \{[^}]*\}, h\("tr"', js), f"{name} puts a header row straight in a table"


def test_the_small_targets_are_24_px():
    css = src("style.css")
    assert re.search(r"\.hit24, button\.rg-key \{[^}]*min-height: 24px;[^}]*min-width: 24px;", css)
    assert re.search(r"label\.check input\[type=checkbox\] \{[^}]*width: 24px; height: 24px;", css)
    assert 'class: "hit24"' in src("diagram.js"), "the Evidence links are not 24 px targets"
