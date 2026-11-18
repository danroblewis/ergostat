"""Reading leases into the spec (SPEC §9.5): ``leases:`` (each tier's terms), a kind's ``lease:``, and a block's
``takes:``, ``pool:`` and ``lease:``, every mistake said with where it was written. Called by the spec compiler with
itself, for its ``named``, ``keys``, ``err`` and ``duration``."""

from __future__ import annotations

from ..spec.ir import DEAD, LEASED, TIERS, LeaseTerms, Spec, Takes

TERMS_KEYS = {"ttl", "attempts"}
TAKES_KEYS = {"kind", "at", "to", "where"}


def terms(c, m, key: str, what: str) -> LeaseTerms:
    """``lease: {ttl: 40m, attempts: 3}`` (either may be left out)."""
    raw = m.get(key)
    if raw is None:
        return LeaseTerms()
    if not isinstance(raw, dict):
        c.err(f"{what}.{key}: a map: ttl: (how long a run may be silent, 40m) and attempts: (before a dead letter, 3)",
              m.at(key), "not-a-map")
        return LeaseTerms()
    return terms_of(c, raw, f"{what}.{key}")


def terms_of(c, raw, what: str) -> LeaseTerms:
    c.keys(raw, TERMS_KEYS, what)
    ttl = c.duration(raw, "ttl", what)
    if ttl is not None and ttl <= 0:
        c.err(f"{what}.ttl: longer than nothing", raw.at("ttl"), "bad-duration")
        ttl = None
    n = raw.get("attempts")
    if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 1):
        c.err(f"{what}.attempts: a whole number, 1 or more", raw.at("attempts"), "bad-number")
        n = None
    return LeaseTerms(ttl, n)


def section(c, spec: Spec) -> None:
    """``leases:``: each tier's terms (``ai: {ttl: 40m}``), over the defaults."""
    for name, m, _ in c.named("leases"):
        if name not in TIERS:
            c.err(f"leases.{name}: a tier of the ladder ({', '.join(TIERS)})" + c.suggest(name, TIERS), m.where, "bad-tier")
            continue
        spec.leases[name] = terms_of(c, m, f"leases.{name}")


def takes(c, m, what: str) -> Takes | None:
    """``takes: {kind: ticket, at: ready}``, with ``to:`` (the states that count as done) and ``where:``."""
    raw = m.get("takes")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        c.err(f"{what}.takes: a map: kind: (a kind of item) and at: (the state it takes them from)", m.at("takes"),
              "not-a-map")
        return None
    c.keys(raw, TAKES_KEYS, f"{what}.takes")
    kind, at = raw.get("kind"), raw.get("at")
    if not isinstance(kind, str) or at is None:
        c.err(f"{what}.takes: kind: and at: (takes: {{kind: ticket, at: ready}})", m.at("takes"), "missing-key")
        return None
    states = [at] if isinstance(at, str) else at
    to = raw.get("to") or []
    to = [to] if isinstance(to, str) else to
    if not isinstance(states, list) or not all(isinstance(x, str) for x in states) or not states:
        c.err(f"{what}.takes.at: a state, or a list of them", raw.at("at"), "bad-states")
        return None
    if not isinstance(to, list) or not all(isinstance(x, str) for x in to):
        c.err(f"{what}.takes.to: a state, or a list of them (the states that count as done)", raw.at("to"), "bad-states")
        to = []
    where = raw.get("where") or {}
    if not isinstance(where, dict):
        c.err(f"{what}.takes.where: a map of field: value (or a list of values)", raw.at("where"), "not-a-map")
        where = {}
    return Takes(kind, list(states), list(to), dict(where))


def pool(c, m, what: str) -> int:
    n = m.get("pool", 1)
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        c.err(f"{what}.pool: a whole number, 1 or more (the most runs of it at once)", m.at("pool"), "bad-number")
        return 1
    return n


def check(c, spec: Spec) -> None:
    """After the blocks: what each takes is a kind of the model's own, in its states; a kind taken gains the states a
    lease moves it through (``leased``, ``dead``) when it does not list them; a block that takes is started by its
    items, so neither every: nor cron: (nor a pool without takes:)."""
    for b in spec.blocks.values():
        what = f"block {b.name}"
        if b.takes is None:
            if b.pool != 1:
                c.err(f"{what}.pool: only a block that takes items runs more than once at a time (takes: {{kind: K, at: S}})",
                      b.where, "pool-without-takes")
            continue
        if b.type not in ("program", "ai"):
            c.err(f"{what}.takes: only a program or an ai block takes items (a run of it per item)", b.where, "bad-takes")
            b.takes = None
            continue
        if b.every or b.cron:
            c.err(f"{what}: a block that takes items is started by them (each item that reaches "
                  f"{', '.join(b.takes.at)}), not by every: or cron:", b.where, "takes-with-schedule")
        k = spec.items.get(b.takes.kind)
        if k is None or b.takes.kind.startswith("ergostat."):
            own = ", ".join(x for x in spec.items if not x.startswith("ergostat."))
            c.err(f"{what}.takes.kind: {b.takes.kind!r} is not a kind of item of the model's own ({own or 'none'})"
                  + c.suggest(b.takes.kind, spec.items), b.where, "unknown-ref")
            b.takes = None
            continue
        bad = [s for s in [*b.takes.at, *b.takes.to] if s not in k.states and s not in (LEASED, DEAD)]
        if bad:
            c.err(f"{what}.takes: {', '.join(map(repr, bad))} {'is not a state' if len(bad) == 1 else 'are not states'} of "
                  f"{k.name} ({', '.join(k.states) or 'it has none'})", b.where, "unknown-state")
            b.takes = None
            continue
        if any(s in (LEASED, DEAD) for s in b.takes.at):
            c.err(f"{what}.takes.at: {LEASED} and {DEAD} are a lease's own states; take items from a state of the work",
                  b.where, "bad-takes")
            b.takes = None
            continue
        if LEASED not in k.states:                       # held by a run: after the first state it is taken from
            k.states.insert(k.states.index(b.takes.at[0]) + 1, LEASED)
        if DEAD not in k.states:
            k.states.append(DEAD)
