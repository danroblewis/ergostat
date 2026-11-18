"""A pool of workspaces (SPEC §12k), kept in the record: each workspace an item, ``ergostat.workspace/POOL-N``, whose
latest event says its state and whose it is (every event restates it whole):

- ``ergostat.workspace.acquired`` (in-use): an item's run took it: fresh, reused after a reset, or the same one again
  (a retry);
- ``.held`` (held): the item's lease ended and the item is not finished (its work is under review): kept for it;
- ``.released`` (free): the item finished, and the workspace was cleaned;
- ``.quarantined``: found dirty or broken; never given to another item until the owner frees it (``.freed``).

``acquire`` and ``release`` take the pool's lock (a file in its folder), so two runs never get one workspace."""

from __future__ import annotations

import fcntl
import re
import time
from contextlib import contextmanager
from pathlib import Path

from ..spec.ir import WORKSPACE, WorkspacePool
from .git import Broken, GitWorktrees

STATE_OF = {f"{WORKSPACE}.acquired": "in-use", f"{WORKSPACE}.held": "held", f"{WORKSPACE}.released": "free",
            f"{WORKSPACE}.quarantined": "quarantined", f"{WORKSPACE}.freed": "free"}
SOURCE = "ergostat"


class PoolError(Exception):
    """No workspace can be given: the pool is full, or one could not be made."""


class PoolFull(PoolError):
    """Every workspace is in use, held or quarantined: the item waits for one, through no fault of its own."""


def root_of(spec, path: str) -> Path:
    q = Path(path).expanduser()
    return q if q.is_absolute() else (spec.root / q)


def folder(p, spec, pool: WorkspacePool) -> Path:
    return (root_of(spec, pool.pool) if pool.pool else p.dir / "workspaces" / pool.name).resolve()


def backend(spec, pool: WorkspacePool) -> GitWorktrees:
    return GitWorktrees(root_of(spec, pool.repo).resolve(), pool.base)


def slot_item(pool: str, n: int) -> str:
    return f"{WORKSPACE}/{pool}-{n}"


def slots(p, spec, pool: WorkspacePool) -> dict[int, dict]:
    """Each workspace of the pool as the record has it now: its state and what its latest event said."""
    out = {}
    d = folder(p, spec, pool)
    for n in range(1, pool.size + 1):
        last = p.events.query(n=1, item=slot_item(pool.name, n), type=f"{WORKSPACE}.*")
        data = dict(last[0]["data"]) if last else {}
        out[n] = {**data, "slot": n, "pool": pool.name, "dir": data.get("dir") or str(d / str(n)),
                  "state": STATE_OF.get(last[0]["type"], "free") if last else "free",
                  "since": last[0]["time"] if last else None}
    return out


def counts(p, spec, name: str | None = None) -> dict[str, int]:
    out = {"free": 0, "in-use": 0, "held": 0, "quarantined": 0}
    for pool in spec.workspaces.values():
        if name is None or pool.name == name:
            for s in slots(p, spec, pool).values():
                out[s["state"]] += 1
    return out


def slug(text: str, most: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s[:most].rstrip("-") or "x"


def branch_for(template: str, item: str, fields: dict | None = None) -> str:
    """The item's branch, by the pool's template: ``{kind}`` (before the /), ``{id}`` (after it), ``{item}`` (whole),
    ``{slug}`` (its title, or name, summary, or id, in lowercase words), or any field of the item, made a safe ref."""
    kind, _, short = item.partition("/")
    fields = fields or {}
    title = next((fields[k] for k in ("title", "name", "summary", "idea") if isinstance(fields.get(k), str) and fields[k]),
                 short)
    vals = {k: v for k, v in fields.items() if isinstance(v, str | int | float) and not isinstance(v, bool)}
    vals.update({"kind": kind, "id": short, "item": item, "slug": slug(title)})

    class Blank(dict):
        def __missing__(self, k):
            return ""
    raw = template.format_map(Blank({k: str(v) for k, v in vals.items()}))
    ref = re.sub(r"[^A-Za-z0-9._/-]+", "-", raw)
    ref = re.sub(r"/+", "/", re.sub(r"\.\.+", ".", ref)).strip("/.-")
    ref = "/".join(part.removesuffix(".lock").strip(".") or "x" for part in ref.split("/"))
    return ref or slug(item)


@contextmanager
def locked(d: Path):
    d.mkdir(parents=True, exist_ok=True)
    with open(d / ".lock", "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _record(p, pool: str, n: int, what: str, data: dict, causedby: str | None = None) -> dict:
    return p.events.add(f"{WORKSPACE}.{what}", item=slot_item(pool, n), source=SOURCE, causedby=causedby,
                        data={"pool": pool, "slot": n, **data})


def acquire(p, spec, name: str, item: str, fields: dict | None = None, run: str | None = None,
            lease: int | None = None) -> dict:
    """A workspace for this item's run: the one it has already (a retry, or after review), else a free one reset for it
    (a dirty or broken one quarantined on the way), else a fresh worktree. Raises PoolError when none can be given.
    ``lease``: the fencing number of the lease the run holds on the item (SPEC §9.5), recorded with the workspace.
    Returns the workspace: ``dir``, ``branch``, ``slot``, ``how``, ``writes`` (what git needs written outside it)."""
    pool = spec.workspaces[name]
    be = backend(spec, pool)
    d = folder(p, spec, pool)
    with locked(d):
        st = slots(p, spec, pool)
        mine = next((s for s in st.values() if s.get("item") == item and s["state"] in ("in-use", "held")), None)
        if mine is not None:
            why = be.check(Path(mine["dir"]))
            if why is None or why.startswith("dirty"):           # its own work in progress: given back as it is
                got = {**mine, "how": "the same one again (its work as it left it)"}
                return _take(p, pool, got, run, lease, be)
            _record(p, pool.name, mine["slot"], "quarantined", {**_keep(mine), "why": why}, run)
        branch = branch_for(pool.branch, item, fields)
        for s in sorted(st.values(), key=lambda s: (not Path(s["dir"]).is_dir(), s["slot"])):
            if s["state"] != "free":
                continue
            sd = Path(s["dir"])
            if sd.exists():
                why = be.check(sd)
                if why is not None:
                    _record(p, pool.name, s["slot"], "quarantined", {**_keep(s), "dir": str(sd), "why": why}, run)
                    continue
                try:
                    how = be.reuse(sd, branch)
                except Broken as e:
                    _record(p, pool.name, s["slot"], "quarantined", {**_keep(s), "dir": str(sd), "why": str(e)}, run)
                    continue
            else:
                try:
                    how = be.make(sd, branch)
                except Broken as e:
                    raise PoolError(f"workspace pool {pool.name}: could not make a worktree for {item}: {e}") from e
            return _take(p, pool, {"slot": s["slot"], "dir": str(sd), "item": item, "branch": branch, "how": how},
                         run, lease, be)
        c = {k: sum(1 for s in st.values() if s["state"] == k) for k in ("in-use", "held", "quarantined")}
        raise PoolFull(f"workspace pool {pool.name} has none free for {item}: {c['in-use']} in use, {c['held']} held "
                        f"for review, {c['quarantined']} quarantined (of {pool.size})")


def _keep(s: dict) -> dict:
    return {k: s[k] for k in ("dir", "item", "branch") if s.get(k)}


def _take(p, pool: WorkspacePool, s: dict, run, lease, be: GitWorktrees) -> dict:
    if s.get("state") == "in-use" and s.get("run") == run and s.get("lease") == lease and run:
        data = {k: s.get(k) for k in ("dir", "item", "branch", "how", "run", "lease", "acquired")}   # its lease's, already
    else:
        data = {"dir": s["dir"], "item": s["item"], "branch": s["branch"], "how": s["how"], "run": run, "lease": lease,
                "acquired": time.time()}
        _record(p, pool.name, s["slot"], "acquired", data, run)
    try:
        writes = be.writes(Path(s["dir"]), s["branch"])
    except Broken:
        writes = []
    return {**data, "slot": s["slot"], "pool": pool.name, "writes": writes}


def held_by(p, spec, item: str) -> list[dict]:
    """The workspaces this item has (in use or held), in every pool."""
    return [s for pool in spec.workspaces.values() for s in slots(p, spec, pool).values()
            if s.get("item") == item and s["state"] in ("in-use", "held")]


def release(p, spec, item: str, finished: bool, why: str, causedby: str | None = None, lease: int | None = None,
            fenced: dict | None = None) -> list[dict]:
    """The item's lease ended (or its run, with no lease): each workspace it has is held for it while it is not
    finished, and cleaned (free) once it is; one dirty or broken when cleaned is quarantined. ``lease``: the fencing
    number of the lease that ended; a workspace a later lease has is left as it is. ``fenced``: the run, and its fence,
    whose lease expired while it goes on (recorded on the workspace held). Returns what was done."""
    done = []
    for pool in spec.workspaces.values():
        be = backend(spec, pool)
        with locked(folder(p, spec, pool)):
            for s in slots(p, spec, pool).values():
                if s.get("item") != item or s["state"] not in ("in-use", "held"):
                    continue
                if lease is not None and s.get("lease") is not None and s["lease"] != lease:
                    continue                                    # another lease has it now
                if not finished:
                    if s["state"] == "in-use":
                        kept = {**_keep(s), **{k: s[k] for k in ("run", "lease") if s.get(k) is not None}}
                        done.append(_record(p, pool.name, s["slot"], "held",
                                            {**kept, "why": why, **({"fenced": fenced} if fenced else {})}, causedby))
                    continue
                d = Path(s["dir"])
                bad = be.check(d)
                if bad is None:
                    try:
                        be.clean(d)
                    except Broken as e:
                        bad = str(e)
                if bad is None:
                    done.append(_record(p, pool.name, s["slot"], "released", {"dir": s["dir"], "why": why,
                                                                              "was": _keep(s)}, causedby))
                else:
                    done.append(_record(p, pool.name, s["slot"], "quarantined",
                                        {**_keep(s), "why": f"{bad}, when its item finished: kept for the owner"},
                                        causedby))
    return done


def free(p, spec, name: str, n: int, by: str = "owner") -> dict:
    """The owner frees a quarantined workspace: its worktree removed (this one only), the slot made anew when next
    needed."""
    pool = spec.workspaces[name]
    with locked(folder(p, spec, pool)):
        s = slots(p, spec, pool).get(n)
        if s is None:
            raise PoolError(f"workspace pool {name} has no workspace {n} (1 to {pool.size})")
        if s["state"] != "quarantined":
            raise PoolError(f"workspace {name}-{n} is {s['state']}: only a quarantined one is freed by hand")
        d = Path(s["dir"])
        if d.exists():
            backend(spec, pool).remove(d)
        return p.events.add(f"{WORKSPACE}.freed", item=slot_item(name, n), source=by,
                            data={"pool": name, "slot": n, "dir": str(d), "why": f"freed by {by}", "was": _keep(s)})
