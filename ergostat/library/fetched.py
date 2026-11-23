"""Fetched libraries (``libraries:``, SPEC §2a, *Fetched libraries*), loaded only as ``libraries.lock`` pins them.

Each library is checked in turn and refused by name, none of its templates loaded, on the first of: no lock, no entry,
an entry without a ``commit`` or ``tree``, or one whose ``git``, ``version`` or ``path`` differ from ``libraries:``
(library-unlocked); a lock that does not read (library-lock-unreadable); no copy (library-missing); a copy that is a
link, holds a kind or size ``files.tree`` refuses, or whose digest is not the lock's ``tree`` (library-altered). Its
templates are parsed from the very bytes that were hashed. ``trust: owner`` makes a library trusted; any other is
untrusted exactly as a ``{folder: PATH}`` is: marked, held by the allowlist and bounded, through ``Template.trust``."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..spec import files
from ..spec.load import Problem
from . import sources, tree
from . import templates as tp
from . import untrusted as ut
from .fetch import FOLDER, LOCK

TRUST = ("owner", "untrusted")


class Refused(Exception):
    def __init__(self, code: str, why: str):
        super().__init__(why)
        self.code = code


def split(libraries) -> tuple[dict, dict]:
    """``libraries:`` checked by ``sources.check``, each entry's ``trust:`` (owner or untrusted) taken out first."""
    if not isinstance(libraries, dict):
        raise sources.SourceError("bad-library-source", "libraries")
    bare, trust = {}, {}
    for name, e in libraries.items():
        if isinstance(e, dict) and "trust" in e:
            if e["trust"] not in TRUST:
                raise sources.SourceError("bad-library-source", f"libraries.{name}.trust (owner or untrusted)")
            trust[name], e = e["trust"], {k: v for k, v in e.items() if k != "trust"}
        bare[name] = e
    return sources.check(bare), trust


def add(doc, got: dict, notes: list) -> list[str]:
    """Each fetched library's templates into ``got``: a name already there stays, unless only the fetched one is
    trusted (said in ``notes``). Each refusal is an error at its ``libraries:`` line; returned as ``library NAME
    (CODE: why)`` for the unknown-template message."""
    libs = doc.libraries
    if libs is None:
        return []
    at = libs.at if hasattr(libs, "at") else lambda _name: None
    try:
        wanted, trust = split(libs)
    except sources.SourceError as e:
        doc.problems.append(Problem("error", f"libraries: refused, no library loaded: {e}", at("libraries"), e.code))
        return [f"libraries: ({e})"]
    try:
        locks: dict | Refused | None = _lock(doc.root)
    except Refused as e:
        locks = e
    refused = []
    for name, src in wanted.items():
        try:
            if isinstance(locks, Refused):
                raise locks
            walked = _one(doc.root, name, src, locks)
        except Refused as e:
            refused.append(f"library {name} ({e.code}: {e})")
            doc.problems.append(Problem("error", f"library {name}: refused, none of its templates loaded: {e}", at(name),
                                        e.code))
            continue
        _take(doc.root / FOLDER / name, name, trust.get(name, "untrusted"), walked, got, notes)
    return refused


def _lock(root: Path) -> dict | None:
    """``libraries.lock`` as name -> entry, read as the model's files are (so kept in the snapshot); None: no lock."""
    try:
        got = json.loads(files.read_text(root / LOCK))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, RecursionError) as e:
        raise Refused("library-lock-unreadable", f"{LOCK} does not read: {e}") from None
    if not isinstance(got, dict) or not all(isinstance(v, dict) for v in got.values()):
        raise Refused("library-lock-unreadable", f"{LOCK} is not a map of name to entry")
    return got


def _one(root: Path, name: str, src: dict, locks: dict | None) -> dict:
    """The copy's listing (``files.tree``), once it is seen to be what the lock entry pins."""
    fix = f"run ergostat library fetch {name}"
    entry = (locks or {}).get(name)
    if entry is None:
        raise Refused("library-unlocked", f"no {LOCK}; {fix}" if locks is None else f"no entry in {LOCK}; {fix}")
    if not all(isinstance(entry.get(k), str) and entry[k] for k in ("commit", "tree")):
        raise Refused("library-unlocked", f"its {LOCK} entry has no commit or no tree; {fix}")
    changed = [k for k in sources.KEYS if entry.get(k) != src.get(k)]
    if changed:
        raise Refused("library-unlocked", f"its {', '.join(changed)} differ from {LOCK}'s; {fix} --update")
    copy = root / FOLDER / name
    if not files.replaying() and (os.path.islink(root / FOLDER) or os.path.islink(copy)):
        raise Refused("library-altered", f"{FOLDER}/{name} is a link or under one")
    try:
        walked = files.tree(copy, tree.ENTRIES, tree.BYTES)
    except FileNotFoundError:
        raise Refused("library-missing", f"no copy at {FOLDER}/{name}; {fix}") from None
    except (files.TreeError, OSError) as e:        # (only the code or strerror: a path in the copy is the library's)
        why = e.code if isinstance(e, files.TreeError) else e.strerror or type(e).__name__
        raise Refused("library-altered", f"{FOLDER}/{name} is not a copy fetch would leave ({why})") from None
    if tree.of(walked) != entry["tree"]:
        raise Refused("library-altered", f"{FOLDER}/{name} is not the tree {LOCK} pins; {fix} --update to take it")
    return walked


def _take(copy: Path, name: str, trust: str, walked: dict, got: dict, notes: list) -> None:
    """The templates in a checked listing, where a folder's would be found (``*.yaml``, ``*.yml``,
    ``*/template.yaml``, no dot-names), parsed from the listing's bytes; an untrusted one's notes marked."""
    def said(text: str, untrusted: bool, folder) -> str:
        return ut.note(folder, text) if untrusted else text
    for p in sorted(walked):
        kind, body = walked[p]
        steps = p.split("/")
        if kind not in ("file", "exec") or any(s.startswith(".") for s in steps) or not (
                len(steps) == 1 and p.endswith((".yaml", ".yml")) or len(steps) == 2 and steps[1] == "template.yaml"):
            continue
        try:
            t = tp.read(copy / p, False, trust, body.decode("utf-8"))
        except (tp.TemplateError, UnicodeDecodeError) as e:
            notes.append(said(f"template {copy / p}: {e}" if isinstance(e, UnicodeDecodeError) else str(e),
                              trust != "owner", copy))
            continue
        t.library = name
        was = got.get(t.name)
        kept, skipped = (t, was) if was is None or tp.trusted(t) and not tp.trusted(was) else (was, t)
        got[t.name] = kept
        if skipped is not None:
            notes.append(said(f"template {t.name}: {skipped.path} is not used; "
                              f"{"ergostat's own" if kept.builtin else kept.path} is", skipped.untrusted,
                              skipped.path.parent))
