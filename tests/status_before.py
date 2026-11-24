"""The status's reads of the record as they were before they read the item index's tables (status-reads-the-projections),
kept as the tests' oracle: each folds the record itself, as ``actions.record.stored``, ``messages.record.stored``,
``reports.record.stored``, ``numbers.proposals.changes``, ``numbers.requests.stored``, ``inbox.interventions
.requests_now`` and ``inbox.entries.asks`` did; ``query`` is ``events.query``. ``old(monkeypatch)`` puts them back in
place of ``projections.stored``, ``query`` and ``asks``, so a whole status answer can be made by the old code."""

from __future__ import annotations

from ergostat.reports.kind import REPORT, report_kind
from ergostat.spec import items as its
from ergostat.spec.ir import (
    ACTION,
    MESSAGE,
    MODEL_CHANGE,
    MODEL_REQUEST,
    MODELLING_REQUEST,
    action_kind,
    message_kind,
    model_change_kind,
    model_request_kind,
    modelling_request_kind,
)


def _view(it) -> dict:
    return {**it.fields, "id": it.id, "state": it.state, "time": it.first, "last": it.last, "entered": it.entered,
            "moves": it.moves}


def actions(p, since=None, until=None) -> dict:
    by: dict[str, list[dict]] = {}
    for e in p.events.query(n=None, type=f"{ACTION}.*", until=until):
        by.setdefault(e["item"], []).append(e)
    out = {}
    for item, es in by.items():
        if es[0]["type"] != f"{ACTION}.requested" or (since is not None and es[0]["time"] < since):
            continue
        it = its.fold(item, es, action_kind())
        ignored = [x["type"].rsplit(".", 1)[1] for x in it.refused if x["form"] == "final"]
        out[item] = {**_view(it), **({"ignored": ignored} if ignored else {})}
    return out


def messages(p, since=None, until=None, n=None) -> dict:
    by: dict[str, list[dict]] = {}
    for e in p.events.query(n=n, type=f"{MESSAGE}.*", until=until):
        by.setdefault(e["item"], []).append(e)
    out = {}
    for item, es in by.items():
        if es[0]["type"] != f"{MESSAGE}.received":
            es = p.events.query(n=None, item=item)
        if since is not None and es[0]["time"] < since:
            continue
        out[item] = {**_view(its.fold(item, es, message_kind())), "received_event": es[0]["id"] if es else None}
    return out


def reports(p, until=None) -> dict:
    by: dict[str, list[dict]] = {}
    for e in p.events.query(n=None, type=f"{REPORT}.*", until=until):
        by.setdefault(e["item"], []).append(e)
    return {item: _view(its.fold(item, es, report_kind())) for item, es in by.items()
            if es[0]["type"] == f"{REPORT}.drafted"}


def _by_item(p, type: str) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    for e in p.events.query(n=None, type=type):
        if "/" in str(e.get("item") or ""):
            by.setdefault(e["item"], []).append(e)
    return by


def changes(p) -> dict:
    return {item.split("/", 1)[1]: (lambda it: (it.state, it.fields))(its.fold(item, evs, model_change_kind()))
            for item, evs in _by_item(p, f"{MODEL_CHANGE}.*").items()}


def _moved_at(evs: list[dict], kind) -> int | None:
    at, was = None, None
    for e in evs:
        to = kind.on.get(e["type"])
        if to is not None and (to != was or e["type"].endswith(".reopened")):
            at = e.get("seq")
        was = to if to is not None else was
    return at


def requests(p) -> dict:
    kind, out = modelling_request_kind(), {}
    for item, evs in _by_item(p, f"{MODELLING_REQUEST}.*").items():
        it = its.fold(item, evs, kind)
        short = item.split("/", 1)[1]
        out[short] = {**it.fields, "id": short, "state": it.state, "moved": _moved_at(evs, kind)}
    return out


def requests_now(p) -> dict:
    by: dict[str, list] = {}
    for e in p.events.query(n=None, type=f"{MODEL_REQUEST}.*"):
        by.setdefault(e["item"], []).append(e)
    out = {}
    for item, es in by.items():
        it = its.fold(item, es, model_request_kind())
        out[it.fields.get("class") or item] = {**it.fields, "id": item, "state": it.state, "moves": it.moves}
    return out


def asks(p, block: str, person: bool, since=None, until=None) -> list[dict]:
    out: list[dict] = []
    for e in p.events.query(n=None, item=block, since=since, until=until,
                            type="person.asked,agent.ran" if person else "block.advised,block.approved,block.denied"):
        if e["type"] in ("person.asked", "block.advised"):
            if out and out[-1]["answered"] is None:
                out[-1].update(answered=e["time"], verdict="superseded", by=None)
            out.append({"seq": e["seq"], "time": e["time"], "data": e["data"], "answered": None, "verdict": None})
        elif out and out[-1]["answered"] is None:
            out[-1].update(answered=e["time"], by=e.get("source"), note=(e.get("data") or {}).get("note") or None,
                           verdict="denied" if e["type"] == "block.denied" else "approved")
    return out


def stored(p, fam: str, since=None, until=None, states=None) -> dict:
    """``projections.stored`` as the modules read it before (``states``: as the callers filtered it)."""
    if fam == "action":
        got = actions(p, since, until)
        return got if states is None else {k: a for k, a in got.items() if a["state"] in states}
    if fam == "message":
        return messages(p, since, until, n=2000)        # (the status's unrouted messages read the latest 2,000 events)
    if fam == "report":
        return reports(p, until)
    return {"change": changes, "request": requests, "model-request": requests_now}[fam](p)


def query(p, type: str, **kw) -> list[dict]:
    return p.events.query(type=type, **kw)


def latest(p, type: str, items, until=None) -> dict:
    return {i: next(reversed(p.events.query(n=1, type=type, item=i, until=until)), None) for i in items}


def openings(p, valves, since, until) -> dict:
    return {k: [t for t, _, _ in v] for k, v in p.events.times(valves, "valve.opened", since, until).items()}


def opened_amounts(p, valve, since, until, n=50) -> list:
    return [e["data"].get("amount") for e in p.events.query(n=n, type="valve.opened", item=valve, since=since, until=until)]


def current(events, spec, ids, fields=()) -> dict:
    return {i: it for i in ids if i and (it := its.one(events, spec, i)) is not None}


def old(monkeypatch) -> None:
    """The old reads in place of the tables', for the rest of the test (or the ``monkeypatch.context()``): the
    families, marks and asks; each agent's and loop's newest events, the window's tallies and openings
    (``events.runs``, ``opened``, ``times``); an action's work item folded from the record (``items.one``); and every
    item changed since a moment folded again from the record (no ``Index.still``)."""
    from ergostat.spec import itemindex, projections
    monkeypatch.setattr(projections, "stored", stored)
    monkeypatch.setattr(projections, "query", query)
    monkeypatch.setattr(projections, "asks", asks)
    monkeypatch.setattr(projections, "latest", latest)
    monkeypatch.setattr(projections, "runs", lambda p, items, since, until: {i: p.events.runs(i, since, until)
                                                                             for i in items})
    monkeypatch.setattr(projections, "opened", lambda p, valves, since, until: {v: p.events.opened(v, since, until)
                                                                                 for v in valves})
    monkeypatch.setattr(projections, "openings", openings)
    monkeypatch.setattr(projections, "opened_amounts", opened_amounts)
    monkeypatch.setattr(its, "current", current)
    monkeypatch.setattr(itemindex.Index, "still", lambda self, ids, keys, at: set())
