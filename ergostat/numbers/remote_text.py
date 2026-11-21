"""A change the modelling loop finds for a remote's part, written as text for that remote's owner (SPEC §4c, "Proposals
for its owner"): in the remote's own names, against the version of its model that was read, never applied here and
never sent by ergostat (sending it is the owner's act).

A parameter's estimate or a flow's equation becomes such a text when every part it would edit is one remote's
(``owner_of``). Every name in it is looked up in what the remote served (``info["names"]``, never a stand-in): one
missing and nothing is written. It is recorded (``record``) under the proposals' lock and, inside that, the remote's
cache lock, only when the version in the cache file is the version the evidence was computed on. It holds the fields
of ``FIELDS`` and no other: no fit, no gate, no edit. Its state is ``checked``; ``proposals.pending`` leaves it out."""

from __future__ import annotations

import re
import time
from pathlib import Path

from ..remote import cache
from ..remote.compose import RemoteVia
from . import proposals as pr
from . import yamledit as ye

FIELDS = ("kind", "title", "text", "evidence", "for_remote", "subject", "made_by", "created", "made")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_TOKEN = re.compile(r"(?<![\w.-])([a-z][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)?)(?![\w.-])")


class _Miss(Exception):
    pass


def edited(x: dict) -> list[str]:
    """The parts a found change would edit: a parameter proposal's parameters, an equation's flow."""
    if x.get("kind") == "parameter":
        return [f"parameter.{n}" for n in x.get("parameters") or {}]
    return [x["target"]] if x.get("kind") == "equation" and x.get("target") else []


def owner_of(spec, refs) -> str | None:
    """The remote every one of ``refs`` was brought in from; "" when none is a remote's; None when they are mixed (this
    model's and a remote's, or two remotes', or a part not in the model)."""
    owners = set()
    for r in refs:
        part = pr._part(spec, r)
        if part is None:
            return None
        w = getattr(part, "defined", None)
        owners.add(w.remote if isinstance(w, RemoteVia) else "")
    if len(owners) != 1:
        return None if owners else ""
    return owners.pop()


def lookup(spec, remote: str, ref: str) -> str:
    """A local part's name at the remote, from what it served (stand-ins are never there): raises ``_Miss``."""
    got = (((spec.remotes or {}).get(remote) or {}).get("names") or {}).get(ref)
    if not got:
        raise _Miss(ref)
    return got


def _bare(ref: str) -> str:
    return ref.split(".", 1)[1]


def _said(prm, v, se=None) -> str:
    if v is None:
        return "no value"
    num = ye.duration(v) if prm.duration else f"{ye.number(v)}{' ' + prm.unit if prm.unit else ''}"
    return num if se is None else f"{num} ± {ye.duration(se) if prm.duration else ye.number(se)}"


def _parameter(spec, x: dict, name) -> tuple[str, str, dict]:
    sets, heads = [], []
    for n, new in x["parameters"].items():
        prm = spec.parameters[n]
        there = name(f"parameter.{n}")
        was, to = _said(prm, prm.value), _said(prm, new, (x.get("uncertainty") or {}).get(n))
        sets.append(f"set {there} from {was} to {to}")
        heads.append(f"{there}: {was} → {to}")
    users = [name(r) for r in x.get("parts") or []]
    read = [name(r) for r in x.get("touched") or []]
    e = (x.get("estimate") or {}).get(next(iter(x["parameters"]))) or {}
    ev = {"points": e.get("n"), "window": e.get("window"), "read": read}
    text = ("; ".join(sets) + " (±: one standard error of the estimate)." +
            (f" {'They are' if len(sets) > 1 else 'It is'} used by {', '.join(users)}." if users else ""))
    return "; ".join(heads), text, ev


def _equation(spec, x: dict, name, window: float) -> tuple[str, str, dict]:
    target = name(x["target"])
    f = spec.flows[x["target"].split(".", 1)[1]]
    causes = [name(f"{r.kind}.{r.name}") for r in f.driven_by]
    names = (spec.remotes[x["_remote"]].get("names") or {}).values()
    taken = {_bare(r) for r in names if r.startswith("parameter.")}
    new: dict[str, str] = {}
    for nm, (role, of) in ((x.get("for_text") or {}).get("roles") or {}).items():
        made = {"per": f"{_bare(target)}-per-{_bare(name(of))}" if role == "per" else "",
                "time-in": f"time-in-{_bare(name(of))}", "base": f"{_bare(target)}-base"}.get(role)
        if not made:
            raise _Miss(nm)
        new[nm] = pr._free(made, taken)
        taken.add(new[nm])
    if set(new) != set(x.get("parameters") or {}):
        raise _Miss(", ".join(sorted(set(x.get("parameters") or {}) ^ set(new))))

    def there(m):
        tok = m.group(1)
        if tok in new:
            return new[tok]
        if "." in tok:
            return name(tok)
        raise _Miss(tok)
    text_eq = _TOKEN.sub(there, x["equation"])
    values = [f"{new[nm]} = {ye.duration(v['value']) if v.get('unit') == 'h' else ye.number(v['value'])}"
              f"{' ' + v['unit'] if v.get('unit') and v.get('unit') != 'h' else ''}"
              for nm, v in (x.get("parameters") or {}).items()]
    text = (f"give {target} the equation {text_eq}" +
            (f", with the new parameter{'s' if len(values) > 1 else ''} {'; '.join(values)} (estimate: true)" if values else "")
            + ".")
    ev = {"points": (x.get("for_text") or {}).get("points"), "window": window, "read": [target, *causes]}
    return f"{_bare(target)} = {text_eq}", text, ev


def text_of(spec, x: dict, window: float) -> dict | str:
    """A found parameter or equation proposal for one remote's parts, as the record written for its owner; else why
    nothing is written (a name not served there)."""
    remote = owner_of(spec, edited(x))
    if not remote:
        return "not all of its parts are one remote's"
    info = (spec.remotes or {}).get(remote) or {}
    parts: dict[str, str] = {}

    def name(ref: str) -> str:
        parts[ref] = lookup(spec, remote, ref)
        return parts[ref]
    try:
        if x["kind"] == "parameter":
            title, said, ev = _parameter(spec, x, name)
        else:
            title, said, ev = _equation(spec, {**x, "_remote": remote}, name, window)
    except _Miss as e:
        return f"{e.args[0]} is not among the parts remote {remote} serves: nothing is written for it"
    v = info.get("version")
    text = (f"For remote {remote}'s owner, on its model as read at version {v}: {said} Evidence: "
            f"{ev['points']} points over {_dur(ev['window'])} of {', '.join(ev['read']) or 'its readings'}, as read "
            f"from {remote}. Never applied here, never sent by ergostat.")
    refs = [r for r in [*(x.get("parts") or []), *(x.get("touched") or []), *str(x.get("target") or "").split(", ")] if r]
    now = time.time()
    return {"id": x["id"], "kind": x["kind"], "title": f"{remote}: {title}", "text": text, "evidence": ev,
            "for_remote": {"remote": remote, "version": v, "parts": parts},
            "subject": pr.subject(spec, [r for r in refs if pr._part(spec, r) is not None]),
            "made_by": "ergostat", "created": now, "made": now}


def _dur(s) -> str:
    from .. import series
    try:
        return f"the last {series.dur(float(s))}"
    except (TypeError, ValueError):
        return "the window read"


def split(spec, found: list[dict], window: float) -> tuple[list[dict], dict[str, dict | None]]:
    """The found changes kept as this model's own, and those for a remote's owner by id (None: one that could not be
    written, which records nothing and leaves what is under its id as it is)."""
    local, texts = [], {}
    for x in found:
        more = x.pop("for_text", None)
        if x.get("kind") not in ("parameter", "equation") or x.get("scope") == "what-if" or not owner_of(spec, edited(x)):
            local.append(x)
            continue
        got = text_of(spec, {**x, "for_text": more}, window)
        texts[x["id"]] = got if isinstance(got, dict) else None
    return local, texts


def folder(p, spec, remote) -> Path | None:
    """The remote's cache folder, its name checked and the path confirmed under ``<state>/remotes``; None if not."""
    if not isinstance(remote, str) or not NAME.fullmatch(remote):
        return None
    root = (Path(p.dir) / "remotes").resolve()
    d = (root / remote).resolve()
    info = (getattr(spec, "remotes", None) or {}).get(remote) or {}
    if d.parent != root or not d.is_dir() or (info.get("dir") and Path(info["dir"]).resolve() != d):
        return None
    return d


def _same(a, b) -> bool:
    """Both versions read (non-empty strings) and equal."""
    return isinstance(a, str) and isinstance(b, str) and bool(a) and a == b


def _differ(a, b) -> bool:
    """Both versions read (non-empty strings) and not equal."""
    return isinstance(a, str) and isinstance(b, str) and bool(a) and bool(b) and a != b


def current(x: dict, spec) -> bool:
    """Written against the version of the remote's model this model has read now (both read, and equal)."""
    fr = x.get("for_remote") or {}
    info = (getattr(spec, "remotes", None) or {}).get(fr.get("remote"))
    return info is not None and _same(fr.get("version"), info.get("version"))


def record(p, spec, xs: list[dict]) -> list[str]:
    """``_record`` under the proposals' lock."""
    with pr.locked(p):
        return _record(p, spec, xs)


def _record(p, spec, xs: list[dict]) -> list[str]:
    """Each text recorded, the proposals' lock held: under the remote's cache lock, the version in its file read and
    held to the version the evidence was computed on, then the events appended (refused, nothing written, when either
    is missing or they differ). One left as it is when found again as it was at the same version, or dismissed there.
    Under the same id a change of this model's own (whatever became of it) is superseded first; every old field outside
    ``FIELDS`` is cleared by the made event."""
    have, folds, out = pr.stored(p), pr.changes(p), []
    for r in xs:
        fr = r["for_remote"]
        d = folder(p, spec, fr["remote"])
        if d is None:
            continue
        was = have.get(r["id"])
        if was is not None and was.get("for_remote") and (was.get("for_remote") or {}).get("version") == fr["version"] \
                and (was["status"] == "dismissed" or was["state"] in pr.OPEN and was.get("text") == r["text"]):
            continue
        old = (folds.get(r["id"]) or (None, {}))[1]
        gone = (*old, "why", "version_now") if old else ()                            # (and the supersede's own)
        body = {**{k: None for k in gone if k not in FIELDS},
                **{k: r[k] for k in FIELDS}}
        with cache.locked(d):
            v = cache.version(d)
            if not _same(v, fr["version"]):
                continue
            if was is not None and not was.get("for_remote"):
                pr.event(p, r["id"], "superseded",
                         {"why": f"its part is now remote {fr['remote']}'s: written as text for its owner"})
            pr.event(p, r["id"], "made", body)
            pr.event(p, r["id"], "checked", {})
        out.append(r["id"])
    return out


def moved(p, spec) -> list[str]:
    """Every open text whose remote's model, read now from its cache file under the cache lock, is another version:
    superseded saying so. A version that can't be read supersedes nothing (``listing`` says it is not current)."""
    out = []
    for pid, x in pr.stored(p).items():
        fr = x.get("for_remote")
        if not fr or x["state"] not in pr.OPEN:
            continue
        d = folder(p, spec, fr.get("remote"))
        if d is None:
            continue
        with cache.locked(d):
            v = cache.version(d)
            if not _differ(fr.get("version"), v):
                continue
            pr.event(p, pid, "superseded", {"why": f"remote {fr['remote']}'s model moved from {fr['version']} to {v} "
                                                   f"since it was written", "version_now": v})
        out.append(pid)
    return out


def why_not(p, spec, x: dict) -> str | None:
    """Why a text is not current (None: it is). Read only: no lock, nothing written."""
    fr = x.get("for_remote") or {}
    name = fr.get("remote")
    d = folder(p, spec, name)
    v = cache.version(d) if d is not None else None
    if v is None:
        return f"remote {name}'s model's version can't be read"
    if not current(x, spec):
        now = ((getattr(spec, "remotes", None) or {}).get(name) or {}).get("version")
        return f"written against {fr.get('version') or 'no version'}; this model read {name} at {now or 'no version'}"
    if v != fr.get("version"):
        return f"remote {name}'s model moved from {fr.get('version')} to {v} since it was written"
    return None


def listing(p, spec, name: str | None = None) -> tuple[list[dict], list[str]]:
    """The open and the dismissed texts (of one remote, or all), oldest first, each with whether it is current and why
    not; and the remotes whose version can't be read. Read only."""
    rows = []
    for x in sorted(pr.stored(p).values(), key=lambda x: x.get("created") or 0):
        fr = x.get("for_remote")
        if not fr or (name and fr.get("remote") != name) or not (x["state"] in pr.OPEN or x["status"] == "dismissed"):
            continue
        why = why_not(p, spec, x)
        rows.append({**{k: v for k, v in x.items() if v is not None}, "current": why is None, "not_current_because": why})
    unread = [r for r in (getattr(spec, "remotes", None) or {}) if (not name or r == name)
              and ((d := folder(p, spec, r)) is None or cache.version(d) is None)]
    return rows, unread
