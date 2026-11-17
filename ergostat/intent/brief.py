"""What a piece of work is held to, and what it is (SPEC §12i): the intent judge's brief.

- **the work**: the item as it stands (its fields, its state, the moment it entered its judged state), its
  **done-when** (the field ``done_when``, verbatim from the message that started it: a follow-up's note), and its
  **change**: when it names a ``commit`` or a ``branch``, the diff of it against ``base`` in the repository ``repo``
  (with the files it touches as they were, so a judge can tell what the work brought in);
- **what it is held to**, each with its id, so a verdict's evidence can name it: the confirmed **decisions** in its
  scope (whose scope shares a word with the kind's ``scope``, or names none), with the alternatives the owner
  rejected; the confirmed **corrections** for its kind of work (``work``, else its scope; or ``general``; or naming
  the item); the owner's **messages** about it (sent about it, routed to it, or naming it); and its done-when.

Only what is confirmed holds: a proposed decision is not the owner's yet."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..spec.ir import IntentKind, Spec

DIFF_MAX = 16000           # the diff a judge reads, at most
FILE_MAX = 40000           # a file as it was, at most (for what the work brought in)
FIELD_MAX = 1500           # one field of the work, at most
SKIP_FIELDS = {"intent", "examples", "messages", "tool_calls", "tool_results", "thinking", "transcript"}


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _strs(v) -> list[str]:
    return [str(x) for x in v] if isinstance(v, list) else [str(v)] if v not in (None, "") else []


def _short(v, n: int = FIELD_MAX):
    if isinstance(v, str):
        return v if len(v) <= n else v[:n] + " [...]"
    import json
    s = json.dumps(v, default=str)
    return v if len(s) <= n else s[:n] + " [...]"


def git(repo: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)


def change(spec: Spec, kk: IntentKind, fields: dict) -> dict:
    """The work's change, when it names one: ``{"diff", "files": {path: text before}, "rev", "repo"}``, or why not."""
    rev = next((fields[k] for k in ("commit", "branch") if isinstance(fields.get(k), str) and fields[k]), None)
    if rev is None:
        return {"note": "it names no commit or branch: its change is not read"}
    root = spec.root.resolve()
    repo = (root / (kk.repo or ".")).resolve()
    if not (repo / ".git").exists() and git(repo, "rev-parse", "--git-dir").returncode != 0:
        return {"rev": rev, "note": f"{kk.repo or '.'} is not a git repository: its change is not read"}
    if isinstance(fields.get("commit"), str) and fields.get("commit") == rev:
        d = git(repo, "show", "--format=%H %s", "--unified=3", rev)
        base = f"{rev}^"
    else:
        mb = git(repo, "merge-base", kk.base, rev)
        base = mb.stdout.strip() or kk.base
        d = git(repo, "diff", "--unified=3", f"{base}..{rev}")
    if d.returncode != 0:
        return {"rev": rev, "note": f"git could not show {rev}: {d.stderr.strip()[:200]}"}
    files = {}
    for path in re.findall(r"^\+\+\+ b/(.+)$", d.stdout, re.M):
        before = git(repo, "show", f"{base}:{path}")
        files[path] = before.stdout[:FILE_MAX] if before.returncode == 0 else ""
    diff = d.stdout
    return {"rev": rev, "repo": kk.repo or ".", "base": base[:12], "files": files,
            "diff": diff if len(diff) <= DIFF_MAX else diff[:DIFF_MAX] + "\n[... the rest of the diff is cut]",
            "diff_cut": len(diff) > DIFF_MAX}


def in_scope(fields: dict, terms: set[str], keys: tuple[str, ...]) -> bool:
    tags = [w for k in keys for x in _strs(fields.get(k)) for w in words(x)]
    return not tags or bool(terms & set(tags)) or "general" in tags


def decisions(p, terms: set[str]) -> list[dict]:
    from ..decisions import acts
    from ..decisions.kinds import DECISION
    out = []
    for it in acts.items(p, DECISION):
        f = it.fields
        if it.state != "confirmed" or not in_scope(f, terms, ("scope",)):
            continue
        out.append({"id": it.id, "type": "decision", "text": f.get("decision") or "",
                    "words": [w.get("text", "")[:600] for w in (f.get("words") or [])[:2]],
                    "reasons": _strs(f.get("reasons"))[:4], "rejected": [a for a in f.get("alternatives") or [] if isinstance(a, dict)],
                    "scope": _strs(f.get("scope"))})
    return out


def corrections(p, terms: set[str], item: str) -> list[dict]:
    from ..decisions import acts
    from ..decisions.kinds import CORRECTION
    out = []
    for it in acts.items(p, CORRECTION):
        f = it.fields
        if it.state != "confirmed":
            continue
        named = item in str(f.get("corrects") or "") or item in _strs(f.get("scope"))
        if not named and not in_scope(f, terms, ("kind_of_work", "scope")):
            continue
        out.append({"id": it.id, "type": "correction", "text": f.get("correction") or "",
                    "words": [w.get("text", "")[:600] for w in (f.get("words") or [])[:2]],
                    "corrects": f.get("corrects") or "", "kind_of_work": _strs(f.get("kind_of_work"))})
    return out


def messages(p, spec: Spec, item: str, until: float | None = None) -> list[dict]:
    """The owner's messages about the work: sent about it, routed to it, or naming it (a block's words are not the
    owner's)."""
    from ..messages import record
    out = []
    for m in record.stored(p, since=None, until=until, n=20000).values():
        if (m.get("by") or "owner") in spec.blocks:
            continue
        routed = [t.get("item") for t in m.get("routed_to") or [] if isinstance(t, dict)]
        if item in (m.get("about") or []) or item in routed or re.search(rf"(?<![\w/]){re.escape(item)}(?![\w.])", m.get("text") or ""):
            out.append({"id": m["id"], "type": "message", "text": m.get("text") or "", "by": m.get("by"), "sent": m.get("sent")})
    return out


def build(p, spec: Spec, kk: IntentKind, it, entry: dict) -> dict:
    """The brief for judging ``it`` (a folded item) at ``entry`` (its move into ``kk.at``)."""
    f = dict(it.fields)
    done_when = f.get("done_when") or f.get("done-when") or (f.get("note") if f.get("follows") and f.get("message") else None)
    work = {"id": it.id, "kind": it.kind, "state": it.state, "at": kk.at, "entered": entry["time"],
            "entry_event": entry["event"], "done_when": str(done_when) if done_when else None,
            "fields": {k: _short(v) for k, v in f.items() if k not in SKIP_FIELDS and not str(k).startswith("_")}}
    terms = {w for s in [*kk.scope, it.kind or ""] for w in words(s) if len(w) > 1}
    wterms = {w for s in (kk.work or [*kk.scope, it.kind or ""]) for w in words(s) if len(w) > 1}
    against = [*decisions(p, terms), *corrections(p, wterms, it.id), *messages(p, spec, it.id)]
    if work["done_when"]:
        against.insert(0, {"id": "done-when", "type": "done-when", "text": work["done_when"]})
    ch = change(spec, kk, f)
    return {"work": work, "against": against, "diff": ch.get("diff"), "files": ch.get("files") or {},
            "change": {k: v for k, v in ch.items() if k not in ("diff", "files")}}
