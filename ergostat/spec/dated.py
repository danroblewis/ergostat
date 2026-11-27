"""A projection's definition saved with the date each part last changed (SPEC §5a, *Saving*): ``# updated YYYY-MM-DD``
above the projection, above its ``query:`` and above each ``events:`` entry that changed. Only the parts that changed
are rewritten: a part the draft leaves as it was (the same value, however it is written) keeps its old text, comments
and all, byte for byte."""

from __future__ import annotations

import re

import yaml

UPDATED = re.compile(r"^\s*#\s*updated\s+\d{4}-\d{2}-\d{2}\s*$")


def _indent(s: str) -> int:
    return len(s) - len(s.lstrip(" "))


def _is_key(s: str, ind: int) -> bool:
    return bool(s.strip()) and not s.lstrip().startswith("#") and _indent(s) == ind and not s.lstrip().startswith("- ")


def segments(lines: list[str], ind: int) -> list[tuple[str | None, list[str], list[str]]]:
    """The keys at indent ``ind`` of these lines, each ``(key, lead, lines)``: the comment lines just above it
    (``lead``), and its own line with everything under it. Lines before the first key: a segment of key None."""
    out: list = []
    cur_key, cur, lead = None, [], []
    pending: list[str] = []
    for s in lines:
        if _is_key(s, ind):
            if cur or cur_key is not None:
                out.append((cur_key, lead, cur))
            elif pending and cur_key is None and not out:
                pass
            k = s.strip().split(":", 1)[0].strip().strip("'\"")
            cur_key, lead, cur = k, pending, [s]
            pending = []
        elif s.lstrip().startswith("#") and _indent(s) <= ind and (cur_key is None or True):
            pending.append(s)
        elif not s.strip():
            pending.append(s)
        else:
            cur.extend(pending)
            pending = []
            cur.append(s)
    if cur or cur_key is not None:
        out.append((cur_key, lead, cur))
    if pending:
        if out:
            k, ld, ls = out[-1]
            out[-1] = (k, ld, ls + pending)
        else:
            out.append((None, [], pending))
    return out


BAD = object()


def _value(lines: list[str]):
    try:
        return yaml.safe_load("\n".join(lines))
    except yaml.YAMLError:
        return BAD


def _same(a: list[str], b: list[str]) -> bool:
    x, y = _value(a), _value(b)
    return (x is not BAD and x == y) or "\n".join(a) == "\n".join(b)


def _undated(lead: list[str]) -> list[str]:
    return [s for s in lead if not UPDATED.match(s)]


def _stamp(ind: int, today: str) -> str:
    return " " * ind + f"# updated {today}"


def _children_indent(lines: list[str]) -> int | None:
    for s in lines[1:]:
        if s.strip() and not s.lstrip().startswith("#"):
            return _indent(s)
    return None


def dated(old: list[str] | None, new: list[str], today: str) -> tuple[list[str], bool]:
    """The body to write (``new``, its unchanged parts in ``old``'s text, its changed query and events entries dated),
    and whether anything changed. ``old`` None: a new projection (its query and every entry dated)."""
    olds = {k: (ld, ls) for k, ld, ls in segments(old or [], 0) if k is not None}
    out: list[str] = []
    changed = old is None
    for k, lead, ls in segments(new, 0):
        if k is None:
            out += ls
            continue
        was = olds.get(k)
        if was is not None and _same(was[1], ls):
            out += was[0] + was[1]
            continue
        changed = True
        if k == "query":
            out += _undated(lead) + [_stamp(0, today)] + ls
        elif k == "events" and len(ls) > 1:
            ci = _children_indent(ls)
            olde = {}
            if was is not None and len(was[1]) > 1:
                wi = _children_indent(was[1])
                olde = {ek: (eld, els) for ek, eld, els in segments(was[1][1:], wi) if ek is not None} if wi is not None else {}
            out += _undated(lead) + [ls[0]]
            for ek, eld, els in segments(ls[1:], ci if ci is not None else 2):
                if ek is None:
                    out += els
                    continue
                w = olde.get(ek)
                if w is not None and _same(w[1], els):
                    out += w[0] + w[1]
                else:
                    out += _undated(eld) + [_stamp(_indent(els[0]), today)] + els
        else:
            out += lead + ls
    if not changed and set(olds) != {k for k, _, _ in segments(new, 0) if k is not None}:
        changed = True
    return out, changed
