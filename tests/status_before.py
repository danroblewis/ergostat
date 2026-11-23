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


def stored(p, fam: str, since=None, until=None) -> dict:
    """``projections.stored`` as the modules read it before."""
    if fam == "action":
        return actions(p, since, until)
    if fam == "message":
        return messages(p, since, until, n=2000)        # (the status's unrouted messages read the latest 2,000 events)
    if fam == "report":
        return reports(p, until)
    return {"change": changes, "request": requests, "model-request": requests_now}[fam](p)


def query(p, type: str, **kw) -> list[dict]:
    return p.events.query(type=type, **kw)


def old(monkeypatch) -> None:
    """The old reads in place of the tables', for the rest of the test (or the ``monkeypatch.context()``)."""
    from ergostat.spec import projections
    monkeypatch.setattr(projections, "stored", stored)
    monkeypatch.setattr(projections, "query", query)
    monkeypatch.setattr(projections, "asks", asks)
