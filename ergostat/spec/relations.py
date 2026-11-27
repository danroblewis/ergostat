"""Relations between items (SPEC §5a, *Relations*): a projection declares typed relations to other items, each a field
holding the ids it names, folded as a set (the ``relation`` fold rule: ids added, or ``{set, add, remove}``) with
its history like any field's. Across projections: a ticket's ``parent`` is an epic.

```yaml
projections:
  ticket:
    id: ticket/*
    relations:
      blocked_by: ticket                 # a projection (or a list of them); precedence: it comes after them
      parent: epic                       # a group: the Graph view hangs its children off it
      duplicates: {projection: ticket, inverse: duplicated_by}
```

What a relation is, besides its projections: ``precedence`` (its targets come first: the item is ready only once each is
finished), ``inverse`` (the other direction's name, derived by ergostat: ``blocks``, ``children``) and ``group`` (a
parent). ``blocked_by``, ``after`` and ``depends_on`` are precedence unless said otherwise; ``parent`` is a group.

Never enforced: no transition is refused for a relation. They are read: the item index keeps every item's links
both ways (``itemindex.py``), and ``precedence.py`` derives each item's status, the critical path and the
schedule from them."""

from __future__ import annotations

import re

from .ir import DEAD, LEASED, Relation

PRECEDENCE = ("blocked_by", "after", "depends_on")          # precedence unless declared otherwise
INVERSES = {"blocked_by": "blocks", "after": "before", "depends_on": "dependents", "parent": "children",
            "duplicates": "duplicated_by", "relates_to": "related_from"}
GROUPS = ("parent",)
REL_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
REL_KEYS = {"projection", "precedence", "inverse", "group", "starts_at", "done_when", "description"}
REL_FOLDS = ("relation", "union", "replace")                # how a relation's field may fold: a set of ids


def inverse_of(name: str) -> str:
    return INVERSES.get(name, f"{name}_of")


def compile_relations(c, m, what: str, rules: dict) -> dict[str, Relation]:
    """A projection's ``relations:``, each ``name: PROJECTION``, ``name: [PROJECTION, ...]`` or ``name: {projection:, precedence:, inverse:,
    group:}``; its field folds by ``relation`` unless ``fold:`` says ``union`` or ``replace``."""
    raw = m.get("relations")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        c.err(f"{what}.relations: a map of relation: the projection it names (blocked_by: ticket)", m.at("relations"), "not-a-map")
        return {}
    out: dict[str, Relation] = {}
    for name, v in raw.items():
        at = raw.at(name)
        if not isinstance(name, str) or not REL_NAME.match(name):
            c.err(f"{what}.relations: {name!r} is not a relation's name (a field name: lowercase letters, digits, _ "
                  f"and -: blocked_by)", at, "bad-relation")
            continue
        opts = v if isinstance(v, dict) else {"projection": v}
        if isinstance(v, dict):
            c.keys(v, REL_KEYS, f"{what}.relations.{name}")
        kinds = opts.get("projection")
        kinds = [kinds] if isinstance(kinds, str) else kinds
        if not isinstance(kinds, list) or not kinds or not all(isinstance(k, str) and k for k in kinds):
            c.err(f"{what}.relations.{name}: the projection it names, or a list of projections (blocked_by: ticket)", at,
                  "bad-relation")
            continue
        prec, group = opts.get("precedence", name in PRECEDENCE), opts.get("group", name in GROUPS)
        if not isinstance(prec, bool) or not isinstance(group, bool):
            c.err(f"{what}.relations.{name}: precedence: and group: are true or false", at, "bad-relation")
            continue
        far = [remote_of(c.doc.remotes, c.doc.sections.get("projections") or {}, str(k)) for k in kinds]
        remote, there = next((x for x in far if x[0]), ("", ""))
        if remote:                                  # a remote's projection: read beside ours, never gating (SPEC §5a)
            if len(kinds) > 1:
                c.err(f"{what}.relations.{name}: a relation naming a remote's projection names only that projection", at,
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
            c.err(f"{what}.relations.{name}.starts_at: a list of the target projection's states ([approved])", at,
                  "bad-relation")
            continue
        if starts and not prec:
            c.err(f"{what}.relations.{name}.starts_at: only a precedence relation's targets block, so only it may say "
                  f"where they stop blocking", at, "starts-at-not-precedence")
            continue
        done_when = opts.get("done_when", {})
        states = m.get("states") or []
        if "done_when" in opts and (not isinstance(done_when, dict) or not done_when or not group or not all(
                s in states and isinstance(w, dict) and w and all(isinstance(f, str) and _plain(x) for f, x in w.items())
                for s, w in done_when.items())):
            c.err(f"{what}.relations.{name}.done_when: a group's, a map of the item's state to the fields it counts as "
                  f"done work in ({{closed: {{end: done}}}}: each a value, or a list of them)", at, "bad-relation")
            continue
        rule = rules.get(name)
        if rule is None:
            rules[name] = "relation"
        elif rule not in REL_FOLDS:
            c.err(f"{what}.fold.{name}: a relation folds as a set of ids ({', '.join(REL_FOLDS)}), not {rule}", at,
                  "bad-fold")
        out[name] = Relation(name, [str(k) for k in kinds], prec, inv, group, remote, there, list(starts),
                             {s: dict(w) for s, w in done_when.items()})
    return out


def _plain(x) -> bool:
    """A value a field is matched to: a string, number, boolean or null, or a list of them."""
    return all(x is None or isinstance(x, str | int | float | bool) for x in (x if isinstance(x, list) else [x]))


def remote_of(remotes, local, kind: str) -> tuple[str, str]:
    """(remote, its projection's name there) when ``kind`` is a remote's (``incidents-incident``): not a local projection (local
    first), and named ``R-K`` for a remote ``R`` (the longest that fits); else ("", "")."""
    if kind in local:
        return "", ""
    fits = [r for r in remotes or {} if kind.startswith(f"{r}-") and len(kind) > len(r) + 1]
    r = max(fits, key=len, default="")
    return (r, kind[len(r) + 1:]) if r else ("", "")


def check_relations(c, spec) -> None:
    """Once every projection is known: each relation names projections of the model, or one its remote serves (as last read;
    one it no longer serves, or a remote never read, is a finding: the model still compiles)."""
    from .load import Problem
    for k in spec.items.values():
        for r in k.relations.values():
            if r.remote:
                info = spec.remotes.get(r.remote) or {}
                if r.there not in (info.get("projections") or {}):
                    ver = info.get("version")
                    c.problems.append(Problem(
                        "finding", f"projection {k.name}.relations.{r.name}: projection {r.kinds[0]} is not in remote "
                        f"{r.remote}'s model" + (f" (version {ver}): it has no projection {r.there}" if ver else
                                                 " (it has not been read)") + "; no line is drawn to it",
                        k.where, "remote-reference-unresolved", f"projections.{k.name}"))
                continue
            for t in r.kinds:
                if t not in spec.items:
                    c.err(f"projection {k.name}.relations.{r.name}: {t!r} is not a projection" + c.suggest(t, spec.items),
                          k.where, "unknown-ref")
            check_starts_at(c, spec, k, r)


def check_starts_at(c, spec, k, r) -> None:
    """Each ``starts_at`` state is a state of a projection the relation names, and not one it counts as finished or paused
    (``messages: done:``, else its last state other than ``leased`` and ``dead``; ``messages: paused:``; ``dead``): a
    finished target blocks nothing already. ``leased`` is refused: a held target counts by the state it was taken
    from (``precedence.starts``), so name that one."""
    targets = [spec.items[t] for t in r.kinds if t in spec.items]
    msgs = getattr(spec, "messages", None)
    done, paused = (getattr(msgs, "done", None) or {}), (getattr(msgs, "paused", None) or {})
    last = lambda t: [x for x in t.states or [] if x not in (LEASED, DEAD)][-1:]      # noqa: E731
    for s in r.starts_at:
        has = [t for t in targets if s in (t.states or [])]
        where = f"projection {k.name}.relations.{r.name}.starts_at: {s!r}"
        if s == LEASED:
            c.err(f"{where}: a leased target counts by the state it was taken from, so name that state", k.where,
                  "starts-at-leased")
        elif s == DEAD:
            c.err(f"{where}: a dead letter is not under way", k.where, "starts-at-finished")
        elif not has:
            c.err(f"{where} is not a state of {', '.join(r.kinds)}" + c.suggest(s, [x for t in targets for x in t.states or []]),
                  k.where, "starts-at-unknown-state")
        elif any(s in (done.get(t.name) or last(t)) or s in (paused.get(t.name) or ()) for t in has):
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
    """(relation, target id) for each link an item's fields hold, by its projection's relations."""
    if kind is None or not kind.relations:
        return []
    return [(r, t) for r in kind.relations for t in ids_in(fields.get(r))]


def any_relations(spec) -> bool:
    return any(k.relations for k in (getattr(spec, "items", None) or {}).values())


def precedence_names(spec) -> dict[str, set[str]]:
    """Projection → its precedence relations."""
    return {n: {r.name for r in k.relations.values() if r.precedence}
            for n, k in (getattr(spec, "items", None) or {}).items() if k.relations}
