"""A lease's terms (SPEC §9.5): its TTL and the attempts an item is allowed, the block's over its kind's over its tier's
(the model's ``leases:``) over the defaults. A program's TTL is at least its timeout: a run is never expired while it
is still allowed to run silent."""

from __future__ import annotations

from ..spec.ir import KIND_OF_TYPE, LEASE_ATTEMPTS, LEASE_TTL, Block, Spec


def tier_of(spec: Spec, b: Block) -> str:
    """The rung a block runs on: its agent's kind, else its type's."""
    a = spec.agents.get(b.agent or "")
    if a is not None and a.kind:
        return a.kind
    return KIND_OF_TYPE.get(b.type, "program")


def terms(spec: Spec, b: Block) -> dict:
    """``{"ttl": seconds, "attempts": n, "tier": rung, "from": {"ttl": where, "attempts": where}}``: each from the first
    that says it, the block, its kind, its tier in ``leases:``, the default."""
    tier = tier_of(spec, b)
    kind = spec.items.get(b.takes.kind) if b.takes else None
    layers = [("block", b.lease), ("kind", kind.lease if kind else None), ("leases", spec.leases.get(tier))]
    out: dict = {"tier": tier, "from": {}}
    for key, default in (("ttl", LEASE_TTL.get(tier, LEASE_TTL["program"])), ("attempts", LEASE_ATTEMPTS)):
        for name, t in layers:
            v = getattr(t, key, None) if t is not None else None
            if v is not None:
                out[key], out["from"][key] = v, name
                break
        else:
            out[key], out["from"][key] = default, "default"
    if tier == "program" and out["from"]["ttl"] == "default":
        out["ttl"] = max(out["ttl"], b.timeout)       # a program's own timeout: silent that long is allowed
    return out


def grace(ttl: float) -> float:
    """How long a lease found past its TTL waits for the watchdog's second look before it expires (``dispatch.py``): a
    tenth of its TTL, at least one pass of the watchdog (a second) and at most half a minute."""
    return max(1.0, min(0.1 * ttl, 30.0))
