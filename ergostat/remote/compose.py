"""``remotes:`` (SPEC §4c): each remote's served model put into this one as an external subsystem.

Every part it serves becomes ``REMOTE-PART`` (as a template's instance names its parts, and with the same renaming:
``library/expand.rename``), in the system ``REMOTE`` (its own systems inside it), pointing at the ``remotes:`` line
(``RemoteVia``). Its blocks become ``type: external`` (never run here), its sensors queries of the remote's same
series (``readings.py``), its agents ``external: true`` (each keeps its rung); its item kinds stay there (the
local fold never folds remote items). A local reference to a remote part that the remote no longer serves gets a
stand-in and a ``remote-reference-unresolved`` finding, so the model still loads; a local block that outputs to a
remote part is an error (``remote-output``)."""

from __future__ import annotations

import contextlib
import contextvars
import re
import time

from ..durations import DurationError, parse_duration
from ..library.expand import BARE, REF, SECTION_OF, rename
from ..spec import files
from ..spec.ir import NAME
from ..spec.load import Map, Problem, Where

KEYS = {"url", "token-file", "systems", "within", "every", "description"}
EVERY, EVERY_LEAST = 60.0, 10.0
IMPORTED = ("systems", "parameters", "auxiliaries", "stocks", "flows", "goals", "blocks", "agents")
BLOCK_KEEP = {"in", "out", "agent", "role", "description", "system"}
KINDS = {"stock": "stocks", "flow": "flows", "auxiliary": "auxiliaries", "variable": "auxiliaries", "goal": "goals",
         "block": "blocks", "parameter": "parameters", "system": "systems"}
STALE_RUNS = 3

_OFFLINE: contextvars.ContextVar[bool] = contextvars.ContextVar("ergostat_remote_offline", default=False)


_FRESH: contextvars.ContextVar[bool] = contextvars.ContextVar("ergostat_remote_fresh", default=False)


@contextlib.contextmanager
def fresh():
    """Ask every remote for its current model whatever the cache's age (``ergostat check``: references are checked
    against what the remote serves now)."""
    tok = _FRESH.set(True)
    try:
        yield
    finally:
        _FRESH.reset(tok)


@contextlib.contextmanager
def offline():
    """Load from the cache only, never asking a remote (the remote API serving its own model)."""
    tok = _OFFLINE.set(True)
    try:
        yield
    finally:
        _OFFLINE.reset(tok)


class RemoteVia(Where):
    """Where a remote's part was brought in: its ``remotes:`` entry, and which remote it is."""

    def __init__(self, file, line: int, remote: str, url: str = ""):
        super().__init__(file, line)
        self.remote, self.url = remote, url

    def __str__(self) -> str:
        return f"{self.file.name}:{self.line} (remote {self.remote})"


def as_map(x, where: Where):
    if isinstance(x, dict):
        m = Map({k: as_map(v, where) for k, v in x.items()})
        m.where, m.lines = where, {k: where for k in x}
        return m
    if isinstance(x, list):
        return [as_map(v, where) for v in x]
    return x


def take(doc, data: Map, defaults: dict, put) -> None:
    """A file's ``remotes:``: each entry checked, its model read from the cache (asked of the remote when the cache is
    older than its ``every``), and its parts put in."""
    body = data["remotes"]
    if not isinstance(body, dict):
        doc.problems.append(Problem("error", "remotes: a map, each entry a remote's name: its url: and token-file:",
                                    data.at("remotes"), "not-a-map"))
        return
    for name, entry in body.items():
        w = body.at(name) if hasattr(body, "at") else data.at("remotes")
        one(doc, str(name), entry, w, defaults, put)


def one(doc, name: str, entry, w: Where | None, defaults: dict, put) -> None:
    def err(msg, where=None, code="bad-remote"):
        doc.problems.append(Problem("error", f"remote {name}: {msg}", where or w, code, f"system.{name}"))

    if not NAME.match(name):
        return err("a remote's name is lowercase letters, digits and -, starting with a letter", code="bad-name")
    if name in doc.remotes:
        return err(f"defined twice: here and at {doc.remotes[name]['where']}", code="defined-twice")
    if not isinstance(entry, dict) or not entry.get("url"):
        return err("give it url: (the remote ergostat's page, https or a tunnel's loopback port) and token-file:",
                   code="missing-key")
    for k in entry:
        if k not in KEYS:
            err(f"unknown key {k!r} (known: {', '.join(sorted(KEYS))})", entry.at(k), "unknown-key")
    url = str(entry["url"]).rstrip("/")
    if not re.match(r"^https?://", url):
        return err(f"url: {url!r} is not an http(s) address", entry.at("url"))
    host = re.sub(r"^https?://", "", url).split("/")[0].rsplit(":", 1)[0].strip("[]")
    if url.startswith("http://") and host not in ("127.0.0.1", "localhost", "::1"):
        err(f"url: {url} is plain http to another machine: use https, or an SSH tunnel to a loopback port "
            f"(ssh -N -L 8795:127.0.0.1:8781 HOST, then url: http://127.0.0.1:8795)", entry.at("url"), "remote-insecure")
    every = EVERY
    if entry.get("every") is not None:
        try:
            every = max(EVERY_LEAST, parse_duration(entry["every"], "every"))
        except DurationError as e:
            err(str(e), entry.at("every"))
    only = entry.get("systems")
    if only is not None and (not isinstance(only, list) or not all(isinstance(x, str) for x in only)):
        err("systems: a list of the remote's systems to bring in", entry.at("systems"))
        only = None
    token_file = entry.get("token-file")
    via = RemoteVia(w.file if w else doc.root, w.line if w else 1, name, url)
    from . import cache
    d = cache.folder(doc.name, doc.root, name)
    if not _OFFLINE.get() and not files.replaying():     # (the last good model: its kept cache only)
        st = cache.status(d)
        if _FRESH.get() or not cache.model(d) or time.time() >= float(st.get("next") or 0):
            cache.refresh(d, url, str(token_file) if token_file else None, doc.root, every,
                          force=_FRESH.get() or not cache.model(d))
    served = cache.model(d)
    st = cache.status(d)
    parent = entry.get("within") or defaults.get("system")
    put("sources", name, as_map({"type": "ergostat", "url": url, **({"token-file": str(token_file)} if token_file else {})},
                                via), via, {})
    where_text = f"remote: run by the ergostat at {url}"
    put("systems", name, as_map({"description": str(entry.get("description") or where_text),
                                 **({"within": str(parent)} if parent else {})}, via), via, {})
    info = {"url": url, "token_file": str(token_file) if token_file else None, "every": every, "dir": str(d),
            "where": via, "within": parent, "systems": list(only) if only else None, "version": None, "fetched": None,
            "name": None, "parts": {}, "names": {}, "kinds": {}, "missing": [], "status": st}
    doc.remotes[name] = info
    if not st.get("ok", True) or st.get("ok") is None and served is None:
        why = st.get("why") or "not asked yet"
        since = st.get("failing_since")
        last = st.get("answered") or (served or {}).get("fetched")
        age = (f"; drawn from its model as last read, {_ago(last)} ago" if served else
               "; never read, so nothing of it is drawn")
        doc.problems.append(Problem("finding", f"remote {name}: {url} did not answer ({why})"
                                    + (f" since {_ago(since)} ago" if since else "") + age, via, "remote-unreachable",
                                    f"system.{name}"))
    if served is None:
        return
    info.update(version=served.get("version"), fetched=served.get("fetched"), name=served.get("name"))
    secs = served.get("sections") or {}
    info["kinds"] = {k: v for k, v in (secs.get("items") or {}).items() if isinstance(v, dict)}
    made = parts(name, secs, only, every)
    for section, entries in made.items():
        for pname, got in entries.items():
            put(section, pname, as_map(got, via), via, {})
            info["parts"][f"{SINGULAR[section]}.{pname}"] = True
            info["names"][f"{SINGULAR[section]}.{pname}"] = f"{SINGULAR[section]}.{pname[len(name) + 1:]}"   # served only


SINGULAR = {"systems": "system", "parameters": "parameter", "auxiliaries": "auxiliary", "stocks": "stock",
            "flows": "flow", "goals": "goal", "blocks": "block", "agents": "agent", "sources": "source"}


def _ago(t) -> str:
    from ..durations import human
    try:
        return human(max(0.0, time.time() - float(t)))
    except (TypeError, ValueError):
        return "?"


def kept_systems(secs: dict, only: list[str] | None) -> set[str] | None:
    """The remote's systems brought in: those named and every system within them (None: all)."""
    if not only:
        return None
    within = {n: (v or {}).get("within") for n, v in (secs.get("systems") or {}).items()}
    out = set()
    for s in within:
        x, seen = s, set()
        while x and x not in seen:
            if x in only:
                out.add(s)
                break
            seen.add(x)
            x = within.get(x)
    return out


def parts(remote: str, secs: dict, only: list[str] | None, every: float) -> dict[str, dict]:
    """The served sections as this model's: renamed, narrowed to ``only``, blocks external, sensors queries."""
    keep_sys = kept_systems(secs, only)

    def kept(section: str, v) -> bool:
        if keep_sys is None or section == "agents":
            return True
        if section == "systems":
            return True if v is None else False
        return isinstance(v, dict) and v.get("system") in keep_sys

    chosen: dict[str, dict] = {}
    for section in IMPORTED:
        for n, v in (secs.get(section) or {}).items():
            if section == "systems" and keep_sys is not None:
                if n in keep_sys:
                    chosen.setdefault(section, {})[n] = v or {}
                continue
            if kept(section, v):
                chosen.setdefault(section, {})[n] = v or {}
    renames = {section: {n: f"{remote}-{n}" for n in (secs.get(section) or {})} for section in IMPORTED}
    renames["items"] = {}
    gone = {f"{remote}-{n}" for section in IMPORTED for n in (secs.get(section) or {})
            if n not in chosen.get(section, {})}
    moved = {m.group(2) for b in (secs.get("blocks") or {}).values() if isinstance(b, dict)
             for m in REF.finditer(str(b.get("out"))) if m.group(1) == "flow"}     # flows a block moves there
    out: dict[str, dict] = {}
    for section, entries in chosen.items():
        for n, v in entries.items():
            got = rename(dict(v), section, None, renames)
            got = _cut(got, section, gone)
            if got is None:
                continue
            got = _local(remote, section, got, every, n, n in moved)
            if section == "systems":
                if not got.get("within") or got.get("within") in gone:
                    got["within"] = remote
            elif section != "agents" and (not got.get("system") or got.get("system") in gone):
                got["system"] = remote
            out.setdefault(section, {})[f"{remote}-{n}"] = got
    return out


def _names_in(text: str) -> set[str]:
    return {m.group(2) for m in REF.finditer(text)}


def _mentions(x, gone: set[str]) -> bool:
    if isinstance(x, str):
        return bool(_names_in(x) & gone) or x.lstrip("+-") in gone
    if isinstance(x, dict):
        return any(_mentions(v, gone) for v in x.values())
    if isinstance(x, list):
        return any(_mentions(v, gone) for v in x)
    return False


def _cut(got: dict, section: str, gone: set[str]) -> dict | None:
    """A part narrowed: what it names among the parts left out is cut (a flow's end becomes a cloud, a cause or an
    input is dropped, an equation that names one is dropped); a goal on a part left out goes with it."""
    if not gone:
        return got
    if section == "flows":
        for end in ("from", "to"):
            if got.get(end) in gone:
                got.pop(end)
        if not got.get("from") and not got.get("to"):
            return None
    if section == "goals" and any(got.get(k) in gone for k in ("stock", "flow", "auxiliary", "variable")):
        return None
    for k in ("driven-by", "in", "out", "show"):
        v = got.get(k)
        if isinstance(v, list):
            got[k] = [x for x in v if not _mentions(x, gone)]
        elif isinstance(v, dict):
            got[k] = {p: x for p, x in v.items() if not _mentions(x, gone)}
        elif v is not None and _mentions(v, gone):
            got.pop(k)
    if isinstance(got.get("equation"), str) and _mentions(got["equation"], gone):
        got.pop("equation")
    if section == "blocks" and got.get("goal") in gone:
        got.pop("goal")
    return got


def _local(remote: str, section: str, got: dict, every: float, there: str, moved: bool = False) -> dict:
    """A served part as it is drawn and read here."""
    if section == "agents":
        return {"kind": got.get("kind") or "program", "external": True,
                "description": got.get("description") or f"runs on {remote}"}
    if section == "blocks":
        b = {k: v for k, v in got.items() if k in BLOCK_KEEP}
        if got.get("goal"):                          # it served a goal there: it reads that goal's error here
            ref = f"goal.{got['goal']}.error"
            ins = b.get("in")
            if ins is None:
                b["in"] = ref
            elif isinstance(ins, list):
                b["in"] = [*ins, ref] if ref not in ins else ins
            elif isinstance(ins, dict):
                b["in"] = {**ins, "goal": ref}
            elif ins != ref:
                b["in"] = [ins, ref]
        b["type"] = "external"
        kind = got.get("type") or "?"
        b["description"] = (got.get("description") or "").strip() or f"a {kind} block, run on {remote}"
        return b
    if section in ("stocks", "flows", "auxiliaries"):
        sensors = got.pop("sensors", None) or {}
        got.pop("sensor", None)
        mine = {}
        for sname, s in sensors.items():
            s = s if isinstance(s, dict) else {}
            mine[sname] = {"query": {"source": remote, "series": f"sensor/{there}.{sname}"},
                           "every": _every(s, every),
                           "description": f"read from {remote} ({s.get('kind') or 'a'} sensor there)",
                           **({"averages": s["averages"]} if s.get("averages") is not None else {})}
        if section == "flows" and not mine and got.get("rate") is None and moved:   # its rate there is what its valve moved
            mine["remote"] = {"query": {"source": remote, "ref": f"flow.{there}"},
                              "every": f"{int(every)}s", "description": f"its rate, as {remote} reckons it"}
        if mine:
            got["sensors"] = mine
    return got


def _every(s: dict, every: float) -> str:
    try:
        own = parse_duration(s.get("every") or every, "every")
    except DurationError:
        own = every
    return f"{int(max(own, every))}s"


def _walk(x, section: str, key: str | None, at, found: list) -> None:
    """Every reference in a local entry: (kind's section, name, where, key it is under)."""
    if isinstance(x, dict):
        for k, v in x.items():
            _walk(v, section, k, x.at(k) if hasattr(x, "at") else at, found)
    elif isinstance(x, list):
        for v in x:
            _walk(v, section, key, at, found)
    elif isinstance(x, str):
        bare = BARE.get((section, key))
        if bare:
            found.append((bare, x.lstrip("+-"), at, key))
        for m in REF.finditer(x):
            found.append((SECTION_OF[m.group(1)], m.group(2), at, key))


def finish(doc, put) -> None:
    """Once every file is read: the local references into each remote checked against what it serves now. One that
    does not resolve gets a stand-in and a finding (the model still loads); a local block that outputs to a remote
    part is an error, since what runs there is changed only there."""
    if not doc.remotes:
        return
    for section, entries in doc.sections.items():
        for ename, entry in list(entries.items()):
            if isinstance(getattr(entry, "where", None), RemoteVia):
                continue
            found: list = []
            _walk(entry, section, None, getattr(entry, "where", None), found)
            for kind, ref_name, at, key in found:
                remote = next((r for r in doc.remotes if ref_name.startswith(r + "-")), None)
                if remote is None:
                    continue
                info = doc.remotes[remote]
                plural = kind
                single = SINGULAR.get(plural, plural)
                there = ref_name[len(remote) + 1:]
                if section == "blocks" and key == "out" and plural != "agents":
                    doc.problems.append(Problem(
                        "error", f"block {ename}.out: {single}.{ref_name} belongs to remote {remote}, which runs it; a "
                        f"block here may read it, never act on it (propose the change to {remote}'s owner)", at,
                        "remote-output", f"block.{ename}"))
                    continue
                if ref_name in doc.sections.get(plural, {}):
                    continue
                if plural not in ("stocks", "flows", "auxiliaries", "goals", "blocks"):
                    continue
                stub = _stand_in(doc, put, remote, plural, ref_name, info)
                if stub and (single, ref_name) not in {(m["kind"], m["name"]) for m in info["missing"]}:
                    info["missing"].append({"kind": single, "name": ref_name, "there": there, "where": str(at)})
                    ver = info.get("version")
                    doc.problems.append(Problem(
                        "finding", f"{section[:-1] if section.endswith('s') else section} {ename}: {single}.{ref_name} "
                        f"is not in remote {remote}'s model"
                        + (f" (version {ver}): it has no {single} {there}" if ver else " (it has not been read)")
                        + "; a stand-in with no sensor is drawn in its place until the remote serves it again, or the "
                        "reference is changed", at, "remote-reference-unresolved", f"{single}.{ref_name}"))


def _stand_in(doc, put, remote: str, plural: str, name: str, info: dict) -> bool:
    via = info["where"]
    gone = f"{remote}-gone"
    desc = f"missing from {remote}'s model: a stand-in for a part this model names"

    def end() -> None:
        if gone not in doc.sections["stocks"]:
            put("stocks", gone, as_map({"system": remote, "description": f"stands in for what {remote} no longer serves"},
                                       via), via, {})
    if plural == "stocks":
        body = {"system": remote, "description": desc}
    elif plural == "auxiliaries":
        body = {"system": remote, "description": desc, "exogenous": True}
    elif plural == "flows":
        end()
        body = {"from": gone, "system": remote, "description": desc}
    elif plural == "goals":
        end()
        body = {"stock": gone, "hold": ">= 0", "system": remote, "description": desc}
    elif plural == "blocks":
        body = {"type": "external", "system": remote, "description": desc}
    else:
        return False
    put(plural, name, as_map(body, via), via, {})
    info["parts"][f"{SINGULAR[plural]}.{name}"] = True
    if gone in doc.sections["stocks"]:
        info["parts"][f"stock.{gone}"] = True
    return True
