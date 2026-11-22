"""Relations between items (SPEC §5a, *Relations*): a kind declares typed relations to other items, each a field
holding the ids it names, folded as a set (the ``relation`` fold rule: ids added, or ``{set, add, remove}``) with
its history like any field's. Cross-kind: a ticket's ``parent`` is an epic.

```yaml
items:
  ticket:
    id: ticket/*
    relations:
      blocked_by: ticket                 # a kind (or a list of kinds); precedence: it comes after them
      parent: epic                       # a group: the Graph view hangs its children off it
      duplicates: {kind: ticket, inverse: duplicated_by}
```

What a relation is, besides its kinds: ``precedence`` (its targets come first: the item is ready only once each is
finished), ``inverse`` (the other direction's name, derived by ergostat: ``blocks``, ``children``) and ``group`` (a
parent). ``blocked_by``, ``after`` and ``depends_on`` are precedence unless said otherwise; ``parent`` is a group.

Never enforced: no transition is refused for a relation. They are read: the item index keeps every item's links
both ways (``itemindex.py``), and ``precedence.py`` derives each item's status, the critical path and the
schedule from them."""

from __future__ import annotations

import re

from .ir import Relation

PRECEDENCE = ("blocked_by", "after", "depends_on")          # precedence unless declared otherwise
INVERSES = {"blocked_by": "blocks", "after": "before", "depends_on": "dependents", "parent": "children",
            "duplicates": "duplicated_by", "relates_to": "related_from"}
GROUPS = ("parent",)
REL_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
REL_KEYS = {"kind", "precedence", "inverse", "group", "starts_at", "description"}
REL_FOLDS = ("relation", "union", "replace")                # how a relation's field may fold: a set of ids


def inverse_of(name: str) -> str:
    return INVERSES.get(name, f"{name}_of")


def compile_relations(c, m, what: str, rules: dict) -> dict[str, Relation]:
    """A kind's ``relations:``, each ``name: KIND``, ``name: [KIND, ...]`` or ``name: {kind:, precedence:, inverse:,
    group:}``; its field folds by ``relation`` unless ``fold:`` says ``union`` or ``replace``."""
    raw = m.get("relations")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        c.err(f"{what}.relations: a map of relation: the kind it names (blocked_by: ticket)", m.at("relations"), "not-a-map")
        return {}
    out: dict[str, Relation] = {}
    for name, v in raw.items():
        at = raw.at(name)
        if not isinstance(name, str) or not REL_NAME.match(name):
            c.err(f"{what}.relations: {name!r} is not a relation's name (a field name: lowercase letters, digits, _ "
                  f"and -: blocked_by)", at, "bad-relation")
            continue
        opts = v if isinstance(v, dict) else {"kind": v}
        if isinstance(v, dict):
            c.keys(v, REL_KEYS, f"{what}.relations.{name}")
        kinds = opts.get("kind")
        kinds = [kinds] if isinstance(kinds, str) else kinds
        if not isinstance(kinds, list) or not kinds or not all(isinstance(k, str) and k for k in kinds):
            c.err(f"{what}.relations.{name}: the kind of item it names, or a list of kinds (blocked_by: ticket)", at,
                  "bad-relation")
            continue
        prec, group = opts.get("precedence", name in PRECEDENCE), opts.get("group", name in GROUPS)
        if not isinstance(prec, bool) or not isinstance(group, bool):
            c.err(f"{what}.relations.{name}: precedence: and group: are true or false", at, "bad-relation")
            continue
        far = [remote_of(c.doc.remotes, c.doc.sections.get("items") or {}, str(k)) for k in kinds]
        remote, there = next((x for x in far if x[0]), ("", ""))
        if remote:                                  # a remote's kind: read beside ours, never gating (SPEC §5a)
            if len(kinds) > 1:
                c.err(f"{what}.relations.{name}: a relation naming a remote's kind names only that kind", at,
                      "bad-relation")
                continue
            if opts.get("precedence") is True:
                c.err(f"{what}.relations.{name}: precedence: ergostat does not see when a remote's item is finished; "
                      f"it cannot gate on it", at, "remote-relation-precedence")
                continue
            if opts.get("group") is True:
                c.err(f"{what}.relations.{name}: group: a remote's items are not grouped here", at, "bad-relation")
                continue
            prec = group = False
        inv = opts.get("inverse") or inverse_of(name)
        if not isinstance(inv, str) or not REL_NAME.match(inv) or inv == name:
            c.err(f"{what}.relations.{name}.inverse: the other direction's name, a field name unlike its own (blocks)",
                  at, "bad-relation")
            continue
        starts = opts.get("starts_at", [])
        starts = [starts] if isinstance(starts, str) else starts
        if not isinstance(starts, list) or not all(isinstance(s, str) and s for s in starts):
            c.err(f"{what}.relations.{name}.starts_at: a list of the target kind's states ([approved])", at,
                  "bad-relation")
            continue
        if starts and not prec:
            c.err(f"{what}.relations.{name}.starts_at: only a precedence relation's targets block, so only it may say "
                  f"where they stop blocking", at, "starts-at-not-precedence")
            continue
        rule = rules.get(name)
        if rule is None:
            rules[name] = "relation"
        elif rule not in REL_FOLDS:
            c.err(f"{what}.fold.{name}: a relation folds as a set of ids ({', '.join(REL_FOLDS)}), not {rule}", at,
                  "bad-fold")
        out[name] = Relation(name, [str(k) for k in kinds], prec, inv, group, remote, there, list(starts))
    return out


def remote_of(remotes, local, kind: str) -> tuple[str, str]:
    """(remote, its kind's name there) when ``kind`` is a remote's (``incidents-incident``): not a local kind (local
    first), and named ``R-K`` for a remote ``R`` (the longest that fits); else ("", "")."""
    if kind in local:
        return "", ""
    fits = [r for r in remotes or {} if kind.startswith(f"{r}-") and len(kind) > len(r) + 1]
    r = max(fits, key=len, default="")
    return (r, kind[len(r) + 1:]) if r else ("", "")


def check_relations(c, spec) -> None:
    """Once every kind is known: each relation names kinds of the model, or a kind its remote serves (as last read;
    one it no longer serves, or a remote never read, is a finding: the model still compiles)."""
    from .load import Problem
    for k in spec.items.values():
        for r in k.relations.values():
            if r.remote:
                info = spec.remotes.get(r.remote) or {}
                if r.there not in (info.get("kinds") or {}):
                    ver = info.get("version")
                    c.problems.append(Problem(
                        "finding", f"item kind {k.name}.relations.{r.name}: item kind {r.kinds[0]} is not in remote "
                        f"{r.remote}'s model" + (f" (version {ver}): it has no item kind {r.there}" if ver else
                                                 " (it has not been read)") + "; no line is drawn to it",
                        k.where, "remote-reference-unresolved", f"item.{k.name}"))
                continue
            for t in r.kinds:
                if t not in spec.items:
                    c.err(f"item kind {k.name}.relations.{r.name}: {t!r} is not a kind of item" + c.suggest(t, spec.items),
                          k.where, "unknown-ref")
            check_starts_at(c, spec, k, r)


def check_starts_at(c, spec, k, r) -> None:
    """Each ``starts_at`` state is a state of a kind the relation names, and not one it counts as finished or paused
    (``messages: done:``, else its last state; ``messages: paused:``): a finished target blocks nothing already."""
    targets = [spec.items[t] for t in r.kinds if t in spec.items]
    msgs = getattr(spec, "messages", None)
    done, paused = (getattr(msgs, "done", None) or {}), (getattr(msgs, "paused", None) or {})
    for s in r.starts_at:
        has = [t for t in targets if s in (t.states or [])]
        where = f"item kind {k.name}.relations.{r.name}.starts_at: {s!r}"
        if not has:
            c.err(f"{where} is not a state of {', '.join(r.kinds)}" + c.suggest(s, [x for t in targets for x in t.states or []]),
                  k.where, "starts-at-unknown-state")
        elif any(s in (done.get(t.name) or t.states[-1:]) or s in (paused.get(t.name) or ()) for t in has):
            c.err(f"{where} is a finished or paused state: a finished target never blocks, and a paused one is not "
                  f"under way", k.where, "starts-at-finished")


def ids_in(v) -> list[str]:
    """The ids a relation's field holds, however it was folded (one id, a list; anything else is not an id)."""
    if isinstance(v, str):
        return [v] if v else []
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str) and x]
    return []


def links_of(kind, fields: dict) -> list[tuple[str, str]]:
    """(relation, target id) for each link an item's fields hold, by its kind's relations."""
    if kind is None or not kind.relations:
        return []
    return [(r, t) for r in kind.relations for t in ids_in(fields.get(r))]


def any_relations(spec) -> bool:
    return any(k.relations for k in (getattr(spec, "items", None) or {}).values())


def precedence_names(spec) -> dict[str, set[str]]:
    """Kind → its precedence relations."""
    return {n: {r.name for r in k.relations.values() if r.precedence}
            for n, k in (getattr(spec, "items", None) or {}).items() if k.relations}
