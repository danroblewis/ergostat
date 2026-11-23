"""The view switch's words, read from the page's source with no browser: each of the three view buttons in the
/diagram toolbar keeps its hover title and carries its visible second half, and the style keeps that half shown.
The browser test (tests/test_diagram_rendering.py::test_the_view_switch_says_what_each_view_shows_on_a_wide_screen_and_a_phone)
checks the drawn text at 1440 and 390 px; this one runs where Playwright is absent."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"


def test_each_view_button_has_its_title_and_says_what_it_shows():
    js = (STATIC / "diagram.js").read_text(encoding="utf-8")
    for view, name, half in (("dynamics", "Dynamics", "what is"), ("blocks", "Blocks", "what is controlled"),
                             ("process", "Process", "what happened")):
        button = re.search(r'h\("button", \{ class: view === "' + view + r'"[^\n]*\n?[^\n]*', js)
        assert button, f"no {view} view button in diagram.js"
        text = button.group(0)
        assert re.search(r'title: "[^"]+"', text), f"the {view} button lost its hover title"
        assert f'"{name}", h("span", {{ class: "what" }}, " · {half}")' in text, f"the {view} button does not say '{half}'"


def test_the_second_half_is_shown_not_hidden():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    rules = re.findall(r"\.seg \.what\s*\{([^}]*)\}", css)
    assert rules, "no .seg .what rule in style.css"
    assert not any(re.search(r"display:\s*none|visibility:\s*hidden", r) for r in rules)
