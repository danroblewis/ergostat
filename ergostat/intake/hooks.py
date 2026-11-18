"""A webhook's payload made into events (``intake: hooks:``, config.py): ``POST /api/hooks/NAME``.

A mapping names, for the sender NAME, the event type (a template, or a value in the payload looked up in a map: one
not in the map is ignored, so a sender's other events are left out), the item (a template), an ``id`` (a template,
so a delivery sent twice is one event), and ``data``: each field a path in the payload (its value as it is: text,
number, list) or a template (text). A path is dotted keys (``issue.fields.summary``), list positions by number
(``pull_requests.0.number``), or ``header:NAME`` for a request header (``header:X-GitHub-Event``). A template is
text with ``{path}`` in it. ``each: PATH``: one event per element of that list, each element the payload."""

from __future__ import annotations

import re

from .envelope import Refused

PART = re.compile(r"\{([^{}]+)\}")
MISSING = object()


def lookup(payload, path: str, headers=None):
    path = path.strip()
    if path.startswith("header:"):
        v = (headers or {}).get(path[7:].strip()) if headers is not None else None
        return MISSING if v is None else v
    cur = payload
    for k in path.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        elif isinstance(cur, list) and k.isdigit() and int(k) < len(cur):
            cur = cur[int(k)]
        else:
            return MISSING
    return cur


def fill(template: str, payload, headers=None, strict: bool = True) -> str | None:
    """A template filled; None when a ``{path}`` it needs is not in the payload (``strict``), else left empty."""
    gone = []

    def one(m):
        v = lookup(payload, m.group(1), headers)
        if v is MISSING or v is None:
            gone.append(m.group(1))
            return ""
        return str(v)
    out = PART.sub(one, template)
    return None if gone and strict else out


def events(hook, payload, headers=None) -> tuple[list[dict], list[str]]:
    """The events a payload makes, and why any part of it was left out."""
    if hook.each:
        got = lookup(payload, hook.each, headers)
        payloads = got if isinstance(got, list) else []
    else:
        payloads = [payload]
    out, left = [], []
    for one in payloads:
        if hook.event_from:
            v = lookup(one, hook.event_from, headers)
            t = hook.event_map.get(str(v)) if v is not MISSING else None
            if t is None:
                left.append(f"{hook.event_from} = {v if v is not MISSING else 'nothing'}: not one {hook.name} maps to an event")
                continue
            t = fill(t, one, headers)
        else:
            t = fill(hook.event or "", one, headers)
        if not t:
            left.append(f"event: {hook.event} needs what the payload does not have")
            continue
        e = {"event": t, "source": hook.source or hook.name}
        if hook.item:
            item = fill(hook.item, one, headers)
            if item is None:
                raise Refused(f"item: {hook.item} needs what the payload does not have")
            e["item"] = item
        if hook.id:
            i = fill(hook.id, one, headers)
            if i:
                e["id"] = i
        data = {}
        for k, v in hook.data.items():
            got = fill(v, one, headers, strict=False) if "{" in v else lookup(one, v, headers)
            if got is not MISSING:
                data[k] = got
        e["data"] = data
        out.append(e)
    return out, left
