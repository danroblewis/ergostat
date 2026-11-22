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
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .. import graph, history, series
from .. import model as mdl
from .. import state as st
from ..remote.items import RemoteRefused
from ..reports.crash import noted as crash_noted
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

        from ..reload import Settled
        self.p = project
        self.mtime = self._mtime()
        self.watch = Settled(project.model)            # the files followed: taken once they settle (reload.py)
        self.errors: list[str] = []                    # the edited model's errors, while the last good one is shown
        self._loading = threading.Lock()               # one thread reads a changed model; the others answer meanwhile
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
        self.watch.took(self.p.model)
        self.errors = []
        self._note()

    def _note(self) -> None:
        """Record the model's change, unless a runner is there to: it says which runs carried over the change, and a
        record made here first (the same fingerprint) would leave it nothing to record."""
        from ..runner import running_pid
        if not running_pid(self.p, wait=False):
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
        """The project, its model the last good one. A change to the files is read once they have settled, by one
        request while the others answer with the model as it was: every request after an edit reading the model at
        once, each again while the file had errors, was what left the page with no answers (reload.py)."""
        due = self.watch.due()
        if due is not None and self._loading.acquire(blocking=False):
            try:
                due = self.watch.due()
                if due is not None:
                    from ..reload import load_checked
                    fresh, errors = load_checked(self.p.model)
                    if fresh is None:
                        self.watch.refused(due)
                        self.errors = errors
                    else:
                        self.p.model = fresh
                        self.watch.took(fresh, due)
                        self.mtime, self.errors = self._mtime(), []
                        self._note()
            except Exception:                          # keep the last model that loaded
                pass
            finally:
                self._loading.release()
        return self.p


def _edited(live: Live, p, running: bool) -> dict | None:
    """The edited model's errors, while the last good version runs (and is shown): the runner's, when one runs here,
    else the page's own."""
    from ..reload import banner, read_state
    got = read_state(p.dir) if running else None
    if got is None and live.errors:
        got = {"errors": live.errors, "banner": banner(live.errors)}
    if got is None:
        return None
    if not running:
        got = {**got, "banner": got["banner"].replace("still running", "still showing")}
    return {"errors": got["errors"], "banner": got["banner"]}


def _laws(p, spec) -> dict:
    """The external blocks' identified laws already fitted; a miss is fitted in a thread, and drawn on a later poll."""
    from ..numbers import external as ex
    if spec is None or not ex.blocks(spec):
        return {}
    got = ex.cached(p, spec)
    if got is None and p.dir not in _FITTING:
        _FITTING.add(p.dir)

        def fit():
            try:
                ex.laws(p, spec)
            except Exception:
                import logging
                logging.getLogger("ergostat").exception("identifying the external blocks' laws failed")
            finally:
                _FITTING.discard(p.dir)
        threading.Thread(target=fit, daemon=True, name="identify-laws").start()
    return {n: x["law"].as_dict() for n, x in (got or {}).items() if x["law"] is not None}


_FITTING: set = set()   # the projects whose laws are being fitted

# The header's project list (/api/projects): the running projects, worked out by one thread every LIST_EVERY seconds;
# a request reads the last list and loads nothing. Until the first is made: none, and stopped unknown (None).
LIST_EVERY = 60.0
_LISTED: dict = {"running": [], "stopped": None, "at": None}
_LISTER = threading.Lock()                     # held only to start or stop the one thread (per process)
_LISTING: dict = {"servers": set(), "stop": None, "thread": None}   # the page servers that need it, its stop, itself


def list_once(stop: threading.Event | None = None) -> None:
    """One pass: ``projects.running()`` into ``_LISTED``, unless ``stop`` was set while it ran. A pass that fails is
    logged and keeps the last list (the answer's ``age`` says how old it is, and the menu says so when it is old)."""
    global _LISTED
    from .. import projects
    try:
        got = projects.running()
    except Exception:
        import logging
        logging.getLogger("ergostat").exception("listing the running projects failed; the last list is kept")
        return
    if stop is None or not stop.is_set():
        _LISTED = got


def list_projects(stop: threading.Event, every: float = LIST_EVERY) -> None:
    """``list_once`` at once and then every ``every`` seconds, until ``stop``."""
    while not stop.is_set():
        list_once(stop)
        if stop.wait(every):
            return


def start_lister(server) -> None:
    """The one lister of this process runs while any of its page servers does (each calls ``stop_lister`` when it
    shuts down)."""
    with _LISTER:
        _LISTING["servers"].add(id(server))
        if _LISTING["thread"] is None:
            _LISTING["stop"] = threading.Event()
            _LISTING["thread"] = threading.Thread(target=list_projects, args=(_LISTING["stop"],),
                                                  name="ergostat-projects", daemon=True)
            _LISTING["thread"].start()


def stop_lister(server=None, wait: float = 10.0) -> bool:
    """``server`` no longer needs the lister (None: no server does). When none does, it is stopped and waited for: a
    pass running then is not kept. True when no lister runs any more (False: one outlasted ``wait``, or others need
    it)."""
    with _LISTER:
        if server is None:
            _LISTING["servers"].clear()
        else:
            _LISTING["servers"].discard(id(server))
        if _LISTING["servers"]:
            return False
        t, _LISTING["thread"] = _LISTING["thread"], None
        if t is None:
            return True
        _LISTING["stop"].set()
    if t is not threading.current_thread():
        t.join(wait)
    return not t.is_alive()


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
    from ..actions.record import ACTION, who
    items = [{**i, "fields": {**i["fields"], **who(i["fields"], i.get("state"))}} if i.get("kind") == ACTION else i for i in got["items"]]
    if hide:
        gone = set(hide.split(","))
        items = [i for i in items if i.get("system") not in gone]
    if needle:                                       # a kind's name (or plain title) matched keeps all of its items
        low = needle.strip().lower()
        named = {k["name"] for k in got["kinds"] if low in f"{k['name']} {k.get('title') or ''}".lower()}
        text = lambda i: i["id"] + " " + json.dumps(i["fields"], separators=(",", ":"), ensure_ascii=False, default=str)   # noqa: E731
        items = [i for i in items if i.get("kind") in named or low in text(i).lower()]
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


def _estimates(p, m, snap: dict, whatif: str | None) -> dict | None:
    """The completion estimates (``eta_api``), of now only: a moment travelled to has none."""
    if abs(time.time() - snap["at"]) >= 5:
        return None
    from .eta_api import estimates
    return estimates(p, m, whatif)


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
    if not asked and getattr(spec, "remotes", None):      # each remote's own map beside ours, marked remote (SPEC §4c)
        from ..remote.process import merge
        got = merge(spec, got, system, snap["at"] - snap["window"], one("by"))
    from ..spec.item_systems import kind_systems
    where = kind_systems(spec)
    got["offered"] = [{"name": k, "system": where.get(k, {}).get("system"), "states": bool(spec.items[k].states)}
                      for k in spec.items]
    got["default"] = offered
    return got


def _remote_events(spec, name, n, glob) -> dict:
    """A remote's newest events from its cache, in ``seq`` order, each marked; what failed said, never as none."""
    import fnmatch

    from ..remote import events, items
    items.remote(spec, name)
    kept, why = events.follow(spec, name)
    if kept is None:
        raise items.RemoteRefused(502, why)
    try:
        n = max(1, min(int(n or 100), EVENTS_MOST))
    except ValueError:
        n = 100
    evs = [{**e, "remote": name} for e in kept["events"] if not glob or fnmatch.fnmatchcase(str(e.get("type")), glob)]
    return {"remote": name, "ok": kept["ok"], "why": kept["why"], "read": kept["read"], "age": kept["age"],
            "events": evs[-n:]}


def api(live: Live, path: str, q: dict):
    """An answer; a graph's with its correspondence (``correspond.py``): which model parts each
    shape is, and which shapes stand for each part, so one selection is lit in every view."""
    got = _answer(live, path, q)
    if path.strip("/") == "graph" and isinstance(got, dict):
        from ..correspond import table
        shown = got.pop("_model", None) or live.get().model       # a proposal drawn: its model's parts
        got["corr"] = table(got, shown)
        if q.get("have"):                             # a page polling: only the values, when it holds this structure
            from .graph_poll import answer
            return answer(got, q["have"][0])
    return got


def _answer_with(live: Live, path: str, q: dict, model):
    """The answer drawn from another model (a proposal's), as if it were the project's."""
    import copy
    q2 = {k: v for k, v in q.items() if k not in ("proposal", "have")}
    p = copy.copy(live.get())                       # the project as it is, its model the proposal's: never shared
    p.model = model
    return _answer(live, path, q2, p)


def _answer(live: Live, path: str, q: dict, project=None):
    if path.strip("/") == "projects":             # the last list the lister made: no model, snapshot or lock here
        got = _LISTED
        return dict(got, age=None if got["at"] is None else max(0.0, time.time() - got["at"]))
    p = project or live.get()
    m = p.model
    one = lambda k: (q.get(k) or [None])[0]       # noqa: E731
    # a change waiting, drawn as it would leave the model (not written); the process map is the record's, the same
    if path.strip("/") == "graph" and one("proposal") and one("view") not in ("process", "wiring"):
        from .numbers_api import proposed_graph
        return proposed_graph(live, p, q, one("proposal"), lambda m2: _answer_with(live, path, q, m2))
    parts = path.strip("/").split("/")
    head, name = parts[0], unquote(parts[1]) if len(parts) > 1 else None
    if head == "items-query":                     # near, path, about (SPEC §5a, Graph queries), as the record is now
        from ..spec import itemgraph as ig
        asked = [k for k in ("near", "path", "about") if one(k) is not None]
        if one("at") or len(asked) != 1:
            raise BadSet("items-query: one of near=ID, path=A&to=B or about=ID, as the record is now (never at=)")
        ev, s = p.events, getattr(m, "spec", None)
        try:
            return ig.near(ev, s, one("near"), one("depth")) if asked == ["near"] else \
                ig.path(ev, s, one("path"), one("to")) if asked == ["path"] else ig.about(ev, s, one("about"))
        except ig.Unknown:
            return None
        except ig.Bad as e:
            raise BadSet(str(e)) from e
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
        edited = _edited(live, p, running)
        spec = getattr(m, "spec", None)              # the diagram's caption: what the model is for, its loops
        said = {"purpose": spec.purpose, "top": len(spec.subsystems(None)),
                "controlled": sorted(g for g in spec.goals if spec.loop(g).controllers)} if spec else {}
        return {"name": m.name, **said, "running": running, "live": snap["live"], "first": p.events.first_time(),
                "attention": ([{"level": "bad", "what": "the model", "says": edited["banner"]}] if edited else [])
                + st.attention(snap, running and snap["live"], m), "loops": snap["loops"], "goals_off": st.goals_off(snap),
                **({"edited": edited} if edited else {}),
                "counts": {"loops": len(m.controllers), "stocks": len(m.stocks), "flows": len(m.flows),
                           "agents": len(m.agents), "events": p.events.count(), "measurements": p.measurements.count()},
                "systems": m.system_names(), "check": [{"level": lv, "message": msg} for lv, msg in mdl.check(m)],
                "at": snap["at"], "window": snap["window"], "recorded": snap.get("recorded"),   # the window's span on record
                "rate_units": rates.overrides(getattr(m, "spec", None)),
                "changes": [{"time": e["time"], **{k: e["data"][k] for k in ("added", "removed", "changed")}}
                            for e in history.changes(p, snap["at"] - snap["window"])][-5:]}
    if head == "coherence":                          # the three views held against each other (the Check page)
        from .numbers_api import coherence
        return coherence(live, p, snap, _window(q) if one("since") else None)
    if head == "exercised":                          # the parts the record has not exercised: findings, for the Check page
        from .numbers_api import exercised
        return exercised(live, p, snap)
    if head == "guide":                              # the Guide's frames: tiny models, the same for every project
        from ..guide import frames
        return frames()
    if head == "export":                             # the model behind the picture, as Markdown (export_api.py)
        from ..blockdiagram import _Diagram, identified, spec_of
        from .export_api import export, file_name
        view = one("view")
        if view not in ("dynamics", "blocks") or (one("format") or "md") not in ("md", "json"):
            raise BadSet("export: view=dynamics or view=blocks, and format=md (or json)")
        g = _answer(live, "graph", {**{k: v for k, v in q.items() if k != "have"}, "view": [view]}, p)
        flat = _Diagram(spec_of(m), {**snap, "laws": _laws(p, getattr(m, "spec", None)) or {}}) \
            if view == "blocks" and spec_of(m) is not None else None
        if flat is not None:
            flat.build()
            identified(flat)
        return {"file": file_name(m.name, view, one("system"), snap["at"]),
                "markdown": export(m, view, one("system"), snap, g, flat)}
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
            laws = _laws(p, getattr(m, "spec", None))   # external blocks' identified laws, once fitted (SPEC §12d)
            return {**diagram(m, {**snap, "laws": laws or {}}, want, system), "attention": att}
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
            reads = None
            if getattr(m.spec, "remotes", None):     # when what remotes' boxes show last read (SPEC §4c)
                from ..remote.measures import read_times
                reads = read_times(p, m.spec, snap["at"])
            if sd:
                return {**finish(fold(dynamics(g, m), m, want, system, reads)), "attention": att}
            return {**fold(g, m, want, system, reads), "attention": att}
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
            from ..daemons.supervise import of_daemon
            b = m.spec.blocks.get(name) if getattr(m, "spec", None) else None
            dn = b.params.get("daemon") if b is not None else None
            from ..actions import record as acts
            began = {e.get("causedby") for e in runs[-80:]}   # the gated actions each run asked for, by its start's id
            asked: dict[str, list] = {}
            for x in acts.stored(p, until=snap["at"]).values():
                if x.get("run") in began:
                    asked.setdefault(x["run"], []).append({k: x.get(k) for k in ("id", "action", "state")})
            from ..leases import ENDED  # how each run's lease ended (a nack: it gave its item back), from its start on
            since = min((e["time"] - (e["data"].get("seconds") or 0) for e in runs[-80:]), default=snap["at"]) - 60
            ended = {e["causedby"]: {k: e["data"].get(k) for k in ("how", "why")} for e in p.events.query(
                n=None, type=ENDED, since=since, until=snap["at"]) if e.get("causedby") in began}
            return {"agent": {**a.__dict__, "rung": a.rung}, **snap["agents"][name], "recent": runs[-80:], "asked": asked,
                    "ended": ended,
                    **({"daemon": {"name": dn, **of_daemon(snap.get("daemons", {}), dn)}} if dn else {}),
                    "log": _tail(log, 40), "log_path": str(log),
                    "loads": [f.name for f in m.flows.values() if f.disturbance and f.agent == name],
                    "use": costs.of_block(p, name, snap["at"] - snap["window"], snap["at"])}   # what its runs cost (§9.1)
        from ..costs import record as costs
        use = costs.per_block(p, snap["at"] - snap["window"], snap["at"])
        return {n: {**a, "hints": [h for h in snap["hints"] if h["agent"] == n], **({"use": use[n]} if n in use else {})}
                for n, a in snap["agents"].items()}
    if head == "daemons":                         # the long-lived runners (SPEC §9.7), as the engine last saw them
        return snap.get("daemons", {})
    if head == "events" and "remote" in q:        # a remote's, from its cache (remote/events.py): never the local record
        if name is not None:
            from ..remote.items import RemoteRefused
            raise RemoteRefused(400, "a remote's events are listed, never opened one by one here")
        return _remote_events(getattr(m, "spec", None), one("remote"), one("n"), one("type"))
    if head == "items" and "remote" in q:         # a remote's, asked there within its budget (remote/items.py)
        from ..remote import items as remote_items
        spec = getattr(m, "spec", None)
        remote_items.remote(spec, one("remote"))
        if len(parts) > 2:
            raise remote_items.RemoteRefused(400, "a remote item's id is one path segment")
        if name is not None:
            return remote_items.detail(spec, one("remote"), name)
        return remote_items.listing(spec, one("remote"), one("kind"), one("state"), one("n") or 100, one("offset") or 0)
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
            d = its.detail(p.events, spec, name, until=snap["at"], history=None if one("history") == "all" else its.HISTORY_SHOWN)
            est = _estimates(p, m, snap, one("whatif"))
            if d and est and name in est.get("items", {}):
                d["eta"] = {**est["items"][name], "at": est["at"], "runs": est["runs"]}
            if d and d.get("kind_of") and spec and d["kind_of"]["name"] in spec.items:   # its endings, as the process map counts them
                from ..process import _done
                ends = _done(spec, p.events, spec.items[d["kind_of"]["name"]])
                d["kind_of"]["final"] = [s for s in d["kind_of"]["states"] if s in ends]
            return d
        from ..spec import item_sets
        n, offset = max(1, min(int(one("n") or its.LISTED), its.LISTED)), int(one("offset") or 0)
        if "search" in q:                         # the items whose fields hold every word, as now (SPEC §5a, Search)
            if one("at"):
                raise BadSet("search: answers as of now; leave out at")
            if item_sets.asked(q) or one("alone"):           # never a filter silently dropped
                raise BadSet("search: narrows by kind and one state only; leave out where, moved, through, followed, "
                             "caused, alone and a list of states")
            got = its.listing(p.events, spec, kind=one("kind"), state=one("state"), n=n, offset=offset,
                              search=one("search"))
            return _as_listed(got, None, 0, bool(one("shown")))
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
        pk = int(one("per_kind") or 0)
        if pk and not one("kind") and not one("state") and spec is not None:   # each kind's newest, however busy the rest
            have = {}
            for i in got["items"]:
                have[i.get("kind")] = have.get(i.get("kind"), 0) + 1
            for k in got["kinds"]:
                if have.get(k["name"], 0) < min(pk, sum(k["counts"].values())):
                    more = its.listing(p.events, spec, kind=k["name"], until=snap["at"], n=pk)["items"]
                    got["items"] = [i for i in got["items"] if i.get("kind") != k["name"]] + more
        if want is not None:
            got["set"] = {"says": want.says(), "params": want.params()}
        out = _as_listed(got, one("q"), int(one("per_kind") or 0), bool(one("shown")), one("hide"))
        if getattr(spec, "remotes", None):            # each remote's own section, asked by the page on its own
            out["remotes"] = [{"name": k, "url": r["url"]} for k, r in spec.remotes.items()]
        est = _estimates(p, m, snap, one("whatif"))
        if est and est.get("items"):                  # each open item's estimate (SPEC §5a, Completion estimates)
            out["items"] = [{**i, "eta": {k: est["items"][i["id"]].get(k) for k in ("p50", "p90", "why", "runs")}}
                            if i["id"] in est["items"] else i for i in out["items"]]
        return out
    if head == "series":                          # behaviour over time: each part's values, bucketed over the window
        refs = [r for r in (one("refs") or "").split(",") if r]
        out = series.series(p, snap, refs, int(one("points") or series.POINTS), bool(one("strip")))
        if one("replay"):                         # and what the model says: its replay, and its projection past now
            from .numbers_api import add_to_series
            add_to_series(live, p, snap, out, one("inputs") or "hold", one("whatif"),
                          "replay" if one("fan") == "replay" else bool(one("fan")), one("loops"))
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
    if head == "impact":                          # a fix's or a change's impact report (SPEC §12n), on its item's page
        from .numbers_api import impact
        return impact(live, p, snap, one)
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
    if head == "report" and name:                 # a report upstream: its text, its link, its scrub log (SPEC §12m)
        from .reports_api import get as report
        return report(p, "/".join(unquote(x) for x in parts[1:]))
    if head == "actions":                         # gated actions sessions asked for, about one item or all (SPEC §12k)
        from .actions_api import listing as actions
        return actions(p, one("item") or None)
    if head == "inbox":                           # everything waiting on a person (SPEC §12o)
        from .actions_api import inbox
        return inbox(p)
    if head == "trust":                           # how far blocks' claims hold, by block, rung and model (SPEC §12g)
        from ..claims import trust
        return trust.table(p, snap["at"] - max(snap["window"], trust.WEEK), snap["at"])
    if head == "verdicts":                        # finished work held to what the owner meant (SPEC §12i)
        from .verdicts_api import table as verdicts
        return verdicts(p, snap)
    if head == "items-graph":                     # the Items page's Graph and Timeline: relations (SPEC §5a)
        from .eta_api import merge
        from .relations_api import graph as items_graph
        est = _estimates(p, m, snap, one("whatif"))   # None while the first is worked out: the legend says so
        return {**merge(items_graph(p, m, snap, q), est), "eta_pending": est is None and abs(time.time() - snap["at"]) < 5}
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
        spec = getattr(m, "spec", None)
        if kind in ("stock", "flow", "disturbance", "sensor") and spec is not None:   # what it counts, first in its panel
            from ..spec import item_sets
            out["counts"] = item_sets.counted_by(spec, "flow" if kind == "disturbance" else kind, pname)
        if kind in ("flow", "valve") and spec is not None:                   # the items leased to the blocks moving it
            from ..spec import item_sets
            out["leases"] = item_sets.leased_by(p.events, spec, x.flow if kind == "valve" else pname, snap["at"])
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


PUSH_LIMIT = 4 * 1024 * 1024        # the largest push read (bytes)


def handler(project):
    live = Live(project)
    token = secrets.token_urlsafe(24)                    # this run's: written into the page, asked of every write

    class Handler(BaseHTTPRequestHandler):
        timeout = 10                                   # an idle browser connection gives its thread back
        public, origins = True, frozenset()            # until _gate says who asks
        READER = "anyone (public, read only)"          # who asks under a name declared open: read (SPEC §4d)
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
            state = Path(p.dir).resolve()
            for root in roots:
                f = (root / rel).resolve()
                if self.public and (f == state or state in f.parents):   # under a public name: never the state's (its tokens)
                    continue
                if (root == f or root in f.parents) and f.is_file():
                    if f.stat().st_size > FILE_LIMIT:
                        return self._send(413, b"too big to show", "text/plain")
                    if page and f.suffix.lower() == ".md":     # opened in the browser: shown rendered, its relative links kept
                        return self._send(200, md_page(f.name, f.read_text(errors="replace")), "text/html; charset=utf-8")
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream", True)
            return self._send(404, b"not found", "text/plain")

        def _gate(self) -> str | None:
            """Who asks, or None with the refusal sent. ``owner``: a request addressed to this server by its own name
            (a page on another site whose name was pointed at 127.0.0.1, DNS rebinding, sends its own name as the
            Host, and is refused). Under a public name the model declares, or through Cloudflare whatever the Host
            (a tunnel that rewrites it), only the email a valid Cloudflare Access login names (SPEC §4d)."""
            from .. import webaccess as wa
            port = self.server.server_address[1]
            host = (self.headers.get("Host") or "").lower()
            local = host in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
            web = wa.of(getattr(live.get().model, "spec", None))
            public = web is not None and host in web.names
            self.origins, self.public = {f"http://{host}"}, True
            if not (public or local):
                return self._send(403, b"not this server's name", "text/plain")
            if not public and not any(self.headers.get(h) for h in wa.HEADERS):
                self.public = False
                return "owner"
            if public and web.open:                       # declared public and read only: no login, and no writes
                return self.READER
            try:
                who = wa.verify(web, self.headers.get("Cf-Access-Jwt-Assertion"))
            except wa.Refused as e:
                return self._send(e.code, json.dumps({"error": str(e)}).encode(), "application/json")
            self.origins = {f"https://{n}" for n in web.names}
            return who

        def _local(self) -> bool:
            from ..intake.token import allowed
            return allowed(self.client_address[0], [])

        def do_POST(self):
            """The page's one kind of write: the owner accepting or dismissing a proposal, asking for
            estimates, or sending the work a message. Only from the page itself: addressed to this server by its own name (the Host
            header), from its own origin (Origin, Sec-Fetch-Site), and carrying the token this run of the
            server wrote into the page it served, which no other page can read. Events pushed (``/api/events``,
            ``/api/hooks/NAME``) carry the state directory's token instead (``intake/``)."""
            u = urlsplit(self.path)
            if u.path == "/api/events" or u.path.startswith("/api/hooks/"):
                from .push_api import post as push
                n = int(self.headers.get("Content-Length") or 0)
                code, data = push(live, u.path, parse_qs(u.query), self.headers, self.client_address[0],
                                  self.rfile.read(n) if 0 < n <= PUSH_LIMIT else None, n)
                return self._send(code, json.dumps(data, default=str).encode(), "application/json")
            if u.path.startswith("/remote/"):                # read only, whoever asks (its token admits)
                return self._remote(u)
            if not self._local():                         # another machine may only push, or read /remote/
                return self._send(403, b'{"error": "only events may be pushed from another machine"}', "application/json")
            who = self._gate()
            if who is None:
                return None
            if who == self.READER:
                return self._send(403, b'{"error": "this name is public and read only (web: open: read)"}', "application/json")
            origin = self.headers.get("Origin")
            fetch_site = self.headers.get("Sec-Fetch-Site")
            if (not u.path.startswith("/api/") or (origin is not None and origin.lower() not in self.origins)
                    or (fetch_site is not None and fetch_site not in ("same-origin", "none"))
                    or not secrets.compare_digest(self.headers.get("X-Ergostat-Token") or "", token)):
                return self._send(403, b'{"error": "only the page may ask"}', "application/json")
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(min(n, 65536)) if n else b""
            from ..webaccess import acting, done
            from .numbers_api import post
            as_who = acting(who)                           # what this write records says who made it (SPEC §4d)
            try:
                q = parse_qs(u.query)
                if u.path == "/api/message":                # the owner's words to the work in flight (SPEC §12h)
                    from .messages_api import post as message
                    code, data = message(live, q, body)
                elif u.path.startswith("/api/control/"):   # a loop's process, tuning or step test: the owner's answer
                    from .control_api import post as control
                    code, data = control(live, u.path.removeprefix("/api/"))
                elif u.path.startswith("/api/report/"):    # the owner marking a report upstream (SPEC §12m)
                    from .reports_api import post as report
                    code, data = report(live, u.path.removeprefix("/api/"), q)
                elif u.path.startswith("/api/action/"):    # the owner's answer to a gated action held (SPEC §12k)
                    from .actions_api import post as action
                    code, data = action(live, u.path.removeprefix("/api/"), q)
                elif u.path.startswith("/api/inbox/"):     # the owner's answer to anything waiting on them (SPEC §12o)
                    from .actions_api import answer
                    code, data = answer(live, u.path.removeprefix("/api/"), q)
                elif u.path.startswith("/api/verdict/"):   # the owner on the intent judge: overrule, reopen (SPEC §12i)
                    from .verdicts_api import post as verdict
                    code, data = verdict(live, u.path.removeprefix("/api/"), q)
                elif u.path.startswith("/api/intent/"):    # a proposed decision or correction: the owner's answer
                    from .intent_api import post as intent
                    code, data = intent(live, u.path.removeprefix("/api/"), q)
                else:
                    code, data = post(live, u.path.removeprefix("/api/"), _window(q), q)
            except Exception as e:                      # a broken request never takes the page down
                crash_noted(live, e, "web")                # a report for the owner (SPEC §12m)
                code, data = 500, {"error": f"{type(e).__name__}: {e}"}
            finally:
                done(as_who)
            return self._send(code, json.dumps(data, default=str).encode(), "application/json")

        def _remote(self, u):
            """The remote API (SPEC §4c, ``remote_api.py``): read only, behind a consumer's bearer token; off (404)
            until a token is made. No Host check: a tunnel or a proxy sends its own name, and the token admits."""
            from ..remote import tokens
            from . import remote_api
            p = live.get()
            if not tokens.load(p.dir):
                return self._send(404, b'{"error": "the remote API is off (ergostat remote token NAME turns it on)"}',
                                  "application/json")
            if self.command != "GET":
                return self._send(405, b'{"error": "the remote API is read only"}', "application/json")
            auth = self.headers.get("Authorization") or ""
            who = tokens.who(p.dir, auth[7:].strip() if auth.lower().startswith("bearer ") else None)
            if who is None:
                return self._send(401, b'{"error": "a token is needed: Authorization: Bearer TOKEN"}', "application/json")
            wait = remote_api.allowed(who)
            if wait is not None:
                try:
                    self.send_response(429)
                    self.send_header("Retry-After", str(max(1, round(wait))))
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except GONE:
                    pass
                return None
            try:
                code, data = remote_api.answer(live, u.path.removeprefix("/remote/"), parse_qs(u.query))
            except BadSet as e:
                code, data = 400, {"error": str(e)}
            except Exception as e:                      # a broken request never takes the page down
                code, data = 500, {"error": f"{type(e).__name__}: {e}"}
            version = data.get("version") if isinstance(data, dict) and u.path.rstrip("/").endswith("/model") else None
            if version and code == 200 and f'"{version}"' in (self.headers.get("If-None-Match") or ""):
                try:
                    self.send_response(304)
                    self.send_header("ETag", f'"{version}"')
                    self.end_headers()
                except GONE:
                    pass
                return None
            body = json.dumps(data, default=str).encode()
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                if version:
                    self.send_header("ETag", f'"{version}"')
                self.end_headers()
                self.wfile.write(body)
            except GONE as e:
                went_away(self.path, len(body), e)
            return None

        def do_GET(self):
            u = urlsplit(self.path)
            if u.path.startswith("/remote/"):                # read only, behind its token: from any machine (SPEC §4c)
                return self._remote(u)
            if not self._local():                         # another machine may only push (intake: bind:) or read /remote/
                return self._send(403, b"only events may be pushed from another machine", "text/plain")
            who = self._gate()
            if who is None:                                # another site's name, or no login under a public one
                return None
            if u.path.startswith("/api/"):
                try:
                    q = parse_qs(u.query)                   # (a blank search kept, to be refused: never "list all")
                    q.update({"search": [""]} if "search" not in q and "search" in parse_qs(u.query, True) else {})
                    data = api(live, u.path.removeprefix("/api/"), q)
                except BadSet as e:                     # an Items filter that is not one: said, as the asker's
                    return self._send(400, json.dumps({"error": str(e)}).encode(), "application/json")
                except RemoteRefused as e:              # a remote not named, not answering, or asked enough (SPEC §4c)
                    return self._send(e.code, json.dumps({"error": e.why, "ok": False}).encode(), "application/json")
                except Exception as e:                  # a broken request never takes the page down
                    crash_noted(live, e, "web")                # a report for the owner (SPEC §12m)
                    return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode(), "application/json")
                if data is None:
                    return self._send(404, b'{"error": "not found"}', "application/json")
                if u.path == "/api/export" and (q.get("format") or ["md"])[0] == "md":    # the document itself, for curl
                    return self._send(200, data["markdown"].encode(), "text/markdown; charset=utf-8")
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
                if who == self.READER:                     # said on the page: no token, and why its buttons do nothing
                    body = body.replace(f'content="{token}">', 'content="">\n<meta name="ergostat-public" content="read only">', 1)
                return self._send(200, body.encode(), "text/html; charset=utf-8", True)   # never kept stale: no-cache, ETag
            asked = (parse_qs(u.query).get("v") or [""])[0]
            cache = FOREVER if asked and asked == asset_version(name) else "no-cache"
            self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream", True, cache)

    Handler.live = live
    return Handler
