"""The page as one file: every answer the page would ask the server for, taken now and written into
a copy of the page with its scripts and style inline. It opens anywhere, offline, with no ergostat
running: a diagram to attach to a document or a ticket, and everything behind it."""

from __future__ import annotations

import base64
import json
import re
import time
from urllib.parse import quote

from .server import STATIC, Live, api

SKIP = {"since", "at"}            # one window, one moment: the snapshot's own


def key(path: str, params: dict) -> str:
    """The lookup key for one request, the same as the page's (``util.js``)."""
    kept = sorted((k, str(v)) for k, v in params.items() if k not in SKIP and v not in (None, "", "undefined"))
    return path + ("?" + "&".join(f"{k}={v}" for k, v in kept) if kept else "")


def _q(name: str) -> str:
    """As the page's encodeURIComponent: it leaves !'()* alone."""
    return quote(name, safe="!'()*")


def _requests(project) -> list[tuple[str, dict]]:
    m = project.model
    reqs: list[tuple[str, dict]] = [("status", {}), ("loops", {}), ("agents", {}), ("items", {}), ("residuals", {}),
                                    ("parts", {}), ("guide", {}), ("graph", {}), ("events", {"n": 80}), ("events", {"n": 80, "runs": 1})]
    for view in ("dynamics", "control", "blocks", "wiring"):
        for system in [None, *m.system_names()]:
            reqs.append(("graph", {"view": view, **({"system": system} if system else {})}))
            if view in ("dynamics", "control", "blocks") and getattr(m, "spec", None) is not None:   # every system opened
                reqs.append(("graph", {"view": view, "open": "*", **({"system": system} if system else {})}))
    reqs += [(f"loops/{_q(n)}", {}) for n in m.controllers]
    reqs += [(f"agents/{_q(n)}", {}) for n in m.agents]
    for kind, table in m.tables().items():
        for n in table:
            k = "disturbance" if kind == "flow" and getattr(table[n], "disturbance", False) else kind
            reqs.append((f"part/{k}/{_q(n)}", {}))
    return reqs


def _strip(x) -> None:
    """Every ``unread_lines`` (lines an agent printed that were not understood) taken out, wherever it is."""
    if isinstance(x, dict):
        x.pop("unread_lines", None)
        for v in x.values():
            _strip(v)
    elif isinstance(x, list):
        for v in x:
            _strip(v)


def build(project, since: str = "1h", logs: bool = False) -> str:
    """``logs``: the end of each agent's log goes in too (left out by default: a log may hold what
    should not be sent on)."""
    live = Live(project)
    data: dict = {"projects": []}
    for path, params in _requests(project):
        q = {"since": [since], **{k: [str(v)] for k, v in params.items()}}
        try:
            got = api(live, path, q)
        except Exception:                      # one part that cannot be answered leaves the rest
            got = None
        if got is not None:
            if path.startswith("agents/") and not logs:
                got["log"] = ["(left out of this snapshot: ergostat snapshot --with-logs puts it in)"]
                got.pop("log_path", None)
            data[key(path, params)] = got
    for it in ((data.get("items") or {}).get("items") or [])[:40]:
        got = api(live, f"items/{_q(it['id'])}", {"since": [since]})
        if got is not None:
            data[f"items/{_q(it['id'])}"] = got
    if not logs:                                  # what an agent printed but ergostat could not read is its log too
        _strip(data)
    snap = {"at": time.time(), "since": since, "name": project.model.name, "data": data}

    def inline(text: str) -> str:
        text = re.sub(r"</(script)", r"<\\/\1", text, flags=re.I)    # nothing in a script may close it early,
        text = re.sub(r"<(script)", r"\\x3c\1", text, flags=re.I)    # nor look like one opening (in a string or regex, \x3c is <)
        return text.replace("<!--", "<\\!--")                          # nor open a comment that hides its end

    page = (STATIC / "index.html").read_text()
    page = page.replace('<link rel="stylesheet" href="/static/style.css">',
                        "<style>\n" + (STATIC / "style.css").read_text() + "\n</style>")
    # every < in the data as \u003c: no tag, comment or script end can form inside the script
    snapshot_js = "window.SNAPSHOT = " + json.dumps(snap, default=str).replace("<", "\\u003c") + ";"

    def script(mt: re.Match) -> str:
        body = inline((STATIC / mt.group(1)).read_text())
        before = f"<script>{snapshot_js}</script>\n" if mt.group(1) == "elk.bundled.js" else ""
        if mt.group(1) == "avoid.js":             # the line router too, as data: a page opened from a file cannot fetch it
            lib = STATIC / "libavoid"
            before += ("<script>window.LIBAVOID = " + json.dumps({"js": base64.b64encode((lib / "libavoid.js").read_bytes()).decode(),
                       "wasm": base64.b64encode((lib / "libavoid.wasm").read_bytes()).decode()}) + ";</script>\n")
        return before + "<script>" + body + "</script>"
    return re.sub(r'<script src="/static/([\w.]+)"></script>', script, page)
