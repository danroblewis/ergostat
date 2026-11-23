"""The diagram's layout scripts, read as the page is sent them (no browser: the behaviour itself is checked in
tests/test_diagram_rendering.py with Playwright). These pin the two fixes for the console's layout warnings:
every libavoid pin goes through the one clamp, and ELK's multi-edge wrapping is tried again at single edges before
the layout drops wrapping."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"


def test_every_libavoid_pin_is_a_share_of_its_part_clamped_to_it():
    src = (STATIC / "avoid.js").read_text()
    calls = re.findall(r"\.addPin\(([^;]*?)\);", src)
    assert calls, "avoid.js adds no pins: the check would pass on nothing"
    assert all(c.strip().startswith("pinOn(") for c in calls), calls      # no pin handed over in pixels
    assert re.search(r"const share = \(v, len\) => \(len > 0 \? Math\.min\(1, Math\.max\(0, v / len\)\) : 0\);", src)
    assert re.search(r"const pinOn = \(s, p\) => \(\{[^}]*x: p\.abs \? share\(p\.x, s\.w\) : p\.x, "
                     r"y: p\.abs \? share\(p\.y, s\.h\) : p\.y,\s*proportional: true,", src)


def test_elk_is_tried_at_single_edge_wrapping_before_wrapping_is_dropped():
    src = (STATIC / "layouts.js").read_text()
    body = src.split("async function runLayoutWith", 1)[1]
    single, dropped = body.find('"SINGLE_EDGE"'), body.find("again without wrapping")
    assert 0 <= single < dropped, "the single-edge retry must come before the fallback that drops wrapping"
    assert "try { lay = await wrapped(" in body
