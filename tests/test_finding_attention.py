"""A kind's ``attention: FIELD`` (SPEC §5a): the words of that field on its latest item that has them are shown on the
page's attention list, so a finding stored on an item is said where it is seen (the pipeline manager's, in the
factory's ergostat.yaml: dev/records/safe-stalls-heal-themselves.md)."""

import textwrap
import time

from ergostat import model as mdl
from ergostat import state as st
from ergostat.spec import read
from ergostat.store import Project

KIND = """
name: f
projections:
  situation:
    match:
      key: situation/*
    states: [raised, handled]
    events:
      situation.raised:
        state: set('raised')
      situation.handled:
        state: set('handled')
    otherwise: rest
    attention: finding
"""


def project(tmp_path, text: str = KIND) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


def said(p) -> list[dict]:
    return [a for a in st.attention(st.snapshot(p), False, p.model) if a["what"].startswith("item situation/")]


def test_the_latest_finding_is_on_the_attention_list(tmp_path):
    p = project(tmp_path)
    assert said(p) == [], "no finding yet: nothing said"
    t = time.time()
    p.events.add("situation.handled", item="situation/1", source="t", at=t - 60, data={"finding": "the queue is held"})
    p.events.add("situation.raised", item="situation/3", source="t", at=t - 30)          # no finding: not said
    (a,) = said(p)
    assert a["item"] == "situation/1" and a["says"] == "the queue is held" and a["level"] == "warn"
    p.events.add("situation.handled", item="situation/2", source="t", at=t - 10,
                 data={"finding": "a lease is held by a run whose process died"})
    p.events.add("situation.handled", item="situation/4", source="t", at=t - 5, data={"finding": "  "})   # blank
    (a,) = said(p)
    assert a["item"] == "situation/2" and "process died" in a["says"], "only the latest, re-read as the record grows"


def test_a_kind_without_it_says_nothing_and_a_bad_one_is_refused(tmp_path):
    p = project(tmp_path, KIND.replace("    attention: finding\n", ""))
    p.events.add("situation.handled", item="situation/1", source="t", data={"finding": "x"})
    assert said(p) == []
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "ergostat.yaml").write_text(textwrap.dedent(KIND.replace("attention: finding", "attention: [a]")))
    _, problems = read(tmp_path / "bad" / "ergostat.yaml")
    assert [x for x in problems if x.code == "bad-attention" and x.level == "error"], [str(x) for x in problems]


def test_the_factory_shows_its_pipeline_managers_finding():
    from pathlib import Path
    spec, problems = read(Path(__file__).resolve().parent.parent / "ergostat.yaml")
    assert spec.items["situation"].attention == "finding"
    text = (Path(__file__).resolve().parent.parent / "dev" / "bin" / "manager.py").read_text()
    assert 'finding=a["summary"]' in text, "the manager's handled situation carries its finding"
