"""The intent judge (SPEC §12i): work that says it is done, its tests passed, is held to what the owner meant (its
done-when, the confirmed decisions and corrections in its scope, the owner's messages about it) before it counts as
done. The case it exists for first: a change that passes its tests and contradicts a confirmed decision is caught,
with the line that does it as evidence; the same change without the decision is not. Synthetic decisions only."""

import json
import re
import subprocess
import sys
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.decisions import acts
from ergostat.decisions.kinds import CORRECTION, DECISION
from ergostat.intent import ai, brief, judge, measures, outcomes, record, standin
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

PY = sys.executable
BASE = '''"""shrinks pictures for customers' pages."""


def prepare(image, settings):
    return image.convert("RGB")


def choose(image, settings):
    return image, "JPEG", {"quality": 80}
'''
WEBP = '''

_choose_before = choose
def choose(image, settings):
    image, fmt, options = _choose_before(image, settings)
    return image, "WEBP", {"quality": options["quality"], "method": 4}
'''
OPTIMIZE = '''

_choose_before = choose
def choose(image, settings):
    image, fmt, options = _choose_before(image, settings)
    return image, fmt, {**options, "optimize": True}
'''
SHRINK = '''

_prepare_before = prepare
def prepare(image, settings):
    if max(image.size) > 1200:
        image = image.resize((1200, 900))
    return _prepare_before(image, settings)
'''

MODEL = """
name: t
projections:
  change:
    query: key.startswith('change/')
    fields:
      state:
        type: one of [proposed, building, review, merged, dropped]
    events:
      change-started:
        when: type == 'change.started'
        '...': data
        state: set('building')
      change-review:
        when: type == 'change.review'
        '...': data
        state: set('review')
      change-merged:
        when: type == 'change.merged'
        '...': data
        state: set('merged')
      change-dropped:
        when: type == 'change.dropped'
        '...': data
        state: set('dropped')
      other:
        when: true
        '...': data
    show: [title]
stocks:
  todo:
    sensor: {manual: true}
flows:
  done:
    from: todo
blocks:
  intent:
    type: judge
    judge: intent
    every: 1h
    projections:
      change:
        at: review
        accepted: [merged]
        scope: [images, formats]
        work: [code]
        repo: repo
        reopen-to: proposed
"""


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=True).stdout


def project(tmp_path, extra: str = "", model: str = MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(model) + textwrap.dedent(extra))
    m = mdl.load(tmp_path)
    errors = [x for x in m.problems if x.level == "error"]
    assert not errors, errors
    repo = tmp_path / "repo"
    if not repo.exists():
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "squeeze.py").write_text(BASE)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
    return Project(m)


def branch(p, name: str, code: str) -> None:
    repo = p.model.spec.root / "repo"
    git(repo, "checkout", "-q", "-b", name, "main")
    (repo / "squeeze.py").write_text(BASE + code)
    git(repo, "commit", "-qam", name)
    git(repo, "checkout", "-q", "main")


def decide(p, text: str, rejected=(), scope=("formats",)) -> str:
    got = acts.propose(p, DECISION, {"decision": text, "scope": list(scope),
                                     "alternatives": [{"option": o, "why": w} for o, w in rejected]}, "owner")
    acts.confirm(p, DECISION, got["item"])
    return got["item"]


def correct(p, text: str, kind_of_work=("code",), corrects: str | None = None, confirm: bool = True) -> str:
    got = acts.propose(p, CORRECTION, {"correction": text, "kind_of_work": list(kind_of_work),
                                       **({"corrects": corrects} if corrects else {})}, "owner")
    if confirm:
        acts.confirm(p, CORRECTION, got["item"])
    return got["item"]


def submit(p, n: int, code: str, title: str = "a change", **more) -> str:
    cid = f"change/{n}"
    branch(p, f"change-{n}", code)
    p.events.add("change.proposed", item=cid, source="dev", data={"title": title, **more})
    p.events.add("change.started", item=cid, source="dev", data={"branch": f"change-{n}"})
    p.events.add("change.review", item=cid, source="dev", data={"note": "tests pass"})
    return cid


def one_pass(p, **kw) -> dict:
    return judge.run(p, p.model.spec, "intent", **kw)


def verdict(p, **kw) -> dict:
    """One pass, and the first verdict it gave, as recorded."""
    vid = one_pass(p, **kw)["verdicts"][0]["id"]
    return record.stored(p)[vid]


def test_work_that_passes_its_tests_and_contradicts_a_confirmed_decision_is_caught(tmp_path):
    p = project(tmp_path)
    did = decide(p, "squeeze serves JPEG and PNG only", [("WebP", "some customers' mail clients cannot show it")])
    cid = submit(p, 1, WEBP, "store photos as WebP")
    got = one_pass(p)
    assert got["judged"] == 1 and got["held"] == 1
    v = record.stored(p)[got["verdicts"][0]["id"]]
    assert v["state"] == "contradicted" and v["work"] == cid
    assert v["against"] == [did]
    ev = v["evidence"][0]
    assert ev["against"] == did and "WEBP" in ev["quote"] and ev["at"].startswith("squeeze.py:")
    # beside its tests, on the work itself
    it = its.one(p.events, p.model.spec, cid)
    assert it.fields["intent"]["verdict"] == "contradicted" and it.fields["intent"]["id"] == v["id"]
    assert it.state == "review", "held for the owner's attention: the default policy does not move the work"
    # the same moment is judged once
    assert one_pass(p)["judged"] == 0


def test_the_same_change_with_nothing_decided_is_not_held(tmp_path):
    p = project(tmp_path)
    submit(p, 1, WEBP)
    got = one_pass(p)
    v = record.stored(p)[got["verdicts"][0]["id"]]
    assert v["state"] == "unjudged" and "nothing to hold it to" in v["why"]


def test_honest_work_under_the_same_decisions_is_met(tmp_path):
    p = project(tmp_path)
    decide(p, "squeeze serves JPEG and PNG only", [("WebP", "clients cannot show it")])
    correct(p, "Never resize an image a customer sent: their page decides its size")
    submit(p, 1, OPTIMIZE, "optimise JPEG tables")
    v = verdict(p)
    assert v["state"] == "met", v
    assert len(v["against"]) == 2


def test_a_confirmed_correction_for_this_kind_of_work_is_held_to(tmp_path):
    p = project(tmp_path)
    cor = correct(p, "Never resize an image a customer sent: their page decides its size")
    correct(p, "Docs never use the word resize", kind_of_work=("docs",))          # another kind of work: not held to
    submit(p, 1, SHRINK)
    v = verdict(p)
    assert v["state"] == "contradicted" and v["against"] == [cor]
    assert "resize" in v["evidence"][0]["quote"]


def test_only_what_the_owner_confirmed_holds(tmp_path):
    p = project(tmp_path)
    acts.propose(p, DECISION, {"decision": "squeeze serves JPEG and PNG only", "scope": ["formats"],
                               "alternatives": [{"option": "WebP"}], "words": [{"text": "JPEG and PNG only"}]},
                  "extractor")
    submit(p, 1, WEBP)
    assert verdict(p)["state"] == "unjudged"


def test_a_decision_out_of_scope_is_not_held_to(tmp_path):
    p = project(tmp_path)
    decide(p, "the billing service serves JSON only", [("WebP", "?")], scope=("billing",))
    submit(p, 1, WEBP)
    assert verdict(p)["state"] == "unjudged"


def test_what_was_there_before_is_not_the_work_bringing_it_in(tmp_path):
    """A word the owner ruled out that the file already had is not this work's doing."""
    p = project(tmp_path)
    decide(p, "never ship code that mentions customers", scope=("images",))      # the base file's docstring does
    submit(p, 1, OPTIMIZE)
    assert verdict(p)["state"] == "met"


def test_the_owners_message_about_the_work_is_held_to(tmp_path):
    from ergostat.messages import record as mrec
    p = project(tmp_path)
    cid = submit(p, 1, SHRINK)
    mrec.received(p, "on change/1: do not resize anything, the pages scale images themselves", about=[cid])
    v = verdict(p)
    assert v["state"] == "contradicted" and v["against"][0].startswith("ergostat.message/")


def test_held_reopen_sends_the_work_back_with_the_verdict_as_its_reason(tmp_path):
    p = project(tmp_path, model=MODEL.replace("    every: 1h\n", "    every: 1h\n    held: reopen\n"))
    decide(p, "squeeze serves JPEG and PNG only", [("WebP", "clients cannot show it")])
    cid = submit(p, 1, WEBP)
    one_pass(p)
    it = its.one(p.events, p.model.spec, cid)
    assert it.state == "proposed"
    r = it.fields["reopened"]
    assert r["from"] == "review" and "webp" in r["reason"].lower() and r["verdict"].startswith("ergostat.verdict/")
    # reopened by the judge, before it was accepted: not the owner finding it, and not counted against the judge
    assert outcomes.signals(p, p.model.spec) == {}


def test_done_when_with_nothing_to_show_is_unmet(tmp_path):
    p = project(tmp_path)
    cid = "change/9"
    p.events.add("change.proposed", item=cid, source="owner", data={"done_when": "the logos keep their transparency"})
    p.events.add("change.review", item=cid, source="dev")
    v = verdict(p)
    assert v["state"] == "unmet" and v["against"] == ["done-when"]


def test_a_follow_up_carries_the_owners_words_as_its_done_when(tmp_path):
    """Work started by the owner's message carries the message verbatim: deliver.finished's follow-up."""
    from ergostat.messages import route
    p = project(tmp_path, extra="messages:\n  finished: follow-up\n  done: {change: [merged, dropped]}\n")
    p.events.add("change.proposed", item="change/1", source="dev")
    p.events.add("change.merged", item="change/1", source="dev")
    route.send(p, p.model.spec, "change/1 left the logos black; make them keep their transparency")
    f = its.one(p.events, p.model.spec, "change/1.1")
    assert f is not None and f.fields["done_when"] == "change/1 left the logos black; make them keep their transparency"


def test_the_measures_tests_alone_against_the_judge(tmp_path):
    """Two changes pass their tests. The judge holds the WebP one; the other is merged, and the owner later corrects
    it. Tests alone would have let both through: 2 of 2 not done as meant. Past the judge: 1 of 1 accepted."""
    p = project(tmp_path)
    decide(p, "squeeze serves JPEG and PNG only", [("WebP", "clients cannot show it")])
    submit(p, 1, WEBP)
    c2 = submit(p, 2, OPTIMIZE)
    one_pass(p)
    p.events.add("change.merged", item=c2, source="dev")
    spec = p.model.spec
    assert measures.measure(p, "ergostat.intent.accepted") == 1
    assert measures.measure(p, "ergostat.intent.false-done") == 0
    assert measures.measure(p, "ergostat.intent.false-done-tests") == 0.5
    correct(p, "Optimised tables broke the old viewer: take them out", corrects=f"{c2}: it broke the old viewer")
    assert measures.measure(p, "ergostat.intent.reopened") == 1
    assert measures.measure(p, "ergostat.intent.false-done") == 1.0
    assert measures.measure(p, "ergostat.intent.false-done-tests") == 1.0
    assert measures.measure(p, "ergostat.intent.false-done@change") == 1.0
    assert measures.measure(p, "ergostat.intent.contradicted") == 1
    assert measures.measure(p, "ergostat.intent.met") == 1
    # the judge's own error, marked
    assert judge.sweep_missed(p, spec, "intent") == 1
    assert [v["state"] for v in record.stored(p).values() if v["work"] == c2] == ["missed"]


def test_the_owner_overrules_a_false_alarm_and_it_stops_counting_as_held(tmp_path):
    p = project(tmp_path)
    decide(p, "squeeze serves JPEG and PNG only", [("WebP", "clients cannot show it")])
    cid = submit(p, 1, WEBP)
    vid = one_pass(p)["verdicts"][0]["id"]
    assert measures.measure(p, "ergostat.intent.false-done-tests") == 1.0
    with pytest.raises(record.VerdictError):
        record.overrule(p, vid, "")
    record.overrule(p, vid, "WebP is fine for this one: it is only served to the new app")
    assert record.get(p, vid)["state"] == "overruled"
    assert its.one(p.events, p.model.spec, cid).fields["intent"]["overruled"].startswith("WebP is fine")
    assert measures.measure(p, "ergostat.intent.false-done-tests") == 0.0
    assert measures.measure(p, "ergostat.intent.overruled") == 1


def test_the_owner_reopening_accepted_work_counts_against_it(tmp_path):
    p = project(tmp_path)
    decide(p, "squeeze serves JPEG and PNG only", [("WebP", "clients cannot show it")])
    cid = submit(p, 1, OPTIMIZE)
    one_pass(p)
    p.events.add("change.merged", item=cid, source="dev")
    with pytest.raises(record.VerdictError):
        record.reopen(p, p.model.spec, cid, "")
    record.reopen(p, p.model.spec, cid, "it is not what I asked for")
    it = its.one(p.events, p.model.spec, cid)
    assert it.state == "proposed" and it.fields["reopened"]["by"] == "owner"
    assert measures.measure(p, "ergostat.intent.false-done") == 1.0


def test_the_engine_runs_the_judge_on_its_clock_and_reports_its_ports(tmp_path):
    p = project(tmp_path, model=MODEL.replace("    every: 1h\n", "    every: 1h\n    out: {held: flow.done}\n"))
    decide(p, "squeeze serves JPEG and PNG only", [("WebP", "clients cannot show it")])
    submit(p, 1, WEBP)
    said = []
    e = Engine(p, say=said.append)
    e.judge(p.model.spec.blocks["intent"])
    ran = p.events.query(n=1, type="agent.ran", item="intent")[-1]
    assert ran["data"]["judged"] == 1 and ran["data"]["held"] == 1
    assert ran["data"]["moved"] == {"done": 1}
    assert any("not done as meant" in s for s in said)


@pytest.mark.parametrize("bad,says", [
    ("    projections: {nothing: {at: review}}\n", "a projection of the model's own"),
    ("    projections: {change: {at: shipped}}\n", "'shipped' is not a state of change"),
    ("    projections: {change: {at: review}}\n    held: ignore\n", "held: attention"),
])
def test_a_judge_written_wrong_is_refused(tmp_path, bad, says):
    model = MODEL.split("    projections:")[0] + bad
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(model))
    with pytest.raises(mdl.ModelError, match=re.escape(says)):
        mdl.load(tmp_path)


def test_a_model_judge_does_not_take_an_intent_judges_keys(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: t\nblocks:\n  j:\n    type: judge\n    model: haiku\n")
    with pytest.raises(mdl.ModelError, match="only an intent judge"):
        mdl.load(tmp_path)


def test_the_rung_of_the_judge(tmp_path):
    p = project(tmp_path)
    assert p.model.spec.blocks["intent"].builtin_rung == "program"
    p2 = project(tmp_path, model=MODEL.replace("    every: 1h\n", "    every: 1h\n    model: haiku\n"))
    assert p2.model.spec.blocks["intent"].builtin_rung == "narrow-ai"
    assert p2.model.agents["intent"].kind == "narrow-ai"


# ---- the AI judge, with a stand-in for the model (no tokens)

def fake_ai(tmp_path, monkeypatch, answer: dict) -> None:
    f = tmp_path / "fake_ai.py"
    out = {"result": json.dumps(answer), "total_cost_usd": 0.0012, "usage": {"input_tokens": 900, "output_tokens": 60}}
    f.write_text(f"import sys, json\nsys.stdin.read()\nprint(json.dumps({out!r}))\n")   # as claude -p --output-format json
    monkeypatch.setenv("ERGOSTAT_AI", f"{PY} {f}")


def test_the_ai_judges_verdict_is_taken_when_its_evidence_is_in_the_work(tmp_path, monkeypatch):
    p = project(tmp_path)
    did = decide(p, "squeeze serves JPEG and PNG only", [("WebP", "clients cannot show it")])
    submit(p, 1, WEBP)
    fake_ai(tmp_path, monkeypatch, {"verdict": "contradicted", "why": "it serves WebP",
                                    "evidence": [{"against": did, "says": "WebP",
                                                  "quote": 'return image, "WEBP", {"quality": options["quality"], "method": 4}'}]})
    v = verdict(p, model="haiku")
    assert v["state"] == "contradicted" and v["mode"] == "ai" and v["model"] == "haiku" and v["rung"] == "narrow-ai"
    assert v["cost_usd"] == 0.0012 and v["tokens_in"] == 900
    assert v["evidence"][0]["against"] == did


def test_the_ai_judges_verdict_without_evidence_found_in_the_work_is_unjudged(tmp_path, monkeypatch):
    p = project(tmp_path)
    did = decide(p, "squeeze serves JPEG and PNG only", [("WebP", "clients cannot show it")])
    submit(p, 1, OPTIMIZE)
    fake_ai(tmp_path, monkeypatch, {"verdict": "contradicted", "why": "it serves WebP",
                                    "evidence": [{"against": did, "quote": 'return image, "WEBP"'},
                                                 {"against": "ergostat.decision/made-up", "quote": "optimize"}]})
    v = verdict(p, model="haiku")
    assert v["state"] == "unjudged" and v["why"].startswith("unsupported") and v["dropped_evidence"] == 2


def test_the_ai_judge_reads_the_work_and_what_it_is_held_to(tmp_path):
    p = project(tmp_path)
    did = decide(p, "squeeze serves JPEG and PNG only", [("WebP", "clients cannot show it")])
    cid = submit(p, 1, WEBP, done_when="photos come out smaller")
    it = its.one(p.events, p.model.spec, cid)
    kk = p.model.spec.blocks["intent"].params["intent"].kinds["change"]
    b = brief.build(p, p.model.spec, kk, it, judge.entry(it, kk))
    text = ai.render(b)
    assert did in text and "Rejected: WebP" in text and '+    return image, "WEBP"' in text
    assert "> photos come out smaller" in text


def test_the_stand_ins_terms():
    assert [t for t, _ in standin.ruled_out({"rejected": [{"option": "WebP"}], "text": "x"})] == ["webp"]
    assert [t for t, _ in standin.ruled_out({"text": "Never resize an image a customer sent: their page decides"})][:2] == \
        ["resize", "image"]
    assert "webp" in standin.words_in('return image, "WEBP"')
    assert {"prepare", "before", "shrink"} <= standin.words_in("_prepare_before_shrink = prepare")


def test_the_cli_lists_verdicts_overrules_and_reopens(tmp_path):
    p = project(tmp_path)
    decide(p, "squeeze serves JPEG and PNG only", [("WebP", "clients cannot show it")])
    cid = submit(p, 1, WEBP)

    def cli(*args):
        r = subprocess.run([PY, "-m", "ergostat", "-C", str(tmp_path), *args], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout
    out = cli("intent", "judge")
    assert "contradicted" in out and cid in out
    out = cli("intent")
    assert "FALSE-DONE" in out and "contradicted" in out
    vid = json.loads(cli("intent", "--json"))["latest"][0]["id"]
    assert "WEBP" in cli("intent", vid)
    cli("intent", "overrule", vid, "--reason", "fine for the new app")
    assert record.get(p, vid)["state"] == "overruled"
    cli("intent", "reopen", cid, "--reason", "not what I meant")
    assert its.one(p.events, p.model.spec, cid).state == "proposed"
    assert float(cli("measure", "intent.overruled").strip()) == 1.0
    _ = time
