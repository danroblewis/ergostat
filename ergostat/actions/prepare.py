"""An ``ai`` block's run made ready (SPEC §12k): the item it works on, its folder (a workspace from its pool for that
item, or its ``workdir:``), what else it may read, and, when it is gated, its tools and actions, written to the file
``$ERGOSTAT_SANDBOX`` names (``sandbox.write``) for the session it starts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import sandbox as sb

KEYS = ("workdir", "workspace", "read", "tools", "actions")


@dataclass
class Prepared:
    cfg: dict | None = None          # what the session is given (None: nothing said; it runs as before)
    workdir: Path | None = None      # its folder (None: the model's)
    workspace: dict | None = None    # the workspace it took
    item: str | None = None
    lease: int | None = None         # the fencing number of the lease the run holds on its item (SPEC §9.5)


def item_of(ctx: dict, env: dict, given: dict | None) -> tuple[str | None, int | None]:
    """The item a run works on, and its lease's fencing number: the lease's (``ERGOSTAT_ITEM``, ``ERGOSTAT_LEASE``),
    else its context's item, else what its command names."""
    from ..workspaces.leases import fence_of
    item = env.get("ERGOSTAT_ITEM") or (given or {}).get("item") or (ctx.get("command") or {}).get("item")
    return (str(item) if item else None), fence_of(env.get("ERGOSTAT_LEASE"))


def prepare(p, spec, b, ctx: dict, run: str, env: dict, given: dict | None) -> Prepared:
    """Raises ``PoolError`` when its pool can give it no workspace (or it names no item to take one for)."""
    from ..workspaces import pool as pl
    if not any(b.params.get(k) is not None for k in KEYS):
        return Prepared()
    item, lease = item_of(ctx, env, given)
    out = Prepared(item=item, lease=lease)
    if b.params.get("workspace"):
        if not item:
            raise pl.PoolError(f"workspace pool {b.params['workspace']}: this run names no item to take a workspace "
                               f"for (a lease's ERGOSTAT_ITEM, its context's item, or its command's item)")
        from ..workspaces.leases import fields_of
        out.workspace = pl.acquire(p, spec, b.params["workspace"], item, fields_of(p, spec, item), run, lease)
        out.workdir = Path(out.workspace["dir"])
    elif b.params.get("workdir"):
        out.workdir = pl.root_of(spec, b.params["workdir"]).resolve()
        if not out.workdir.is_dir():
            raise pl.PoolError(f"workdir {b.params['workdir']}: no such folder ({out.workdir})")
    read = [str(pl.root_of(spec, r).resolve()) for r in b.params.get("read") or []]
    acts = [spec.actions[a] for a in b.params.get("actions") or [] if a in spec.actions]
    cfg = {"block": b.name, "run": run, "item": item, "lease": lease, "root": str(spec.root), "state": str(p.dir),
           "workdir": str(out.workdir or spec.root), "branch": (out.workspace or {}).get("branch"), "read": read,
           "writes": (out.workspace or {}).get("writes") or [], "tools": b.params.get("tools"),
           "actions": [a.name for a in acts], "waits": [a.wait + a.timeout for a in acts]}
    cfg["file"] = str(sb.write(p, b.name, run, cfg))
    out.cfg = cfg
    env["ERGOSTAT_SANDBOX"] = cfg["file"]
    env["ERGOSTAT_WORKDIR"] = cfg["workdir"]
    if item:
        env.setdefault("ERGOSTAT_ITEM", item)
    if out.workspace:
        env["ERGOSTAT_WORKSPACE"] = out.workspace["dir"]
        env["ERGOSTAT_BRANCH"] = out.workspace["branch"]
        ctx["workspace"] = {k: out.workspace[k] for k in ("pool", "slot", "dir", "branch", "how")}
    if acts:
        env.update(sb.env(cfg))
    return out
