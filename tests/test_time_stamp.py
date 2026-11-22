"""The one time stamp, read from the page's script without a browser (the browser check is
tests/test_items_page.py::test_every_time_is_one_stamp_with_its_date_and_zone): one formatter, the fields it covers,
and event data printed unrounded."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"


def js(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_one_formatter_gives_the_date_the_time_and_the_zone():
    util = js("util.js")
    assert len(re.findall(r"^function stamp\(", util, re.M)) == 1
    body = util[util.index("function stamp("):]
    body = body[:body.index("\n}\n")]
    template = re.search(r"`([^`]*)`", body).group(1)
    assert re.fullmatch(r"\$\{d\.getFullYear\(\)\}-\$\{p\(d\.getMonth\(\) \+ 1\)\}-\$\{p\(d\.getDate\(\)\)\} "
                        r"\$\{p\(d\.getHours\(\)\)\}:\$\{p\(d\.getMinutes\(\)\)\}:\$\{p\(d\.getSeconds\(\)\)\} \$\{zone\}",
                        template), template
    assert 'timeZoneName: "short"' in util


def test_every_at_raised_since_and_started_field_is_a_time_field():
    rule = re.search(r"const TIME_FIELD = /(.+)/;", js("util.js")).group(1)
    for name in ("done_at", "created_at", "at", "raised", "since", "started"):
        assert re.search(rule, name), name
    for name in ("status", "chat", "format", "started_by", "raised_by"):
        assert not re.search(rule, name), name
    assert "timeField(name, v) ?? fieldView(" in js("pages.js")


def test_the_gaps_tables_use_the_stamp_and_event_data_is_unrounded():
    details = js("details.js")
    data = details[details.index("function dataCell("):]
    data = data[:data.index("\n}\n")]
    assert "tidy" not in data and "toPrecision" not in data and "toFixed" not in data
    assert not re.search(r"\btidy\b", js("util.js"))
    table = details[details.index("function eventsTable("):]
    assert 'h("td", { class: "nowrap" }, stamp(e.time))' in table[:table.index("\n}\n")]
    assert '["when", stamp(e.time)]' in details
    assert "const when = (t) => stamp(t);" in js("pages.js")
    for name in ("details.js", "pages.js"):
        assert "toLocaleString(" not in js(name) and "toLocaleDateString(" not in js(name), name
