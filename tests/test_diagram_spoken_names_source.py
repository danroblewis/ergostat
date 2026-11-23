"""The diagram parts' spoken names, read from the page's source with no browser (dev/records/diagram-spoken-names.md).
The browser tests in tests/test_diagram_rendering.py check the drawn labels over six demos and each kind's name;
this one runs where Playwright is absent: each view's name function speaks only its own discipline's words, every
kind word the browser sweep allows is one the function can say, and the focus name goes through the two functions."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"


def body(src: str, start: str, stop: str) -> str:
    """The text from `start` to the next `stop` after it (a function or a table and what follows to its end)."""
    i = src.find(start)
    assert i >= 0, f"no {start!r}: the check would pass on nothing"
    j = src.find(stop, i + len(start))
    assert j > i, f"no end {stop!r} after {start!r}"
    return src[i:j]


def words(code: str) -> str:
    """The string literals of a piece of JS (what it can say), template literals included."""
    return " ".join(a or b for a, b in re.findall(r'"([^"\n]*)"|`([^`]*)`', code))


def test_dynamics_names_never_say_a_control_word():
    sd = words(body((STATIC / "dynamics.js").read_text(encoding="utf-8"), "function sdSpoken(", "\n}\n"))
    for kind in ("stock", "flow", "pipe of flow", "connector", "goal gap", "desired level", "module", "cloud"):
        assert kind in sd, f"sdSpoken does not say {kind!r}"
    assert not re.search(r"sensor|controller", sd, re.I), sd


def test_blocks_names_never_say_a_dynamics_word():
    js = (STATIC / "blocks.js").read_text(encoding="utf-8")
    bd = words(body(js, "const BD_KINDS", "\nfunction openBlock("))
    for kind in ("controller", "summing junction", "signal", "reference minus measurement", "control loop", "subsystem"):
        assert kind in bd, f"bdSpoken does not say {kind!r}"
    assert not re.search(r"stock", bd, re.I), bd


def test_the_focus_name_of_a_dynamics_or_blocks_part_is_its_spoken_name():
    aria = body((STATIC / "keys.js").read_text(encoding="utf-8"), "function ariaOf(", "\n}\n")
    assert re.search(r"dynamics: typeof sdSpoken === \"function\" && sdSpoken", aria)
    assert re.search(r"blocks: typeof bdSpoken === \"function\" && bdSpoken", aria)
    first = aria.find("if (part) return spoken(part, S.graph);")
    assert 0 <= first < aria.find('if (el.matches(".node"))'), "the generic name is used before the spoken one"
