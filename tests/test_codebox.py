"""The query boxes' shared code-editor part (codebox.js: line numbers and bracket matching), checked without a browser:
the page loads it before the two editors that call it, and none of the three scripts reaches past ergostat's own server
(done 3 of promql-code-editor; the browser tests in test_promql_editor.py and test_sql_editor.py check it running)."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"
EDITORS = ("promql.js", "sql.js")


def scripts() -> list[str]:
    """The /static/ scripts index.html loads, in its order."""
    return re.findall(r'<script src="/static/([^"]+)"></script>', (STATIC / "index.html").read_text())


def test_codebox_loads_before_the_editors_that_use_it():
    order = scripts()
    assert "codebox.js" in order
    for name in EDITORS:
        assert "codeBox." in (STATIC / name).read_text(), name
        assert order.index("codebox.js") < order.index(name), (name, order)


def test_editor_scripts_reach_nothing_outside_the_server():
    for name in ("codebox.js", *EDITORS):
        text = (STATIC / name).read_text()
        assert not re.search(r"https?://|//cdn|\bimport\s*\(|^\s*import\s", text, re.M), name
