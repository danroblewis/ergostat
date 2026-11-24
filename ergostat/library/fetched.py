"""The fetched libraries, at load (SPEC §2a): each ``libraries:`` entry's lock entry read, its copy in
``.libraries/NAME`` listed (``files.tree``) and hashed, and its templates parsed from those same bytes. The first
failure refuses the library, said as an error with its code; a refused library gives no template."""

from __future__ import annotations

import json
import posixpath
import re
from contextvars import ContextVar
from pathlib import Path

from ..spec import files
from ..spec.load import Problem
from . import sources, tree
from . import templates as tp
from . import untrusted as ut

LOCK, DIR = "libraries.lock", ".libraries"
# name -> (a copy's folder, the lock entry it would have): a candidate compiled in memory only (compare.py)
OVER: ContextVar[dict | None] = ContextVar("fetched_over", default=None)


def _lock(doc):
    """``libraries.lock``'s entries: None when it is missing; raises ValueError when it does not read."""
    try:
        got = json.loads(files.read_text(doc.root / LOCK))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, RecursionError) as e:
        raise ValueError(str(e)) from None
    if not isinstance(got, dict) or not all(isinstance(v, dict) for v in got.values()):
        raise ValueError("not a map of name to entry")
    return got


def _one(doc, name: str, e: dict, entries) -> list[tp.Template]:
    """The library's templates; raises (code, reason) when it is refused."""
    over = (OVER.get() or {}).get(name)
    lk = over[1] if over else entries.get(name) if entries is not None else None
    if lk is None and entries is None:
        raise Refusal("library-unlocked", f"there is no {LOCK} (ergostat library fetch writes it)")
    if not isinstance(lk, dict):
        raise Refusal("library-unlocked", f"{LOCK} has no entry for it (ergostat library fetch)")
    if any(lk.get(k) != e.get(k) for k in ("git", "version", "path")):
        raise Refusal("library-unlocked", f"its git, version or path is not {LOCK}'s (ergostat library fetch)")
    if not isinstance(lk.get("tree"), str) or not isinstance(lk.get("commit"), str):
        raise Refusal("library-unlocked", f"its {LOCK} entry has no tree or commit (ergostat library fetch)")
    root = Path(over[0]) if over else doc.root / DIR / name
    try:
        listing, h = tree.read(root)
    except FileNotFoundError:
        raise Refusal("library-missing", f"{DIR}/{name} does not exist (ergostat library fetch)") from None
    except (files.TreeError, OSError) as x:
        raise Refusal("library-altered", f"{DIR}/{name}: {x}") from None
    if h != lk["tree"]:
        raise Refusal("library-altered", f"{DIR}/{name} is not what {LOCK} pinned (its tree hash differs)")
    out = []
    for rel, (kind, data) in sorted(listing.items()):
        top = "/" not in rel and rel.endswith((".yaml", ".yml"))
        if kind in ("file", "exec") and (top or rel.count("/") == 1 and posixpath.basename(rel) == "template.yaml"):
            owner = e.get("trust") == "owner"
            try:
                t = tp.read(root / rel, False, "owner" if owner else "untrusted", text=data.decode("utf-8"))
            except (tp.TemplateError, UnicodeDecodeError) as x:      # an untrusted one's text marked, as a folder's
                said = f"library {name}: {x}"
                doc.problems.append(Problem("finding", said if owner else ut.note(root, said), None, "template-library"))
                continue
            t.library = name
            out.append(t)
    return out


class Refusal(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code, self.reason = code, reason


def take(doc, data) -> None:
    """The main file's ``libraries:``: ``doc.fetched`` (their templates, in config order) and ``doc.refused``."""
    libs = data["libraries"]
    try:
        cfg = sources.check(libs)
    except sources.SourceError as x:
        doc.problems.append(Problem("error", f"{x.field}: refused, {x.code} (SPEC §2a)", data.at("libraries"), x.code))
        why = Refusal(x.code, f"the libraries: section is refused at {x.field}, so none of its libraries is used")
        for name, e in libs.items() if isinstance(libs, dict) else ():    # each raw entry listed, as refused
            doc.listed[str(name)] = described(str(name), e if isinstance(e, dict) else {}, None, [], why)
        return
    try:
        entries, broken = _lock(doc), None
    except ValueError as x:
        entries, broken = None, Refusal("library-lock-unreadable", f"{LOCK} cannot be read: {x}")
    for name, e in cfg.items():
        doc.libraries.append(name)
        got, refusal = [], None
        try:
            if broken and name not in (OVER.get() or {}):
                raise broken
            got = _one(doc, name, e, entries)
            doc.fetched += got
        except Refusal as r:
            refusal = r
            doc.refused[name] = (r.code, r.reason)
            doc.problems.append(Problem("error", f"library {name} refused: {r.reason}", libs.at(name), r.code))
        over = (OVER.get() or {}).get(name)                 # a candidate is described by the lock entry it would have
        doc.listed[name] = described(name, e, over[1] if over else (entries or {}).get(name), got, refusal)


HEX = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
SHELL, HELD = "owner's shell", "sandbox or refused"
SECTION = ("bad-library-source", "too-many-libraries")            # sources.check's codes: the whole map refused


def described(name: str, e: dict, lk, templates: list, refusal: Refusal | None) -> dict:
    """One library as load read it (no network, no git): where from, its pin, whether its copy is the pinned one,
    its trust, and per template where its programs would run: the owner's shell only when the trust gate's own test
    (``templates.trusted``) proves it the owner's, else ``sandbox or refused`` (the gate decides per use which)."""
    commit = lk.get("commit") if isinstance(lk, dict) else None
    s = {k: v for k, v in e.items() if k in sources.KEYS and isinstance(v, str)}    # a refused section's: strings only
    return {"name": name, "git": s.get("git"), "version": s.get("version"), "path": s.get("path"),
            "commit": commit[:12] if isinstance(commit, str) and HEX.fullmatch(commit) else None,
            "tree": refusal.code if refusal else "ok", "reason": refusal.reason if refusal else None,
            "trust": "owner" if e.get("trust") == "owner" else "untrusted",
            "templates": {t.name: SHELL if tp.trusted(t) else HELD for t in templates}}


def line(d: dict) -> str:
    """``library NAME: URL @ VERSION (commit C), trust T, N templates; programs: ...``, as check and ``ergostat
    library`` say it. A refused untrusted library's reason (which may name its files) is marked."""
    p = ut.printable                              # a refused section's raw values: nothing a terminal acts on
    where = p(d["git"] or "no git URL") + (f" (path {p(d['path'])})" if d.get("path") else "")
    progs = ", ".join(f"{n} {v}" for n, v in d["templates"].items()) or "none offered"
    out = (f"library {p(d['name'])}: {where} @ {p(d['version'] or 'no version')} "
           f"(commit {d['commit'] or 'not pinned'}), trust {d['trust']}, "
           f"{len(d['templates'])} template{'' if len(d['templates']) == 1 else 's'}; programs: {progs}")
    if d["tree"] != "ok":
        why = ut.printable(d["reason"])
        mine = d["trust"] == "owner" or d["tree"] in SECTION           # a section refusal: the owner's file, not a copy
        out += f"; refused, {d['tree']}: " + (why if mine else ut.mark(why, ut.FILE))
    return out
