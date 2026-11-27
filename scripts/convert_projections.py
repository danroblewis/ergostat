#!/usr/bin/env python3
"""Rewrite projections from the old syntax (``match:``, ``states:``, ``events:`` keyed by event type with ``"*"``,
``otherwise:``) to the projection workbench's (``query:``, ``fields:``, named kinds of event with ``when:``), in YAML
files and in the YAML strings of Python files (tests). A one-off, mechanical: what it cannot rewrite it names.

    python3 scripts/convert_projections.py FILE...     (needs ruamel.yaml: a round trip keeps the comments)
"""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

OLD = ("match", "states", "otherwise")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _yaml():
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def path_expr(p: str) -> str:
    if p in ("type", "source", "time", "key"):
        return p
    if p == "item":
        return "key"
    parts = p.split(".")
    out = parts[0]
    for x in parts[1:]:
        out += f".{x}" if IDENT.match(x) else f"[{x!r}]"
    return out


def lit(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    return repr(v) if not isinstance(v, str) else repr(str(v))


def query_of(match) -> str:
    terms = []
    for p, v in match.items():
        e = path_expr(str(p))
        if isinstance(v, str) and any(c in v for c in "*?["):
            if v.endswith("*") and not any(c in v[:-1] for c in "*?["):
                terms.append(f"{e}.startswith({v[:-1]!r})")
            else:
                terms.append(f"glob({e}, {v!r})")
        elif isinstance(v, list):
            terms.append("(" + " or ".join(f"{e} == {lit(x)}" for x in v) + ")")
        else:
            terms.append(f"{e} == {lit(v)}")
    return " and ".join(terms)


def kind_name(t: str, used: set) -> str:
    n = re.sub(r"[^a-z0-9-]+", "-", re.sub(r"^\$\{[^}]*\}\.", "", str(t)).lower()).strip("-") or "event"
    if not n[0].isalpha():
        n = "e-" + n
    base, i = n, 2
    while n in used:
        n, i = f"{base}-{i}", i + 1
    used.add(n)
    return n


def is_old(b) -> bool:
    if not isinstance(b, dict):
        return False
    if any(k in b for k in OLD):
        return True
    ev = b.get("events")
    if isinstance(ev, dict) and any(not isinstance(h, dict) or "when" not in h for h in ev.values()):
        return True
    return False


FOLD_CALL = re.compile(r"^\s*(add|append|union|merge|min|max|first|count|mean|variance|stdev|rms)\(\s*data\.([A-Za-z_][A-Za-z0-9_]*)\s*(?:,\s*(\d+)\s*)?\)\s*$")


def _comments(src, dst, keys=None):
    try:
        for k, c in src.ca.items.items():
            if keys is None or k in keys:
                dst.ca.items[k] = c
    except AttributeError:
        pass


def convert(b):
    """An old-syntax projection body → the new syntax (a CommentedMap, the other keys and their comments kept)."""
    events = b.get("events") if isinstance(b.get("events"), dict) else {}
    states = b.get("states")
    otherwise = b.get("otherwise", "merge")
    star = events.get("*") or {}
    folded = {}                                   # a "*" entry FOLD(data.F) on field F: the field's declared fold
    for f, v in star.items():
        m = FOLD_CALL.match(v) if isinstance(v, str) else None
        if m and m.group(2) == f:
            folded[f] = m.group(1) + (f"({m.group(3)})" if m.group(3) else "")
    rest_star = CommentedMap((f, v) for f, v in star.items() if f not in folded)
    _comments(star, rest_star, set(rest_star))
    names: list = []
    for t, h in events.items():
        for f in (h or {}):
            if f not in names and f not in ("...",):
                names.append(f)
    rels = set(b.get("relations") or {}) if isinstance(b.get("relations"), dict) else set()
    fields = CommentedMap()
    if states is not None:
        fields["state"] = CommentedMap([("type", f"one of [{', '.join(map(str, states))}]")]) \
            if isinstance(states, list) else CommentedMap([("type", states)])
    for f in names:
        if f == "state" or f in rels or (f == "stages" and b.get("pipeline")):
            continue
        fields[f] = CommentedMap([("fold", folded[f])]) if f in folded else CommentedMap()
        fields[f].fa.set_flow_style()
    _comments(star, fields, set(folded))
    used: set = set()
    new_events = CommentedMap()
    tname = {}
    for t, h in events.items():
        if t == "*":
            continue
        h = h or {}
        e = CommentedMap()
        e["when"] = f"type == {str(t)!r}"
        if otherwise == "rest":
            e["..."] = "data"
        else:
            for f in folded:
                if f not in h:
                    e[f] = f"data.{f}"
        for f, v in rest_star.items():
            if f not in h:
                e[f] = v
        for f, v in h.items():
            e[f] = v
        _comments(h, e)
        n = kind_name(t, used)
        tname[str(t)] = n
        new_events[n] = e
    _comments(events, new_events, None)
    for t, n in tname.items():                     # a comment on the old type's line: on the new name's
        try:
            if t in events.ca.items:
                new_events.ca.items[n] = events.ca.items[t]
        except AttributeError:
            pass
    moves_from = b.get("moves-from")
    if otherwise in ("merge", "rest") and (events or star):
        o = CommentedMap([("when", True), ("...", "data")])
        for f, v in rest_star.items():
            o[f] = v
        new_events[kind_name("other", used)] = o
    elif otherwise == "ignore":
        o = CommentedMap([("when", True)])
        for f in folded:
            o[f] = f"data.{f}"
        for f, v in rest_star.items():
            o[f] = v
        new_events[kind_name("other", used)] = o
    out = CommentedMap()
    wrote_fields = False
    for k, v in b.items():
        if k == "match":
            out["query"] = query_of(v) if isinstance(v, dict) else v
        elif k == "states" or (k == "events" and not wrote_fields):
            if fields and not wrote_fields:
                out["fields"] = fields
            wrote_fields = True
            if k == "events" and new_events:
                out["events"] = new_events
        elif k == "events":
            if new_events:
                out["events"] = new_events
        elif k == "otherwise":
            continue
        elif k == "moves-from" and isinstance(moves_from, dict):
            out[k] = CommentedMap((tname.get(str(t), t), s) for t, s in moves_from.items())
        else:
            out[k] = v
    if "events" not in out and new_events and "events" not in b:
        out["events"] = new_events
    if not wrote_fields and fields:
        out["fields"] = fields
    _comments(b, out, set(out))
    return out



def convert_doc(data) -> int:
    """Every old projection in a loaded document (``projections:``, or a body alone) rewritten; how many."""
    n = 0
    if isinstance(data, dict) and isinstance(data.get("projections"), dict):
        ps = data["projections"]
        for name in list(ps):
            if is_old(ps[name]):
                ps[name] = convert(ps[name])
                n += 1
    return n


def convert_text(text: str, body: bool = False) -> str | None:
    y = _yaml()
    try:
        data = y.load(text)
    except Exception:
        return None
    if body:
        if not is_old(data) or not any(k in data for k in ("match", "events")) or len(data) < 2:
            return None
        data = convert(data)
    elif not convert_doc(data):
        return None
    buf = io.StringIO()
    y.dump(data, buf)
    out = buf.getvalue()
    if not text.endswith("\n"):
        out = out.rstrip("\n")
    lead = text[:len(text) - len(text.lstrip("\n"))]
    return lead + out


def _indent_of(text: str) -> int:
    ls = [x for x in text.split("\n") if x.strip()]
    return min((len(x) - len(x.lstrip(" ")) for x in ls), default=0)


def convert_string(s: str) -> str | None:
    if "projections:" not in s and not re.search(r"^\s*(match|states|otherwise):", s, re.M):
        return None
    if re.search(r"(?<!\{)\{[A-Za-z_][A-Za-z0-9_]*\}(?!\})", s):     # a format string: its fields kept
        fmt = "{{" in s
        t = s.replace("{{", "\x01").replace("}}", "\x02") if fmt else s
        t = re.sub(r"^(\s*)\{([A-Za-z_][A-Za-z0-9_]*)\}\s*$", r"\1# __FMTLINE_\2__", t, flags=re.M)
        t = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", r"__FMT_\1__", t)
        if fmt and ("{" in t or "}" in t):
            return None
        t = t.replace("\x01", "{").replace("\x02", "}")
        got = _plain(t)
        if got is None:
            return None
        if fmt:
            got = got.replace("{", "{{").replace("}", "}}")
        got = re.sub(r"# __FMTLINE_([A-Za-z_][A-Za-z0-9_]*)__", r"{\1}", got)
        return re.sub(r"__FMT_([A-Za-z_][A-Za-z0-9_]*)__", r"{\1}", got)
    return _plain(s)


def _plain(s: str) -> str | None:
    pad = _indent_of(s)
    src = "\n".join(x[pad:] if x.strip() else x.strip() for x in s.split("\n")) if pad else s
    got = convert_text(src) if "projections:" in src else convert_text(src, body=True)
    if got is None and re.search(r"^projections:", src, re.M):     # the rest does not parse: the section alone
        ls = src.split("\n")
        i = next(n for n, x in enumerate(ls) if re.match(r"^projections:", x))
        j = next((n for n in range(i + 1, len(ls)) if ls[n].strip() and not ls[n].startswith((" ", "#"))), len(ls))
        part = convert_text("\n".join(ls[i:j]) + "\n")
        if part is not None:
            got = "\n".join(ls[:i] + part.rstrip("\n").split("\n") + ls[j:])
    if got is None:
        return None
    if pad:
        got = "\n".join((" " * pad + x) if x.strip() else x for x in got.split("\n"))
    return got


def convert_py(path: str) -> tuple[int, int]:
    src = open(path).read()
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    lines = src.splitlines(keepends=True)
    offs = [0]
    for ln in lines:
        offs.append(offs[-1] + len(ln))
    edits, failed = [], 0
    for t in toks:
        if t.type != tokenize.STRING:
            continue
        text = t.string
        m = re.match(r"^([rRbBuU]*)('''|\"\"\"|'|\")", text)
        if not m or "f" in m.group(1).lower() or "b" in m.group(1).lower():
            continue
        try:
            val = ast.literal_eval(text)
        except Exception:
            continue
        if not isinstance(val, str):
            continue
        new = convert_string(val)
        if new is None:
            if "projections:" in val and re.search(r"^\s*(match|states|otherwise):", val, re.M):
                failed += 1
            continue
        pre, q = m.group(1), m.group(2)
        body = text[len(pre) + len(q):-len(q)]
        if body != val and not (body.startswith("\\\n") and body[2:] == val):
            if len(q) == 1 and "r" not in pre.lower():      # a one-line string with escapes: written again so
                enc = new.replace("\\", "\\\\").replace("\n", "\\n").replace(q, "\\" + q)
                start = offs[t.start[0] - 1] + t.start[1]
                end = offs[t.end[0] - 1] + t.end[1]
                edits.append((start, end, pre + q + enc + q))
                continue
            failed += 1
            continue
        cont = "\\\n" if body.startswith("\\\n") else ""
        if len(q) == 1 and "\n" in new:
            q = q * 3
        if q in new:
            failed += 1
            continue
        start = offs[t.start[0] - 1] + t.start[1]
        end = offs[t.end[0] - 1] + t.end[1]
        edits.append((start, end, pre + q + cont + new + q))
    for start, end, rep in reversed(edits):
        src = src[:start] + rep + src[end:]
    if edits:
        open(path, "w").write(src)
    return len(edits), failed


def convert_yaml_file(path: str) -> int:
    text = open(path).read()
    got = convert_text(text)
    if got is None:
        return 0
    open(path, "w").write(got)
    return 1


def main():
    for p in sys.argv[1:]:
        if p.endswith(".py"):
            n, f = convert_py(p)
        else:
            n, f = convert_yaml_file(p), 0
        if n or f:
            print(f"{p}: {n} rewritten" + (f", {f} NOT (by hand)" if f else ""))


if __name__ == "__main__":
    main()
