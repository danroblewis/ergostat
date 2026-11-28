"""The items group's kinds of panel (SPEC §4f): the kinds' overview, every kind's newest, a kind's states, model,
definition and paged list, and each part of one item. Each checks in a model's dashboards:, a wrong parameter is
refused at its line, and /api/dashboard answers each as its own endpoint does."""

import time

import pytest

from ergostat import model as mdl
from ergostat.spec.dashboards import query
from ergostat.store import Project
from ergostat.web import dashboard_api, server
from tests.test_dashboards import MODEL, errors, project

BOARD = """\
  items:
    title: Items, as the pages draw them
    panels:
      - {panel: projections, states: all, size: full, fit: true}
      - {panel: items-by-projection, q: t1, finished: show, per_projection: 10}
      - {panel: projection-now, projection: ticket, points: 30, states: groups}
      - {panel: projection-model, projection: ticket}
      - {panel: projection-definition, projection: ticket}
      - {panel: item-list, projection: ticket, state: doing, q: t, sort: -title, finished: show, n: 10}
      - {panel: item-summary, item: ticket/1}
      - {panel: item-why, item: ticket/4}
      - {panel: item-path, item: ticket/1}
      - {panel: item-relations, item: ticket/1}
      - {panel: item-fields, item: ticket/1}
      - {panel: item-refused, item: ticket/1}
      - {panel: item-moves, item: ticket/1}
      - {panel: item-events, item: ticket/1}
      - {panel: item-changes, item: ticket/1, history: title}
      - {panel: item-state-timeline, item: ticket/1}
      - {panel: item-field-chart, item: ticket/1, field: title}
      - {panel: item-events-histogram, item: ticket/1}
"""
TEXT = MODEL + BOARD


def test_each_kind_checks_and_round_trips(tmp_path):
    from ergostat.spec import read
    from ergostat.spec.dashboards import plain
    from tests.test_dashboards import write
    assert errors(tmp_path, TEXT) == []
    spec, _ = read(write(tmp_path, TEXT) / "ergostat.yaml")
    got = plain(spec.dashboards["items"])["panels"]
    assert [p["panel"] for p in got] == ["projections", "items-by-projection", "projection-now", "projection-model",
                                        "projection-definition", "item-list",
                                        "item-summary", "item-why", "item-path", "item-relations", "item-fields",
                                        "item-refused", "item-moves", "item-events", "item-changes",
                                        "item-state-timeline", "item-field-chart", "item-events-histogram"]
    assert got[5]["sort"] == "-title" and got[5]["n"] == 10 and got[14]["history"] == "title" and got[0]["fit"] is True


@pytest.mark.parametrize("old, new, code, about", [
    ("{panel: projections, states: all, size: full, fit: true}", "{panel: projections, states: every}", "bad-dashboard", ""),
    ("{panel: items-by-projection, q: t1, finished: show, per_projection: 10}", "{panel: items-by-projection, per_projection: 0}", "bad-dashboard", ""),
    ("{panel: items-by-projection, q: t1, finished: show, per_projection: 10}", "{panel: items-by-projection, finished: yes}", "bad-dashboard", ""),
    ("{panel: projection-now, projection: ticket, points: 30, states: groups}", "{panel: projection-now, projection: ticket, states: [all]}",
     "bad-dashboard", ""),
    ("{panel: projection-now, projection: ticket, points: 30, states: groups}", "{panel: projection-now, projection: ticket, points: 1}",
     "bad-dashboard", ""),
    ("{panel: projection-model, projection: ticket}", "{panel: projection-model, projection: tickets}", "unknown-ref", "projections.tickets"),
    ("{panel: projection-definition, projection: ticket}", "{panel: projection-definition}", "bad-dashboard", ""),
    ("{panel: projection-definition, projection: ticket}", "{panel: projection-definition, projection: 3}", "bad-dashboard", ""),
    ("{panel: item-list, projection: ticket, state: doing, q: t, sort: -title, finished: show, n: 10}",
     "{panel: item-list, projection: ticket, state: waiting}", "unknown-ref", "projections.ticket"),
    ("{panel: item-list, projection: ticket, state: doing, q: t, sort: -title, finished: show, n: 10}",
     "{panel: item-list, projection: ticket, state: [open, doing]}", "bad-dashboard", ""),
    ("{panel: item-list, projection: ticket, state: doing, q: t, sort: -title, finished: show, n: 10}",
     "{panel: item-list, projection: ticket, n: 0}", "bad-dashboard", ""),
    ("{panel: item-list, projection: ticket, state: doing, q: t, sort: -title, finished: show, n: 10}",
     "{panel: item-list, projection: epic}", "unknown-ref", "projections.epic"),
    ("{panel: item-list, projection: ticket, state: doing, q: t, sort: -title, finished: show, n: 10}",
     "{panel: item-list, projection: ticket, page: 2}", "unknown-key", ""),
    ("{panel: item-summary, item: ticket/1}", "{panel: item-summary}", "bad-dashboard", ""),
    ("{panel: item-why, item: ticket/4}", "{panel: item-why, item: 4}", "bad-dashboard", ""),
    ("{panel: item-fields, item: ticket/1}", "{panel: item-fields, item: [ticket/1]}", "bad-dashboard", ""),
    ("{panel: item-changes, item: ticket/1, history: title}", "{panel: item-changes, item: ticket/1, history: [title]}",
     "bad-dashboard", ""),
    ("{panel: item-events, item: ticket/1}", "{panel: item-events, item: ticket/1, projection: ticket}", "unknown-key", ""),
    ("{panel: item-state-timeline, item: ticket/1}", "{panel: item-state-timeline}", "bad-dashboard", ""),
    ("{panel: item-field-chart, item: ticket/1, field: title}", "{panel: item-field-chart, item: ticket/1, field: [title]}",
     "bad-dashboard", ""),
    ("{panel: item-events-histogram, item: ticket/1}", "{panel: item-events-histogram, item: ticket/1, n: 0}",
     "unknown-key", ""),
])
def test_a_wrong_parameter_is_refused_at_its_line(tmp_path, old, new, code, about):
    text = TEXT.replace(old, new)
    assert text != TEXT
    got = errors(tmp_path, text)
    line = next(i for i, x in enumerate(text.splitlines(), 1) if new.strip() in x)
    assert [(p.code, p.about, p.where.line if p.where else None) for p in got] == [(code, about, line)], got


def test_an_item_of_any_id_checks_whether_recorded_or_not(tmp_path):
    assert errors(tmp_path, TEXT.replace("item: ticket/4}", "item: not/recorded}")) == []


def test_the_dashboard_answers_each_panel_as_its_own_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)
    project(tmp_path, TEXT)
    p = Project(mdl.load(tmp_path))
    live = server.Live(p)
    got = dashboard_api.answer(live, p, "items", {}, wait=True)
    assert all("answer" in x for x in got["panels"]), [x for x in got["panels"] if "answer" not in x]
    by = {x["panel"]["panel"]: x["answer"] for x in got["panels"]}
    assert "ticket" in {k["name"] for k in by["projections"]["projections"]}
    assert by["projection-model"]["projection"] == by["projection-definition"]["projection"] == "ticket" and by["projection-model"]["counted_in"]
    assert by["projection-now"]["states"] and len(by["projection-now"]["times"]) == 30
    assert [i["id"] for i in by["item-list"]["items"]] and all(i["state"] == "doing" for i in by["item-list"]["items"])
    assert [i["id"] for i in by["items-by-projection"]["items"]] == ["ticket/1"]          # searched: t1 alone
    for k in ("item-summary", "item-path", "item-relations", "item-fields", "item-refused", "item-moves", "item-events",
              "item-state-timeline", "item-events-histogram"):
        assert by[k]["id"] == "ticket/1" and "history" not in by[k], k
    assert by["item-changes"]["id"] == "ticket/1" and set(by["item-changes"]["history"]) == {"title"}
    assert by["item-field-chart"]["id"] == "ticket/1" and "title" in by["item-field-chart"]["history"]   # every field's
    assert by["item-why"]["known"] and not by["item-why"]["done"]                  # ticket/4 is doing, not done
    # each the very answer its endpoint gives, asked on its own of the same moment (why: only as the record is now)
    at = time.time() - 5
    past = dashboard_api.answer(live, p, "items", {"at": [str(at)]}, wait=True)
    for x in past["panels"]:
        decl = x["panel"]
        if decl["panel"] == "item-why":
            assert "never at=" in x["error"]
            continue
        params = {k: v for k, v in decl.items() if k not in ("panel", "title", "size", "note", "fit")}
        path = dashboard_api.PATHS[decl["panel"]]
        for k in [k for k in params if "{" + k + "}" in path]:
            path = path.replace("{" + k + "}", params.pop(k).replace("/", "%2F"))
        alone = server.api(live, path, {"since": [str(past["window"])], "at": [str(at)],
                                        **dashboard_api.FIXED.get(decl["panel"], {}), **query(params)})
        assert alone == x["answer"], decl["panel"]
