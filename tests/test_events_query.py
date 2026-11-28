"""The Events dashboard's query (SPEC §5a, *The Events dashboard's query*): plain words a full-text search, an
expression a filter, the scope words kept, an events panel's ``query:``, and ``unexplained()``: the events no
projection takes, from the tally's postings, dropped once a projection takes them, never by a scan."""

from __future__ import annotations

import textwrap
import time
from pathlib import Path

from ergostat import eventquery as eq
from ergostat import model as mdl
from ergostat.numbers import unexplained as ux
from ergostat.store import Project
from ergostat.web.server import Live, api

MODEL = """\
name: t
projections:
  alert:
    query: key.startswith('alert/')
    fields:
      state:
        values: [new, closed]
    events:
      alert-fired:
        when: type == 'alert.fired'
        '...': data
        state: set('new')
      other:
        when: true
        '...': data
uses:
  modelling:
    use: modelling
    with:
      ai: false
      ignore-events: ['debug.*']
"""

FEED = """\
  feed:
    query: source == 'ec2-feed'
    key: [instance]
    fields:
      instance: text
      state: text
    events:
      changed:
        when: true
        instance: data.detail.instance
        state: data.detail.state
"""


def project(tmp_path: Path, text: str = MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems if x.level == "error"]
    return Project(m)


def again(p: Project) -> Project:
    return Project(mdl.load(Path(p.model.path).parent))


def emit(p: Project, n: int = 4) -> None:
    t = time.time() - 60
    for i in range(n):
        p.events.add("aws.eventbridge", source="ec2-feed", at=t + i,
                     data={"source": "aws.ec2", "detail": {"instance": f"i-{i}", "state": "running" if i % 2 else "stopped"}})
    p.events.add("alert.fired", item="alert/1", source="pager", data={"title": "disk full"}, at=t)   # taken by alert
    p.events.add("debug.tick", source="ec2-feed", data={}, at=t)                                    # ignored by the owner
    p.events.add("agent.ran", item="agent/x", source="ergostat", data={}, at=t)                     # ergostat's own


def events(p, **q):
    return api(Live(p), "events", {k: [str(v)] for k, v in q.items()})


def test_plain_words_are_a_full_text_search_and_an_expression_filters(tmp_path):
    assert eq.as_query("aws") == "has('aws')"
    assert eq.as_query("aws running") == "has('aws') and has('running')"
    assert eq.as_query("source == 'x'") == "source == 'x'"
    assert eq.as_query("unexplained()") == "unexplained()"
    p = project(tmp_path)
    emit(p)
    got = events(p, query="aws")
    assert [e["type"] for e in got["events"]] == ["aws.eventbridge"] * 4 and got["total"] == 4
    assert not got["scanned"]                                            # from the trigram index
    got = events(p, query="aws running")
    assert {e["data"]["detail"]["state"] for e in got["events"]} == {"running"} and got["total"] == 2
    got = events(p, query="source == 'ec2-feed' and data.detail.state == 'running'")
    assert [e["data"]["detail"]["instance"] for e in got["events"]] == ["i-1", "i-3"]   # oldest first, as the record
    assert got["exact"]
    got = events(p, query="disk", item="alert/1")                        # the scope words still apply
    assert [e["item"] for e in got["events"]] == ["alert/1"]
    assert events(p, query="disk", item="alert/2")["events"] == []
    assert events(p, query="aws", n=1)["events"][0]["data"]["detail"]["instance"] == "i-3"   # the newest n


def test_runs_are_left_out_unless_asked_and_a_bad_query_is_said(tmp_path):
    p = project(tmp_path)
    emit(p)
    assert events(p, query="has('agent')")["events"] == []
    assert [e["type"] for e in events(p, query="has('agent')", runs=1)["events"]] == ["agent.ran"]
    import pytest
    with pytest.raises(eq.QueryError):
        events(p, query="data.(")


def test_an_events_panel_keeps_a_query(tmp_path):
    text = MODEL + textwrap.dedent("""\
        dashboards:
          feed:
            panels:
              - {panel: events, query: "source == 'ec2-feed' and unexplained()"}
          bad:
            panels:
              - {panel: events, query: "data.("}
        """)
    (tmp_path / "ergostat.yaml").write_text(text)
    from ergostat import spec
    _, problems = spec.read(tmp_path / "ergostat.yaml", extremes=False)
    errs = [str(x) for x in problems if x.level == "error"]
    assert len(errs) == 1 and "bad.panels[0].query" in errs[0] and "does not parse" in errs[0], errs


def test_unexplained_lists_what_no_projection_takes_and_drops_it_once_one_does(tmp_path):
    p = project(tmp_path)
    emit(p)
    got = events(p, query="unexplained()")
    assert got["events"] == [] and "modelling's events loop" in got["unexplained"]     # nothing indexed it yet
    ux.update(p)                                                          # the tally (the events loop's sensor)
    got = events(p, query="unexplained()")
    assert [e["type"] for e in got["events"]] == ["aws.eventbridge"] * 4 and "unexplained" not in got
    assert got["total"] == 4 and got["rechecked"] == 5 and got["dropped"] == 1    # debug.tick: the owner ignores it
    assert [e["data"]["detail"]["instance"] for e in events(p, query="unexplained() and has('running')")["events"]] == ["i-1", "i-3"]
    # a projection that takes them now: they drop out, and their postings with them
    p.model.path.write_text(p.model.path.read_text().replace("projections:\n", "projections:\n" + FEED, 1))
    p = again(p)
    got = events(p, query="unexplained()")
    assert got["events"] == [] and got["dropped"] == 5 and got["total"] == 0
    (left,) = eq.index_for(p.events).unexplained()                        # the taken ones' postings gone, the ignored kept
    assert eq.index_for(p.events).events_of([left])[0]["type"] == "debug.tick"


def test_unexplained_reads_only_its_candidates(tmp_path):
    p = project(tmp_path)
    t = time.time() - 3600
    for i in range(3000):                                                 # taken by alert: never candidates
        p.events.add("alert.fired", item=f"alert/{i}", source="pager", data={"title": "x"}, at=t + i * 0.1)
    p.events.add("odd.thing", source="elsewhere", data={"why": "nobody"}, at=t + 400)
    ux.update(p)
    read = []
    real = eq.Index.events_of

    def counted(self, seqs):
        read.append(len(seqs))
        return real(self, seqs)
    eq.Index.events_of = counted
    try:
        got = events(p, query="unexplained()")
    finally:
        eq.Index.events_of = real
    assert [e["type"] for e in got["events"]] == ["odd.thing"]
    assert sum(read) == 1 and got["walked"] == 1                          # the one candidate, no other event read


def test_the_tally_indexes_only_the_new_events(tmp_path):
    p = project(tmp_path)
    emit(p)
    ux.update(p)
    ix = eq.index_for(p.events)
    assert len(ix.unexplained()) == 5 and ix.unexplained_indexed() == p.events.last_seq()
    emit(p, 2)
    ux.update(p)
    assert len(ix.unexplained()) == 8
