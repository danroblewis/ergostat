"""A diagram left open asks for its graph every few seconds; what changes between two asks is almost always its readings
and values, not its structure (docs/proposals/scale.md, #12). The page says which structure it holds (``have``: the
hash this gives it), and when the answer's structure is still that one it is sent only the values: the value keys of
every part that has any (a node, a port, an edge, a loop), by the part's place in a walk both sides make the same way,
and the top-level answers that are values (``attention``). The page puts them into the copy it holds and has the very
answer a whole one would have been. Any other change (a part
added, a label, the model edited) changes the hash, and the whole answer is sent with its new one."""

from __future__ import annotations

import hashlib
import json

VALUES = ("value", "valueText", "points", "rate", "rateText", "position", "how", "estimated", "reading", "status", "error",
          "decision", "decisionAt", "excess", "desired", "switching", "band", "last", "charted", "measures", "rows", "loops")
TOP_VALUES = ("attention", "since", "until")   # the answer's own keys that are values: sent whole with every answer
                                                # (the Process view's window moves with the clock: a poll seconds on)


def walk(got: dict, visit) -> None:
    """Every part of an answer (each object below its top), in one order, keys sorted: ``visit(part)`` for each, and
    on into what is not a value (a value's own parts are the value's). The page walks its copy the same way
    (diagram.js: withValues): at the top every key but ``TOP_VALUES``; below it, every key but ``VALUES``."""
    def go(x, top: bool) -> None:
        if isinstance(x, list | tuple):                  # (as JSON has them: a list)
            for y in x:
                go(y, False)
        elif isinstance(x, dict):
            if not top:
                visit(x)
            skip = TOP_VALUES if top else VALUES
            for k in sorted(x, key=str):                  # (as JSON has them: their names, as text)
                if k not in skip:
                    go(x[k], False)
    go(got, True)


def split(got: dict) -> tuple[dict, dict]:
    """An answer as its structure (every value taken out) and its values: ``values``, ``[i, {key: value}]`` for the
    ``i``-th part that has any, and the top-level values."""
    found: list = []
    count = [0]

    def visit(x: dict) -> None:
        mine = {k: x[k] for k in VALUES if k in x}
        if mine:
            found.append([count[0], mine])
        count[0] += 1
    walk(got, visit)
    return _bare(got, True), {"values": found, **{k: got[k] for k in TOP_VALUES if k in got}}


def _bare(x, top: bool = False):
    """A copy without the values (what is left shared: the leaves)."""
    if isinstance(x, list | tuple):
        return [_bare(y) for y in x]
    if isinstance(x, dict):
        skip = TOP_VALUES if top else VALUES
        return {k: _bare(v) for k, v in x.items() if k not in skip}
    return x


def stamp(structure: dict) -> str:
    text = json.dumps(structure, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.blake2b(text.encode(), digest_size=12).hexdigest()


def answer(got: dict, have: str | None) -> dict:
    """The whole answer with its structure's hash (``structure``), or, when the page holds that structure already,
    only the values (``same``: the hash; ``keys``: which keys of a part are values)."""
    structure, values = split(got)
    h = stamp(structure)
    if have == h:
        return {"same": h, "keys": list(VALUES), "top": list(TOP_VALUES), **values}
    return {**got, "structure": h}
