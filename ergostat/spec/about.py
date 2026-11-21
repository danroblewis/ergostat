"""Items about parts of the model (SPEC §5a, *About*): a kind that declares ``about: FIELD`` names, in that field of
each of its items, the parts of the model the item bears on (``goal.x``, ``stock.y``, ``flow.z``, ``auxiliary.w``,
``block.v``: the text form a claim's ``about`` uses). The item index keeps each item→part link (``itemindex.ABOUT``),
so the open items about a part are one lookup: ``explain`` ends with them (at most 5), a ``check`` finding about a
part carries their ids, and an off loop in ``ergostat status`` names them (at most 3). A name that is not a part of
the model is a finding (``about-missing-part``). A model none of whose kinds declares ``about:`` looks nothing up."""

from __future__ import annotations

from .load import Problem

KINDS = {"goal": "goals", "stock": "stocks", "flow": "flows", "auxiliary": "auxiliaries", "block": "blocks"}
EXPLAIN_MOST, STATUS_MOST = 5, 3


class Unknown(Exception):
    """The item index could not be read: which items are about a part is not known (never "none")."""


def parts_named(v) -> list[str]:
    """The names an ``about`` field holds: one, or a list. Anything else that is not empty is kept as its text, so a
    malformed name is a finding, never dropped."""
    vs = v if isinstance(v, list) else [] if v is None else [v]
    return list(dict.fromkeys(x if isinstance(x, str) else str(x) for x in vs if x is not None and x != ""))


def is_part(spec, name: str) -> bool:
    kind, _, rest = name.partition(".")
    return kind in KINDS and rest in (getattr(spec, KINDS[kind], None) or {})


def declared(spec) -> bool:
    return any(getattr(k, "about", None) for k in (getattr(spec, "items", None) or {}).values())


def _label(it, k) -> str:
    """An item's title, else its first field with a value (those its kind shows first)."""
    f, skip = it.fields, getattr(k, "about", None)
    v = f.get("title")
    if v in (None, "", []):
        v = next((f[x] for x in [*(k.show if k else []), *f] if x in f and x != skip and f[x] not in (None, "", [])), "")
    s = " ".join(str(v).split())
    return s if len(s) <= 60 else s[:57].rsplit(" ", 1)[0] + "..."


def open_about(events, spec, parts=None) -> dict[str, list[tuple[str, str, float]]]:
    """Per part named (of ``parts``; None: every name any item holds), the open (not finished) items about it, the
    latest first: (id, title or first field, its last event's time). Reads the link rows and those items' rows only.
    Empty, and nothing looked up, when no kind declares ``about:``. Raises ``Unknown`` when the index cannot be read."""
    if not declared(spec):
        return {}
    from .itemindex import done_states, index_for
    try:
        ix = index_for(events, spec, False)
        if ix is None:
            raise Unknown("the record is kept nowhere on disk, so it has no item index")
        with ix.lock:
            links = ix.about(None if parts is None else list(parts))
            done = getattr(getattr(spec, "messages", None), "done", None)
            shown = {}
            for it in ix.items(ids={i for i, _ in links}, moves=False):     # the latest first
                k = spec.items.get(it.kind) if it.kind else None
                if k is None or not k.states or it.state not in done_states(k, ix.left(k.name), done):
                    shown[it.id] = (it.id, _label(it, k), it.last)
    except Unknown:
        raise
    except Exception as e:                    # (a file healing could not build again, a record that cannot be read)
        raise Unknown(f"{type(e).__name__}: {e}") from e
    rank = {i: n for n, i in enumerate(shown)}
    out: dict[str, list[tuple[str, str, float]]] = {}
    for i, p in sorted(links, key=lambda x: rank.get(x[0], 0)):
        if i in shown:
            out.setdefault(p, []).append(shown[i])
    return out


def short(ids: list[str], most: int = STATUS_MOST) -> str:
    """``a, b, c +2``: at most ``most`` ids, and how many more."""
    return ", ".join(ids[:most]) + (f" +{len(ids) - most}" if len(ids) > most else "")


def explain_line(events, spec, part: str) -> str:
    """``explain``'s last line for a part: its open items (at most 5, "and N more"); "" when no kind declares
    ``about:``."""
    if not declared(spec):
        return ""
    head = f"Open items about {part}"
    try:
        got = open_about(events, spec, [part]).get(part, [])
    except Unknown as e:
        return f"{head}: unknown, the item index could not be read ({e})."
    if not got:
        return f"{head}: none."
    listed = ", ".join(f"{i} ({t})" if t else i for i, t, _ in got[:EXPLAIN_MOST])
    return f"{head}: {listed}" + (f", and {len(got) - EXPLAIN_MOST} more" if len(got) > EXPLAIN_MOST else "") + "."


def findings(spec, out: list) -> None:
    """``check``: each finding about a part with open items about it carries their ids (``items``, and said in its
    message); each name an open item holds that is not a part of the model is ``about-missing-part``; an index that
    cannot be read is ``about-unknown`` (and nothing is said to be missing or not)."""
    if not declared(spec):
        return
    from .chains import record_dir
    d = record_dir(spec)
    if d is None:
        return                                  # no record yet: no items
    try:
        from ..storage import Storage, open_events
        named = open_about(open_events(getattr(spec, "storage", None) or Storage(), d), spec)
    except Exception as e:
        out.append(Problem("finding", f"the items about parts of the model could not be read ({e}): which parts they "
                           f"name, whether each is in the model, and which findings they bear on are unknown", None,
                           "about-unknown", "model"))
        return
    for f in out:
        ids = [i for i, *_ in named.get(f.about, [])]
        if ids and not f.items:
            f.items = ids
            f.message += f" (open items about it: {short(ids, EXPLAIN_MOST)})"
    for part in sorted(p for p in named if not is_part(spec, p)):
        ids = [i for i, *_ in named[part]]
        out.append(Problem("finding", f"{part}: {len(ids)} open item{'s' if len(ids) > 1 else ''} about it "
                           f"({short(ids, EXPLAIN_MOST)}), but it is not a part of the model: name a goal, stock, flow, "
                           f"auxiliary or block (goal.x)", None, "about-missing-part", part, ids))
