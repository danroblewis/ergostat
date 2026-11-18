"""Reading ``workspaces:`` (SPEC §12k) into the spec, every mistake said with where it was written. Called by the spec
compiler with itself, for its ``named``, ``keys`` and ``err``."""

from __future__ import annotations

import string

from ..spec.ir import WorkspacePool

POOL_KEYS = {"type", "repo", "pool", "size", "branch", "base", "description"}
TYPES = ("git",)
FIELDS = ("kind", "id", "item", "slug")      # what a branch template always has; any field of the item besides


def workspaces(c, spec) -> None:
    for name, m, what in c.named("workspaces"):
        c.keys(m, POOL_KEYS, what)
        t = str(m.get("type") or "git")
        if t not in TYPES:
            c.err(f"{what}.type: {', '.join(TYPES)} (a git worktree per item)", m.at("type"), "bad-type")
            continue
        if not m.get("repo"):
            c.err(f"{what}: repo: the repository its workspaces are worktrees of (from the model's folder, or a whole "
                  f"path)", m.where, "missing-key")
            continue
        size = m.get("size", 2)
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            c.err(f"{what}.size: a whole number, 1 or more (how many workspaces it holds)", m.at("size"), "bad-number")
            size = 1
        branch = str(m.get("branch") or "{kind}/{id}-{slug}")
        try:
            names = [f for _, f, _, _ in string.Formatter().parse(branch) if f is not None]
        except ValueError as e:
            c.err(f"{what}.branch: a template like {{kind}}/{{id}}-{{slug}} ({e})", m.at("branch"), "bad-template")
            names = []
        if any(not f or not f.replace("_", "").replace("-", "").isalnum() for f in names):
            c.err(f"{what}.branch: each {{...}} names a field of the item ({', '.join(FIELDS)}, or one of its own)",
                  m.at("branch"), "bad-template")
        spec.workspaces[name] = WorkspacePool(name, str(m["repo"]), size, branch, str(m.get("base") or "HEAD"),
                                              str(m["pool"]) if m.get("pool") else None, t, c.text(m, "description"),
                                              m.where)
