"""The fetched libraries, at load (SPEC §2a): each ``libraries:`` entry's lock entry read, its copy in
``.libraries/NAME`` listed (``files.tree``) and hashed, and its templates parsed from those same bytes. The first
failure refuses the library, said as an error with its code; a refused library gives no template."""

from __future__ import annotations

import json
import posixpath

from ..spec import files
from ..spec.load import Problem
from . import sources, tree
from . import templates as tp
from . import untrusted as ut

LOCK, DIR = "libraries.lock", ".libraries"


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
    lk = entries.get(name) if entries is not None else None
    if entries is None:
        raise Refusal("library-unlocked", f"there is no {LOCK} (ergostat library fetch writes it)")
    if not isinstance(lk, dict):
        raise Refusal("library-unlocked", f"{LOCK} has no entry for it (ergostat library fetch)")
    if any(lk.get(k) != e.get(k) for k in ("git", "version", "path")):
        raise Refusal("library-unlocked", f"its git, version or path is not {LOCK}'s (ergostat library fetch)")
    if not isinstance(lk.get("tree"), str) or not isinstance(lk.get("commit"), str):
        raise Refusal("library-unlocked", f"its {LOCK} entry has no tree or commit (ergostat library fetch)")
    root = doc.root / DIR / name
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
        return
    try:
        entries, broken = _lock(doc), None
    except ValueError as x:
        entries, broken = None, Refusal("library-lock-unreadable", f"{LOCK} cannot be read: {x}")
    for name, e in cfg.items():
        doc.libraries.append(name)
        try:
            if broken:
                raise broken
            doc.fetched += _one(doc, name, e, entries)
        except Refusal as r:
            doc.refused[name] = (r.code, r.reason)
            doc.problems.append(Problem("error", f"library {name} refused: {r.reason}", libs.at(name), r.code))
