"""The legend is open unless the reader closed it (dev/records/diagram-side-panel-legend-first.md): no page script
writes ergostat.legend except the legend's own toggle handler, so a first visit never stores 'closed' for the
reader. Read from the source, without a browser: in Chromium the legend inserted open fires a toggle that writes
'open' over a first-visit 'closed', so the browser tests cannot see that write come back."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"
WRITE = re.compile(r"""localStorage\.setItem\(\s*["']ergostat\.legend["']""")
HANDLER = re.compile(r"""addEventListener\(\s*["']toggle["']\s*,\s*\(\)\s*=>\s*\{\s*if\s*\(d\.isConnected\)""")


def test_the_legend_is_remembered_only_when_the_reader_toggles_it():
    writes = [(js.name, n, line) for js in sorted(STATIC.glob("*.js"))
              for n, line in enumerate(js.read_text().splitlines(), 1) if WRITE.search(line)]
    assert writes, "no script remembers the legend's open or closed state"
    stray = [(name, n) for name, n, line in writes
             if not (HANDLER.search(line) and HANDLER.search(line).start() < WRITE.search(line).start())]
    assert not stray, f"ergostat.legend written outside the legend's toggle handler: {stray}"
