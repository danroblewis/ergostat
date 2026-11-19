"""The web page's HTTP server (standard library, bound to 127.0.0.1; read only but for the owner accepting or dismissing a
proposal, or confirming, dismissing or superseding a decision, ``POST``). ``/`` is the page;
``/api/*`` returns what the command line shows, as JSON; ``/static/*`` the page's files; ``/file/PATH`` a file
an item names; every other address of the page (``/items``, ``/item/ID``, ``/diagram?view=blocks``) is the page. The model is re-read when
``ergostat.toml`` changes, so the page follows the Supervisor's edits."""

from __future__ import annotations

import hashlib
import html
import json
import mimetypes
import re
import secrets
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .. import graph, history, series
from .. import model as mdl
from .. import state as st
from ..series import off_stretches
from ..spec.item_sets import BadSet

STATIC = Path(__file__).parent / "static"
GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)    # the client went away mid-answer
EVENTS_MOST = 1000                   # the most events one answer carries (``n``); page through with ``after``
FILE_LIMIT = 20 * 1024 * 1024        # a file an item names is shown up to this size
# the page's own addresses (/items, /item/ID, /diagram?view=blocks): each is the page, which draws what the path
# names; the same list as the page's (``UI_PAGES``, util.js). /api, /static and /file are never among them
UI_PAGES = ("diagram", "loops", "agents", "items", "item", "record", "model", "check", "guide", "fit", "residuals")


_VERSIONS: dict = {}                 # a static file's version, by name: (mtime, size, hash of its content)
_STATIC_REF = re.compile(r'((?:src|href)=")/static/([\w./-]+)(")')
FOREVER = "public, max-age=31536000, immutable"


def asset_version(name: str) -> str | None:
    """A static file's version: a hash of its content, kept until the file changes (its mtime or size). The page
    references every file with it (``/static/NAME?v=VERSION``), so an update changes the address the browser asks
    for, and a file asked for with its current version may be kept by the browser for good."""
    f = STATIC / name
    try:
        st_ = f.stat()
    except OSError:
        return None
    got = _VERSIONS.get(name)
    if got and got[:2] == (st_.st_mtime_ns, st_.st_size):
        return got[2]
    v = hashlib.blake2b(f.read_bytes(), digest_size=6).hexdigest()
    _VERSIONS[name] = (st_.st_mtime_ns, st_.st_size, v)
    return v


def versioned(name: str) -> str:
    """The address of a static file, with its version."""
    v = asset_version(name)
    return f"/static/{name}?v={v}" if v else f"/static/{name}"


def with_versions(page: str) -> str:
    """A page with every ``/static/`` file it loads given its version, and the versions of the files the
    scripts load themselves (libavoid's module and WebAssembly, in its worker) as a meta tag they read."""
    page = _STATIC_REF.sub(lambda m: m.group(1) + versioned(m.group(2)) + m.group(3), page)
    late = {n: asset_version(n) for n in ("libavoid/libavoid.js", "libavoid/libavoid.wasm")}
    meta = f'<meta name="ergostat-assets" content="{html.escape(json.dumps(late))}">'
    return page.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n' + meta, 1)


def is_page_path(path: str) -> bool:
    """``path`` (as sent, still encoded) is one of the page's own addresses: the root, or under one of UI_PAGES."""
    return path in ("", "/") or path.split("/")[1] in UI_PAGES


def went_away(path: str, size: int, e: BaseException) -> None:
    """A client that hung up before its answer was written: one quiet line on stderr (the runner's log)."""
    import sys
    print(f"{time.strftime('%H:%M:%S')} web: the client went away before {path.split('?')[0]} was sent "
          f"({size // 1024} KB, {type(e).__name__})", file=sys.stderr, flush=True)


def md_page(name: str, text: str) -> bytes:
    """A Markdown file opened in the browser, rendered with the page's own Markdown and styles: raw HTML in
    it is shown as text, never run; its relative links stay relative, so they open the files beside it."""
    data = json.dumps(text).replace("<", "\\u003c")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(name)}</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body class="file-page"><main class="md" id="doc"></main>
<script src="/static/marked.min.js"></script><script src="/static/highlight.min.js"></script>
<script>
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}})[c]);
marked.use({{ renderer: {{ html: (t) => esc(typeof t === "string" ? t : t.text || "") }} }});
const el = document.getElementById("doc");
el.innerHTML = marked.parse({data});
for (const a of el.querySelectorAll('a[href^="#/"]')) a.setAttribute("href", a.getAttribute("href").slice(1));   // an old page address
for (const c of el.querySelectorAll("pre code")) {{ try {{ hljs.highlightElement(c); }} catch (e) {{}} }}
</script></body></html>"""
    return with_versions(page).encode()


class Live:
    """The project, with its model re-read when the file changes."""

    def __init__(self, project):
        import threading
        self.p = project
        self.mtime = self._mtime()
        self._lock = threading.Lock()
        self._snaps: dict = {}
        self._making: dict = {}            # snapshots being made: one at a time for each moment, however many ask
        self._kept: dict = {}

    def cached(self, key):
        with self._lock:
            return self._kept.get(key)

    def keep(self, key, value) -> None:
        with self._lock:
            if len(self._kept) > 16:
                self._kept.clear()
            self._kept[key] = value

    def reloaded(self) -> None:
        """The model was changed here (a proposal accepted): take it as the one loaded."""
        self.mtime = self._mtime()
        history.note(self.p)

    def _mtime(self):
        return mdl.stamp(self.p.model)

    def snapshot(self, p, window: float, at: float | None):
        """The state, shared by the requests of one moment: the page asks for several parts of it
        every few seconds, and each would otherwise estimate it all again. Kept 1.5s; a past
        moment (``at``) is kept until the model changes. Made once however many ask at once: on a
        long record, requests that each made their own (and kept making it after their clients gave
        up) were what left every later answer waiting."""
        key = (window, at, self.mtime)
        import threading
        while True:
            with self._lock:
                got = self._snaps.get(key)
                if got and (at is not None or time.time() - got[0] < 1.5):
                    return got[1]
                busy = self._making.get(key)
                if busy is None:                       # this request makes it; the others asking meanwhile wait for it
                    busy = self._making[key] = threading.Event()
                    break
            busy.wait(120)
        try:
            snap = st.snapshot(p, window, at)
            with self._lock:
                if len(self._snaps) > 32:
                    self._snaps.clear()
                self._snaps[key] = (time.time(), snap)
            return snap
        finally:
            with self._lock:
                self._making.pop(key, None)
            busy.set()

    def get(self):
        now = self._mtime()
        if now != self.mtime:
            try:
                self.p.model = mdl.load(self.p.model.path.parent)
                self.mtime = now
                history.note(self.p)
            except Exception:
                pass                                   # keep the last model that loaded
        return self.p


def _window(q) -> float:
    from ..durations import parse_duration
    try:
        return parse_duration(q["since"][0]) if q.get("since") else st.WINDOW
    except ValueError:
        return st.WINDOW


def _tail(path, n: int) -> list[str]:
    """The last ``n`` lines of a file, read from its end."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 65536))
            return f.read().decode(errors="replace").splitlines()[-n:]
    except OSError:
        return []


def _lease_of(fields: dict) -> dict:
    """An item's lease, as its row shows it (SPEC §9.5): who holds it, until when, its attempts; not its history."""
    lease = fields.get("lease")
    if not isinstance(lease, dict):
        return {}
    return {"lease": {k: v for k, v in lease.items() if k != "history"}}


def _as_listed(got: dict, needle: str | None, per_kind: int, shown: bool, hide: str | None = None) -> dict:
    """The Items page's list: only the items matching its search (``q``, in the id or any field), the
    newest ``per_kind`` of each kind (how many matched is ``matched``), and with ``shown`` each item's
    fields cut to its kind's columns. A kind whose items carry large fields (the model's changes)
    otherwise made every refresh of the list hundreds of KB, most of it never shown. The systems in
    ``hide`` (comma-separated: the page's collapsed groups) send no items, only their kinds' counts."""
    items = got["items"]
    if hide:
        gone = set(hide.split(","))
        items = [i for i in items if i.get("system") not in gone]
    if needle:
        low = needle.strip().lower()
        text = lambda i: i["id"] + " " + json.dumps(i["fields"], separators=(",", ":"), ensure_ascii=False, default=str)   # noqa: E731
        items = [i for i in items if low in text(i).lower()]
    matched: dict[str, int] = {}
    kept = []
    for i in items:
        k = i.get("kind") or ""
        matched[k] = matched.get(k, 0) + 1
        if not per_kind or matched[k] <= per_kind:
            kept.append(i)
    if shown:
        show = {k["name"]: set(k["show"]) for k in got["kinds"]}
        kept = [{**i, "fields": {**{f: v for f, v in i["fields"].items() if f in show.get(i.get("kind") or "", ())},
                                 **_lease_of(i["fields"])}} for i in kept]
    return {**got, "items": kept, "matched": matched, "listed": len(got["items"])}


def inferred_of(spec, kind: str, name: str | None) -> dict | None:
    """Whether a model change added this part (``inferred:``, SPEC §12e), and which: ``{"from": item or None}``, or None
    for a part the YAML declares. What the side panel says, subtly: "added by ergostat, from model change X"."""
    if spec is None or name is None:
        return None
    x = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries,
         "parameter": spec.parameters}.get(kind, {}).get(name)
    if x is None and kind == "stock":                       # an auxiliary is opened as a level, like a stock
        x = spec.auxiliaries.get(name)
    v = getattr(x, "inferred", None)
    if not v:
        return None
    return {"from": v if "/" in v else None}


def _items_of(p, m, kind: str, name: str, snap: dict) -> dict | None:
    """A part's items, for its side panel (``item_sets.of_part``): a stock's now, a flow's in the window. A sensor's
    are its part's."""
    from ..spec import item_sets
    spec = getattr(m, "spec", None)
    if spec is None:
        return None
    if kind == "sensor":
        s = next((x for x in spec.sensors() if f"{x.of.name}.{x.name}" == name), None)
        if s is None:
            return None
        kind, name = s.of.kind, s.of.name
    elif kind == "stock" and name in spec.auxiliaries:
        kind = "auxiliary"
    elif kind == "disturbance":
        kind = "flow"
    got = item_sets.of_part(spec, kind, name, snap["at"] - snap["window"], snap["at"], m)
    got["of"] = {"kind": kind, "name": name}
    if "events" in got:
        got["events"] = {**got["events"], **item_sets.events_items(p.events, got["events"],
                                                                   snap["at"] - snap["window"], snap["at"])}
    return got


def _process(p, m, snap: dict, q: dict, system: str | None) -> dict:
    """The Process view (``process.py``): the kinds asked for (``kinds``, joined by commas), else the system's;
    ``by`` states or events; ``paths``, the frequency filter, a percentage."""
    from .. import process as pm
    spec = getattr(m, "spec", None)
    if spec is None or not getattr(spec, "items", None):
        return {"kind": "process", "by": "states", "paths": 0, "kinds": [], "nodes": [], "edges": [], "events": 0,
                "since": snap["at"] - snap["window"], "until": snap["at"], "capped": {}, "hidden": {"nodes": 0, "edges": 0},
                "total": {"nodes": 0, "edges": 0}, "offered": [], "default": []}
    one = lambda k: (q.get(k) or [None])[0]       # noqa: E731
    offered = pm.kinds_of(spec, system)
    asked = [k for k in (one("kinds") or "").split(",") if k in spec.items]
    try:
        share = max(0.0, min(100.0, float(one("paths") or 0))) / 100
    except ValueError:
        share = 0.0
    got = pm.process(p.events, spec, asked or offered, snap["at"] - snap["window"], snap["at"], one("by"), share)
    from ..spec.item_systems import kind_systems
    where = kind_systems(spec)
    got["offered"] = [{"name": k, "system": where.get(k, {}).get("system"), "states": bool(spec.items[k].states)}
                      for k in spec.items]
    got["default"] = offered
    return got


def api(live: Live, path: str, q: dict):
    """An answer; a graph's with its correspondence (``correspond.py``): which model parts each
    shape is, and which shapes stand for each part, so one selection is lit in every view."""
    got = _answer(live, path, q)
    if path.strip("/") == "graph" and isinstance(got, dict):
        from ..correspond import table
        got["corr"] = table(got, live.get().model)
        if q.get("have"):                             # a page polling: only the values, when it holds this structure
            from .graph_poll import answer
            return answer(got, q["have"][0])
    return got


def _answer(live: Live, path: str, q: dict):
    p = live.get()
    m = p.model
    one = lambda k: (q.get(k) or [None])[0]       # noqa: E731
    parts = path.strip("/").split("/")
    head, name = parts[0], unquote(parts[1]) if len(parts) > 1 else None
    at = None
    if one("at"):
        try:
            at = float(one("at"))
        except ValueError:
            at = None
    snap = live.snapshot(p, _window(q), at)
    if head == "status":
        from .. import rates
        from ..runner import running_pid
        running = bool(running_pid(p))
        return {"name": m.name, "running": running, "live": snap["live"], "first": p.events.first_time(),
                "attention": st.attention(snap, running and snap["live"], m), "loops": snap["loops"],
                "counts": {"loops": len(m.controllers), "stocks": len(m.stocks), "flows": len(m.flows),
                           "agents": len(m.agents), "events": p.events.count(), "measurements": p.measurements.count()},
                "systems": m.system_names(), "check": [{"level": lv, "message": msg} for lv, msg in mdl.check(m)],
                "at": snap["at"], "window": snap["window"], "rate_units": rates.overrides(getattr(m, "spec", None)),
                "changes": [{"time": e["time"], **{k: e["data"][k] for k in ("added", "removed", "changed")}}
                            for e in history.changes(p, snap["at"] - snap["window"])][-5:]}
    if head == "projects":
        from ..projects import known
        return known()
    if head == "coherence":                          # the three views held against each other (the Check page)
        from .numbers_api import coherence
        return coherence(live, p, snap, _window(q) if one("since") else None)
    if head == "exercised":                          # the parts the record has not exercised: findings, for the Check page
        from .numbers_api import exercised
        return exercised(live, p, snap)
    if head == "guide":                              # the Guide's frames: tiny models, the same for every project
        from ..guide import frames
        return frames()
    if head == "graph":
        system = one("system") or None
        around = one("around") or None
        from ..runner import running_pid
        att = st.attention(snap, bool(running_pid(p)) and snap["live"], m)
        if one("view") in ("process", "wiring"):    # the process map (the wiring it replaced still reaches it)
            # read again every 5s at most (on a long record it takes a second); a past moment's, kept
            key = ("process", snap["window"], snap["at"] if at is not None else int(time.time() // 5), live.mtime,
                   system, one("kinds"), one("by"), one("paths"))
            got = live.cached(key)
            if got is None:
                got = _process(p, m, snap, q, system)
                live.keep(key, got)
            return {**got, "attention": att}
        if one("view") == "blocks":                 # the control view: the whole control system as a block diagram
            from ..blockdiagram import diagram
            opened = q.get("open")
            want = None if opened is None else {x for x in (opened[0] or "").split(",") if x}
            return {**diagram(m, snap, want, system), "attention": att}
        from ..dynamics import attention as sd_attention
        from ..dynamics import dynamics, finish
        from ..fold import fold
        sd = one("view") == "dynamics"          # the system dynamics view: drawn from the same graph
        if sd:
            att = sd_attention(att, snap)       # (in its own words)
        tree = getattr(getattr(m, "spec", None), "systems", None)
        if tree and not around:              # systems as parts: boxed, opened, or drilled into (whatever it reaches outside)
            g = graph.control(m, snap, graph.select(m), graph.readings(p, at))
            opened = q.get("open")
            want = None if opened is None else {x for x in (opened[0] or "").split(",") if x}
            if sd:
                return {**finish(fold(dynamics(g, m), m, want, system)), "attention": att}
            return {**fold(g, m, want, system), "attention": att}
        sel = graph.select(m, system, around, int(one("depth") or 1))
        g = graph.control(m, snap, sel, graph.readings(p, at))
        return {**(dynamics(g, m) if sd else g), "attention": att}
    if head == "systems":
        return [{"name": s, "description": m.systems[s].description if s in m.systems else "",
                 "parts": len(m.members(s)), "loops": [n for n in snap["loops"] if n in m.members(s)]}
                for s in m.system_names()]
    if head == "loops":
        if name:
            lp = snap["loops"].get(name)
            if lp is None:
                return None
            since = snap["at"] - snap["window"]
            stock_pts = st.history(p, lp["stock"], since, snap["at"])
            step = max(1, len(stock_pts) // 300)
            # the whole window, reduced: every opening's time thinned evenly, the off stretches from every crossing
            openings = sorted(({"time": e["time"], "amount": e["data"].get("amount"), "valve": e["item"]}
                               for v in lp["valves"] for e in p.events.query(n=None, type="valve.opened", item=v, since=since,
                                                                               until=snap["at"])), key=lambda o: o["time"])
            n_open = len(openings)
            openings = openings[::max(1, n_open // 300)]
            crossings = st.crossings_of(p, name, since, snap["at"])
            stretches = off_stretches(p, name, since, snap["at"])
            in_window = [e for e in crossings if e["time"] >= since]
            c = m.controllers[name]
            agent = lambda a: ({"name": a, "kind": m.agents[a].kind, "rung": m.agents[a].rung}       # noqa: E731
                               if a in m.agents else None)
            parts = []
            for s_ in lp["sensors"]:
                got = p.measurements.latest(f"sensor/{s_}", snap["at"])
                parts.append({"kind": "sensor", "name": s_, "agent": agent(m.sensors[s_].agent),
                              "last": {"time": got[0], "value": got[1]} if got else None})
            parts.append({"kind": "controller", "name": name, "agent": agent(c.agent), "open_loop": c.open_loop,
                          "last": lp["last_decision"]})
            for v in lp["valves"]:
                parts.append({"kind": "valve", "name": v, "agent": agent(m.valves[v].agent), "mode": m.valves[v].mode,
                              "max": m.valves[v].max, "last": p.events.last_opening(v, snap["at"])})
            return {**lp, "points": stock_pts[::step], "openings": openings, "openings_total": n_open,
                    "since": since, "until": snap["at"], "off_stretches": stretches,
                    "crossings": in_window[-20:], "crossings_total": len(in_window),
                    "description": c.description, "parts": parts,
                    "rates": {f: snap["flows"].get(f, {}).get("rate") for f in lp["flows"]},
                    "decisions": st.decisions(p, name, since, snap["at"]),
                    "hints": [h for h in snap["hints"] if h["controller"] == name]}
        return snap["loops"]
    if head == "agents":
        if name:
            a = m.agents.get(name)
            if a is None:
                return None
            runs = [e for e in p.events.query(n=400, item=name, type="agent.*", until=snap["at"])
                    if e["type"] in ("agent.ran", "agent.failed")]
            from ..runner import log_path
            log = log_path(p, name)
            from ..costs import record as costs
            return {"agent": {**a.__dict__, "rung": a.rung}, **snap["agents"][name], "recent": runs[-80:],
                    "log": _tail(log, 40), "log_path": str(log),
                    "loads": [f.name for f in m.flows.values() if f.disturbance and f.agent == name],
                    "use": costs.of_block(p, name, snap["at"] - snap["window"], snap["at"])}   # what its runs cost (§9.1)
        from ..costs import record as costs
        use = costs.per_block(p, snap["at"] - snap["window"], snap["at"])
        return {n: {**a, "hints": [h for h in snap["hints"] if h["agent"] == n], **({"use": use[n]} if n in use else {})}
                for n, a in snap["agents"].items()}
    if head == "events":
        if name:                                  # one event, by id
            return p.events.get(name)
        after = one("after")
        skip = () if one("runs") or one("type") else ("agent.started", "agent.ran")   # as `ergostat event`
        if not one("type") and not one("item"):   # a transcript's lines are on its item's page, asked by type or item
            skip = (*skip, "claude.*")
        before = one("before")
        return p.events.query(n=max(1, min(int(one("n") or 100), EVENTS_MOST)), type=one("type"), item=one("item"),
                              source=one("source"), machine=one("machine"), after_seq=int(after) if after else None,
                              before_seq=int(before) if before else None, skip=skip,
                              **({"since": snap["at"] - snap["window"], "until": snap["at"]} if one("window") else {}))
    if head == "items":
        from ..spec import items as its
        spec = getattr(m, "spec", None)
        if name and one("archived"):            # its full history: the events rolled up into its snapshot, a page at a time
            from ..rollup import archived
            return archived(p, name, offset=int(one("offset") or 0), n=min(int(one("n") or 200), EVENTS_MOST))
        if name:
            return its.detail(p.events, spec, name, until=snap["at"],
                              history=None if one("history") == "all" else its.HISTORY_SHOWN)
        from ..spec import item_sets
        n, offset = max(1, min(int(one("n") or its.LISTED), its.LISTED)), int(one("offset") or 0)
        want = item_sets.parse(q, snap["at"]) if one("kind") and (one("state") or one("alone") or item_sets.asked(q)) else None
        if want is not None and (item_sets.asked(q) or one("alone")):   # a set the listing does not serve (SPEC §5a)
            got = item_sets.select(p.events, spec, want, until=snap["at"], n=n, offset=offset)
            if one("alone"):                              # the side panel's list: the set, and nothing of the page
                k = spec.items[want.kind]
                return {**_as_listed({**got, "kinds": [{"name": k.name, "show": k.show}]}, None, 0, bool(one("shown"))),
                        "kinds": []}
            page = its.listing(p.events, spec, kind=want.kind, state="\0", until=snap["at"], n=1)   # its kinds and counts
            return _as_listed({**page, **got}, one("q"), int(one("per_kind") or 0), bool(one("shown")), one("hide"))
        got = its.listing(p.events, spec, kind=one("kind"), state=one("state"), until=snap["at"], n=n, offset=offset)
        if want is not None:
            got["set"] = {"says": want.says(), "params": want.params()}
        return _as_listed(got, one("q"), int(one("per_kind") or 0), bool(one("shown")), one("hide"))
    if head == "series":                          # behaviour over time: each part's values, bucketed over the window
        refs = [r for r in (one("refs") or "").split(",") if r]
        out = series.series(p, snap, refs, int(one("points") or series.POINTS), bool(one("strip")))
        if one("replay"):                         # and what the model says: its replay, and its projection past now
            from .numbers_api import add_to_series
            add_to_series(live, p, snap, out, one("inputs") or "hold", one("whatif"),
                          "replay" if one("fan") == "replay" else bool(one("fan")))
        return out
    if head == "dominance":                       # which feedback loops drive the behaviour, and when (Loops That Matter)
        from .numbers_api import loop_dominance
        return loop_dominance(live, p, snap, int(one("points") or series.POINTS), one("loop"))
    if head == "whatif-fit":                      # a what-if's fit before anything is stored: per stock, and its payoff
        from .numbers_api import whatif_fit
        return whatif_fit(live, p, snap, one("whatif"))
    if head == "proposal-effect":                 # proposals simulated, alone or all pending together: nothing written
        from .numbers_api import effect
        return effect(live, p, snap, one("ids"))
    if head == "fit":                             # the Model page: the replay against the record, its history, the proposals
        from .numbers_api import fit_page
        return fit_page(live, p, snap)
    if head == "loop-control":                    # the loop as a control engineer reads it: identified, analysed, monitored
        from .control_api import get as control
        return control(live, p, snap, one("goal") or "")
    if head == "loop-scope":
        return series.scope(p, snap, one("goal") or "", int(one("points") or series.POINTS))
    if head == "messages":                        # the owner's messages, about one item or all (SPEC §12h)
        from .messages_api import listing
        return listing(p, one("item") or None)
    if head == "actions":                         # gated actions sessions asked for, about one item or all (SPEC §12k)
        from .actions_api import listing as actions
        return actions(p, one("item") or None)
    if head == "trust":                           # how far blocks' claims hold, by block, rung and model (SPEC §12g)
        from ..claims import trust
        return trust.table(p, snap["at"] - max(snap["window"], trust.WEEK), snap["at"])
    if head == "verdicts":                        # finished work held to what the owner meant (SPEC §12i)
        from .verdicts_api import table as verdicts
        return verdicts(p, snap)
    if head == "items-flow":
        return series.items_flow(p, snap, one("kind") or "", int(one("points") or series.POINTS))
    if head == "residuals":
        return snap["residuals"]
    if head == "parts":
        rd = graph.readings(p, at)
        agent = lambda n: ({"name": n, "kind": m.agents[n].kind, "rung": m.agents[n].rung} if n in m.agents else None)  # noqa: E731
        return {
            "stock": [{"name": n, "value": snap["stocks"][n]["value"], "unit": x.unit, "points": snap["stocks"][n]["points"][-40:],
                       "sensor": snap["stocks"][n]["sensor"], "inflow": snap["stocks"][n]["inflow"],
                       "outflow": snap["stocks"][n]["outflow"],
                       "systems": x.systems} for n, x in m.stocks.items()],
            "flow": [{"name": n, "from": x.source, "to": x.target, "rate": snap["flows"][n]["rate"], "how": snap["flows"][n]["how"],
                      "valve": snap["flows"][n]["valve"]} for n, x in m.flows.items() if not x.disturbance],
            "disturbance": [{"name": n, "from": x.source, "to": x.target, "rate": snap["flows"][n]["rate"], "how": snap["flows"][n]["how"],
                             "estimated": snap["flows"][n]["estimated"]} for n, x in m.flows.items() if x.disturbance],
            "valve": [{"name": n, "flow": x.flow, "mode": x.mode, "agent": agent(x.agent), "position": rd.get(f"valve/{n}"),
                       "last": (snap["flows"].get(x.flow, {}).get("openings") or {}).get("last"),
                       "rate": snap["flows"].get(x.flow, {}).get("rate")} for n, x in m.valves.items()],
            "sensor": [{"name": n, "measures": x.measures, "agent": agent(x.agent), "reading": rd.get(n),
                        "at": (p.measurements.latest(f"sensor/{n}") or (None,))[0]} for n, x in m.sensors.items()],
            "controller": [{"name": n, "holds": x.holds, "setpoint": x.setpoint, "status": snap["loops"][n]["status"],
                            "agent": agent(x.agent), "open_loop": x.open_loop} for n, x in m.controllers.items()],
            "system": [{"name": s_, "description": m.systems[s_].description if s_ in m.systems else "", "parts": len(m.members(s_)),
                        "loops": [n for n in snap["loops"] if n in m.members(s_)],
                        "off": [n for n in snap["loops"] if n in m.members(s_) and snap["loops"][n]["status"] in ("off", "open")]}
                       for s_ in m.system_names()],
        }
    if head == "part":
        kind = name
        pname = unquote(parts[2]) if len(parts) > 2 else None
        table = m.tables().get("flow" if kind == "disturbance" else kind)
        if table is None or pname not in table:
            return None
        x = table[pname]
        out = {"kind": x.kind if not getattr(x, "disturbance", False) else "disturbance", "model": x.__dict__}
        out["inferred"] = (inferred_of(getattr(m, "spec", None), "flow", getattr(x, "flow", None)) if kind == "valve" else
                           inferred_of(getattr(m, "spec", None), "flow" if kind == "disturbance" else kind, pname))
        if kind == "stock":
            out["now"] = snap["stocks"].get(pname)
            if pname in getattr(getattr(m, "spec", None), "auxiliaries", {}):
                from .numbers_api import part_numbers
                out["numbers"] = part_numbers(live, p, snap, "auxiliary", pname)
        elif kind in ("flow", "disturbance"):
            out["now"] = snap["flows"].get(pname)
            if getattr(m, "spec", None) is not None:
                from ..dynamics import equation
                from ..spec.findings import unit_of
                from ..spec.ir import Ref
                from .numbers_api import part_numbers
                out["equation"] = equation(m.spec, pname)
                out["unit"] = unit_of(m.spec, Ref("flow", pname))       # what moves: its own unit, else its stocks'
                out["numbers"] = part_numbers(live, p, snap, "flow", pname)
        elif kind == "sensor":
            sid, since = f"sensor/{pname}", snap["at"] - snap["window"]
            out["now"] = {"readings": p.measurements.range(sid, since, snap["at"], last=60),
                          "count": p.measurements.count(sid, since, snap["at"])}
        elif kind == "valve":
            out["now"] = {"openings": p.events.query(n=300, type="valve.opened", item=pname),
                          "flow": snap["flows"].get(x.flow)}
        elif kind == "controller":
            out["now"] = {"loop": snap["loops"].get(pname),
                          "decisions": p.events.query(n=20, type="controller.decided", item=pname)}
        if kind in ("stock", "flow", "disturbance", "sensor"):   # what goes through it: its items (SPEC §5a, which items)
            out["items"] = _items_of(p, m, kind, pname, snap)
        agent = getattr(x, "agent", None)
        if agent and agent in m.agents:
            out["agent"] = {"name": agent, "kind": m.agents[agent].kind, "rung": m.agents[agent].rung}
        if kind in ("stock", "flow", "disturbance"):     # what the record says of it: not exercised, with its span
            from .numbers_api import exercised
            aux = pname in getattr(getattr(m, "spec", None), "auxiliaries", {})
            ref = f"{'auxiliary' if aux else 'stock' if kind == 'stock' else 'flow'}.{pname}"
            out["findings"] = [x for x in exercised(live, p, snap) if x["about"] == ref]
        return out
    return None


def handler(project):
    live = Live(project)
    token = secrets.token_urlsafe(24)                    # this run's: written into the page, asked of every write

    class Handler(BaseHTTPRequestHandler):
        timeout = 10                                   # an idle browser connection gives its thread back
        def log_message(self, *a):
            pass

        def _send(self, code: int, body: bytes, ctype: str, tagged: bool = False, cache: str = "no-cache"):
            """An answer; ``tagged`` (a GET's 200): with its ETag, and asked again by the browser with it each
            time (``no-cache``), so an answer that did not change since is a 304 with no body: the page
            refreshes every few seconds, and an item's images and files are drawn again each time. A static
            file asked for with its current version is kept for good instead (``cache``)."""
            try:
                tag = f'"{hashlib.blake2b(body, digest_size=12).hexdigest()}"' if tagged and code == 200 else None
                same = tag is not None and tag in (self.headers.get("If-None-Match") or "")
                self.send_response(304 if same else code)
                if tag:
                    self.send_header("ETag", tag)
                if not same:
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache if tag else "no-store")
                self.end_headers()
                if not same:
                    self.wfile.write(body)
            except GONE as e:                        # the page stopped waiting: a line in the log, not a traceback
                went_away(self.path, len(body), e)

        def _file(self, rel: str, page: bool = False):
            p = live.get()
            roots = [r.resolve() for r in (p.model.path.parent if p.model.path else None, p.dir) if r]
            for root in roots:
                f = (root / rel).resolve()
                if (root == f or root in f.parents) and f.is_file():
                    if f.stat().st_size > FILE_LIMIT:
                        return self._send(413, b"too big to show", "text/plain")
                    if page and f.suffix.lower() == ".md":     # opened in the browser: shown rendered, its relative links kept
                        return self._send(200, md_page(f.name, f.read_text(errors="replace")), "text/html; charset=utf-8")
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream", True)
            return self._send(404, b"not found", "text/plain")

        def _host_ok(self) -> bool:
            """Only a request addressed to this server by its own name: a page on another site whose
            name was pointed at 127.0.0.1 (DNS rebinding) sends its own name as the Host, and is refused."""
            port = self.server.server_address[1]
            return (self.headers.get("Host") or "").lower() in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

        def do_POST(self):
            """The page's one kind of write: the owner accepting or dismissing a proposal, asking for
            estimates, or sending the work a message. Only from the page itself: addressed to this server by its own name (the Host
            header), from its own origin (Origin, Sec-Fetch-Site), and carrying the token this run of the
            server wrote into the page it served, which no other page can read."""
            u = urlsplit(self.path)
            origin = self.headers.get("Origin")
            fetch_site = self.headers.get("Sec-Fetch-Site")
            if (not self._host_ok() or not u.path.startswith("/api/")
                    or (origin is not None and origin.lower() != f"http://{(self.headers.get('Host') or '').lower()}")
                    or (fetch_site is not None and fetch_site not in ("same-origin", "none"))
                    or not secrets.compare_digest(self.headers.get("X-Ergostat-Token") or "", token)):
                return self._send(403, b'{"error": "only the page may ask"}', "application/json")
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(min(n, 65536)) if n else b""
            from .numbers_api import post
            try:
                q = parse_qs(u.query)
                if u.path == "/api/message":                # the owner's words to the work in flight (SPEC §12h)
                    from .messages_api import post as message
                    code, data = message(live, q, body)
                elif u.path.startswith("/api/control/"):   # a loop's process, tuning or step test: the owner's answer
                    from .control_api import post as control
                    code, data = control(live, u.path.removeprefix("/api/"))
                elif u.path.startswith("/api/action/"):    # the owner's answer to a gated action held (SPEC §12k)
                    from .actions_api import post as action
                    code, data = action(live, u.path.removeprefix("/api/"), q)
                elif u.path.startswith("/api/verdict/"):   # the owner on the intent judge: overrule, reopen (SPEC §12i)
                    from .verdicts_api import post as verdict
                    code, data = verdict(live, u.path.removeprefix("/api/"), q)
                elif u.path.startswith("/api/intent/"):    # a proposed decision or correction: the owner's answer
                    from .intent_api import post as intent
                    code, data = intent(live, u.path.removeprefix("/api/"), q)
                else:
                    code, data = post(live, u.path.removeprefix("/api/"), _window(q), q)
            except Exception as e:                      # a broken request never takes the page down
                code, data = 500, {"error": f"{type(e).__name__}: {e}"}
            return self._send(code, json.dumps(data, default=str).encode(), "application/json")

        def do_GET(self):
            u = urlsplit(self.path)
            if not self._host_ok():                        # another site's name pointed here: nothing is read
                return self._send(403, b"not this server's name", "text/plain")
            if u.path.startswith("/api/"):
                try:
                    data = api(live, u.path.removeprefix("/api/"), parse_qs(u.query))
                except BadSet as e:                     # an Items filter that is not one: said, as the asker's
                    return self._send(400, json.dumps({"error": str(e)}).encode(), "application/json")
                except Exception as e:                  # a broken request never takes the page down
                    return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode(), "application/json")
                if data is None:
                    return self._send(404, b'{"error": "not found"}', "application/json")
                return self._send(200, json.dumps(data, default=str).encode(), "application/json", True)
            if u.path == "/file":                          # a file an item names (file:PATH), from inside the project only
                return self._file((parse_qs(u.query).get("path") or [""])[0])
            if u.path.startswith("/file/"):                # the same, as a path: a Markdown file's relative links resolve
                navigating = "text/html" in (self.headers.get("Accept") or "") and "raw" not in parse_qs(u.query)
                return self._file(unquote(u.path.removeprefix("/file/")), page=navigating)
            if is_page_path(u.path):
                name = "index.html"
            elif u.path.startswith("/static/"):
                name = u.path.removeprefix("/static/")
            else:
                return self._send(404, b"not found", "text/plain")
            f = (STATIC / name).resolve()
            if STATIC.resolve() not in f.parents or not f.is_file():
                return self._send(404, b"not found", "text/plain")
            if name == "index.html":                       # the page carries this run's token for its writes, and its files' versions
                body = with_versions(f.read_text()).replace('<meta charset="utf-8">',
                                                            f'<meta charset="utf-8">\n<meta name="ergostat-token" content="{token}">', 1)
                return self._send(200, body.encode(), "text/html; charset=utf-8", True)   # never kept stale: no-cache, ETag
            asked = (parse_qs(u.query).get("v") or [""])[0]
            cache = FOREVER if asked and asked == asset_version(name) else "no-cache"
            self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream", True, cache)

    Handler.live = live
    return Handler
