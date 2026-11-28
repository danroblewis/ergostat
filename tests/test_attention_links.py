"""Every attention row links to where the thing is (state.attention): an alarm to its block, a daemon and an agent to
its page, an agent's refused lines to them on the Events page, a stock's residual to the stock on the diagram; and a
residual that came and went leaves a record (residual.significant, residual.subsided: invariant 7)."""

from __future__ import annotations

import time

from ergostat import state as st


def _snap(**kw) -> dict:
    return {"loops": {}, "agents": {}, "residuals": {}, **kw}


def _agent(**kw) -> dict:
    return {"failing": False, "refused": 0, "stale": [], "last": None, **kw}


def test_each_row_links_to_where_its_thing_is(tmp_path):
    now = time.time()
    snap = _snap(alarms={"too-many": {"since": now, "watches": "stock.queue", "bound": "above 5"}},
                 daemons={"tail": {"state": "failed", "why": "exited 1"}},
                 agents={"fixer": _agent(failing=True, last={"data": {"note": "exit 2"}}, refused=3, unread=1)},
                 residuals={"queue": {"significant": True, "change": 4.0, "explained": 1.0, "unexplained": 3.0}})
    got = {(a["what"], a["says"][:12]): a for a in st.attention(snap)}
    links = {w: a.get("link") for (w, _), a in got.items()}
    assert links["alarm too-many"] == "/diagram?view=blocks&around=block/too-many"
    assert links["daemon tail"] == "/agents/tail"
    assert links["stock queue"] == "/diagram?around=stock/queue"
    fixer = {a["says"][:12]: a["link"] for (w, _), a in got.items() if w == "agent fixer"}
    assert fixer["its last run"] == "/agents/fixer" and fixer["1 lines look"] == "/agents/fixer"
    assert fixer["3 lines refu"] == "/events?match=agent.refused&item=fixer"
    assert all(a.get("link") or a.get("item") for a in got.values())


def test_a_residual_that_came_and_went_is_recorded_once_each_way(tmp_path, project):
    p = project
    big = {"queue": {"significant": True, "change": 4.0, "explained": 1.0, "unexplained": 3.0, "hours": 1.0}}
    assert st.note_residuals(p, {}, 1.0) == []
    (e,) = st.note_residuals(p, big, 10.0)
    assert e["type"] == "residual.significant" and e["item"] == "stock.queue" and e["data"]["unexplained"] == 3.0
    assert st.note_residuals(p, big, 20.0) == []                         # still significant: nothing new
    quiet = {"queue": {**big["queue"], "significant": False, "unexplained": 0.1}}
    (e,) = st.note_residuals(p, quiet, 30.0)
    assert e["type"] == "residual.subsided" and e["data"]["since"] == 10.0
    assert st.note_residuals(p, quiet, 40.0) == []
    assert [x["type"] for x in p.events.query(n=None, type="residual.*")] == ["residual.significant", "residual.subsided"]


def test_a_held_group_of_unexplained_events_links_to_its_object_not_its_request():
    from ergostat.inbox.entries import _request_link
    assert _request_link({"id": "events-unexplained@events:aws.put", "source": "events", "about": "events:aws.put"}) == \
        "/item/ergostat.unexplained/aws.put"
    assert _request_link({"id": "fit-poor@stock.q", "source": "fit", "about": "stock.q"}) == \
        "/item/ergostat.modelling-request/fit-poor@stock.q"


def test_the_interventions_projection_is_named_for_what_it_holds():
    from ergostat.spec import ir
    assert ir.INTERVENTION_CLASS == "ergostat.intervention-class" and not hasattr(ir, "MODEL_REQUEST")
