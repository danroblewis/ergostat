"""Done item 2 of dashboard-panel-controls-on-hover, read from the source without a browser (the browser tests in
tests/test_dashboard_page.py show it on the page): a panel in edit mode builds only Edit and remove, laid out of the
flow and hidden until the panel is hovered or holds focus.

    uv run python -m pytest tests/test_dashboard_controls.py
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"
JS = (STATIC / "dashboard.js").read_text(encoding="utf-8")
CSS = (STATIC / "dashboard.css").read_text(encoding="utf-8")


def tools_built():
    """The text of every dashTool(...) button dashboard.js builds for a panel (dashCell; a row's bar is its own)."""
    cell = re.search(r"\nfunction dashCell\(.*?\n\}\n", JS, re.S)
    assert cell, "no dashCell"
    return re.findall(r'dashTool\("([^"]*)"', cell.group(0))


def rule(selector):
    """The declarations of the CSS rule whose selector is exactly ``selector``."""
    found = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS, re.M)
    assert found, f"no rule for {selector}"
    return found.group(1)


def test_a_panel_builds_only_edit_and_remove():
    assert sorted(tools_built()) == ["Edit", "×"]
    for gone in ("dash-foot", "dash-grip", "⋮", "←", "→", "−", "↕"):
        assert gone not in JS, gone


def test_the_controls_are_out_of_the_flow_and_hidden_until_hover_or_focus():
    shut = rule(".dash-grid.editing .dash-tools")
    assert "position: absolute" in shut and "opacity: 0" in shut and "pointer-events: none" in shut
    shown = rule(".dash-grid.editing:not(.dragging) .dash-cell:is(:hover, :focus-within) .dash-tools")
    assert "opacity: 1" in shown and "pointer-events: auto" in shown
