"""A part knows the system it belongs to (SPEC §2a, *A part's system*): a library instance's parts and a remote's
record their system and their name within it; a hand-written part records none, whatever its name; inside its own
system's box a part is drawn by its short name, its full name kept for hover and links; outside, its full name."""

import textwrap
from pathlib import Path

from ergostat import spec as sp
from ergostat.shown import shorten
from ergostat.spec.belongs import Belongs, by_name
from tests.test_remote import served_into, write

ROOT = Path(__file__).resolve().parent.parent

USES = """
name: t
systems:
  work: {}
uses:
  questions:
    use: respond-to
    within: work
    with:
      within: 2h
      answer: ./bin/answer.sh
stocks:
  questions-extra: {system: work}       # hand-written: named like the instance's, but none of its
"""

REMOTE = """
name: m
stocks:
  a-open: {unit: things}
flows:
  a-in: {to: a-open}
"""

LOCAL = """
name: support
remotes:
  m:
    url: http://127.0.0.1:1
stocks:
  m-b-open: {}                           # hand-written, beside remote m: named like its parts, none of them
flows:
  m-b-in: {to: m-b-open, driven-by: [+stock.m-a-open]}
"""


def _read(text, tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    spec, ps = sp.read(tmp_path / "ergostat.yaml", extremes=False)
    assert not [p for p in ps if p.level == "error"], ps
    return spec


def _remote(tmp_path, local=LOCAL):
    write(tmp_path / "support", local)
    served_into(tmp_path / "support", tmp_path, remote="m", text=REMOTE)
    return sp.read(tmp_path / "support" / "ergostat.yaml", extremes=False)


def test_a_library_instances_part_and_a_remotes_part_each_record_their_system_and_short_name(tmp_path):
    spec = _read(USES, tmp_path)
    assert spec.belongs["stock.questions-waiting"] == Belongs("questions", "waiting")
    assert spec.belongs["flow.questions-answered"] == Belongs("questions", "answered")
    assert spec.belongs["goal.questions-on-time"] == Belongs("questions", "on-time")
    assert spec.belongs["block.questions-answer"] == Belongs("questions", "answer")
    assert "stock.questions-extra" not in spec.belongs            # hand-written: no owner, whatever its name says
    assert "item.questions" not in spec.belongs                   # a name given whole by a parameter: taken as given
    assert "system.questions" not in spec.belongs and "system.work" not in spec.belongs
    spec, ps = _remote(tmp_path / "r")
    assert not [p for p in ps if p.level == "error"], ps
    assert spec.belongs["stock.m-a-open"] == Belongs("m", "a-open")
    assert spec.belongs["flow.m-a-in"] == Belongs("m", "a-in")
    assert spec.stocks["m-a-open"].name == "m-a-open"               # its full name as before


def test_a_nested_uses_parts_belong_to_it_and_its_system_to_the_outer_instance(tmp_path):
    from tests.test_templates import PRIVATE
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "nag.yaml").write_text(PRIVATE)
    (tmp_path / "proj").mkdir()
    spec = _read("name: t\nlibrary: ../private\nuses:\n  n:\n    use: nag\n", tmp_path / "proj")
    assert spec.belongs["stock.n-counter"] == Belongs("n", "counter")
    assert spec.belongs["stock.n-inner-level"] == Belongs("n-inner", "level")
    assert spec.belongs["system.n-inner"] == Belongs("n", "inner")
    assert "system.n" not in spec.belongs                                # the owner's own instance: named by the owner


def test_a_hand_written_m_a_open_beside_remote_ms_a_open_keeps_distinct_owners(tmp_path):
    spec, ps = _remote(tmp_path)
    assert spec.belongs["stock.m-a-open"] == Belongs("m", "a-open")
    assert "stock.m-b-open" not in spec.belongs and "flow.m-b-in" not in spec.belongs   # never read from the text
    # the very name taken by hand: the hand-written part is first and keeps no owner; the remote's is not put over it
    local = LOCAL.replace("m-b-open", "m-a-open").replace("m-b-in: {to: m-a-open, driven-by: [+stock.m-a-open]}",
                                                          "m-b-in: {to: m-a-open}")
    from ergostat.spec.load import load
    write(tmp_path / "two" / "support", local)
    served_into(tmp_path / "two" / "support", tmp_path / "two", remote="m", text=REMOTE)
    doc = load(tmp_path / "two" / "support" / "ergostat.yaml")
    hand = doc.defined[("stocks", "m-a-open")]
    assert getattr(hand, "belongs", None) is None and not hasattr(hand, "remote")
    assert doc.defined[("flows", "m-a-in")].belongs == Belongs("m", "a-in")


def _graph(nodes, focus=None):
    return {"kind": "control", "focus": focus, "nodes": nodes, "edges": []}


def test_inside_a_systems_box_the_short_name_is_shown_with_the_full_name_available_outside_the_full_name(tmp_path):
    spec = _read(USES, tmp_path)
    assert by_name(spec)["questions-waiting"] == Belongs("questions", "waiting")
    inside = {"id": "stock:questions-waiting", "kind": "stock", "label": "questions-waiting", "systems": ["questions", "work"]}
    hand = {"id": "stock:questions-extra", "kind": "stock", "label": "questions-extra", "systems": ["work"]}
    g = shorten(_graph([inside, hand]), spec)
    assert inside["shown"] == "waiting" and inside["label"] == "questions-waiting"     # the full name kept: hover, links
    assert "shown" not in hand                                                      # no owner: its full name
    # drilled into the instance: the system known, so its parts read short
    drilled = {"id": "stock:questions-waiting", "kind": "stock", "label": "questions-waiting", "systems": []}
    shorten(_graph([drilled], focus="questions"), spec)
    assert drilled["shown"] == "waiting"
    # drawn outside the instance's box (only work open), or as a terminal at the edge: the full name
    out = {"id": "stock:questions-waiting", "kind": "stock", "label": "questions-waiting", "systems": ["work"]}
    term = {"id": "term:stock:questions-waiting", "kind": "terminal", "label": "questions-waiting", "systems": []}
    shorten(_graph([out, term], focus="work"), spec)
    assert "shown" not in out and "shown" not in term
    # a closed box: its measure rows and ports are inside it
    box = {"id": "system:questions", "kind": "system", "label": "questions", "systems": ["work"],
           "measures": [{"part": "stock:questions-waiting", "label": "questions-waiting"}],
           "ports": [{"id": "p", "label": "questions-waiting"}, {"id": "q", "label": "questions-extra"}]}
    shorten(_graph([box]), spec)
    assert box["measures"][0]["shown"] == "waiting" and box["ports"][0]["shown"] == "waiting"   # one part: no clash
    assert "shown" not in box["ports"][1]
    assert g is not None


def test_two_parts_drawn_side_by_side_never_read_the_same(tmp_path):
    spec = _read(USES.replace("questions-extra: {system: work}", "waiting: {system: questions}"), tmp_path)
    mine = {"id": "stock:questions-waiting", "kind": "stock", "label": "questions-waiting", "systems": ["questions"]}
    hand = {"id": "stock:waiting", "kind": "stock", "label": "waiting", "systems": ["questions"]}
    shorten(_graph([mine, hand]), spec)
    assert "shown" not in mine and "shown" not in hand                  # "waiting" twice: both by their full names


def test_an_owner_unknown_is_drawn_by_its_full_name(tmp_path):
    spec = _read(USES, tmp_path)
    spec.belongs = {}                                                   # nothing recorded: nothing shortened
    n = {"id": "stock:questions-waiting", "kind": "stock", "label": "questions-waiting", "systems": ["questions"]}
    shorten(_graph([n]), spec)
    assert "shown" not in n


GOLDEN = {   # examples/small-requests, as it compiled before parts recorded their systems
    "systems": ["build-cache", "help-queue", "modelling", "morning", "regressions", "review-reminders", "work"],
    "stocks": ["accepted-changes", "answered-requests", "build-cache-level", "changes-testing", "help-queue-waiting",
               "model-error", "morning-due", "morning-written", "passed-changes", "pending-changes", "regressions-done",
               "regressions-draft-revert", "regressions-draft-revert-working", "regressions-find-culprit",
               "regressions-find-culprit-working", "regressions-label", "regressions-label-working", "regressions-stuck",
               "review-reminders-given-up", "review-reminders-pings-sent", "review-reminders-unanswered",
               "unanswered-requests"],
    "flows": ["build-cache-corrected", "build-cache-rising", "changes-accepted", "changes-failed", "changes-made",
              "changes-made-by-fixer", "changes-passed", "changes-superseded", "help-queue-answered",
              "help-queue-answered-by-hand", "help-queue-arriving", "model-drift", "model-mended", "morning-falling-due",
              "morning-writing", "regressions-arriving", "regressions-draft-revert-done", "regressions-draft-revert-retried",
              "regressions-draft-revert-stuck", "regressions-draft-revert-taken", "regressions-find-culprit-done",
              "regressions-find-culprit-retried", "regressions-find-culprit-stuck", "regressions-find-culprit-taken",
              "regressions-label-done", "regressions-label-retried", "regressions-label-stuck", "regressions-label-taken",
              "regressions-unstuck", "requests-answered", "requests-raised", "review-reminders-answered",
              "review-reminders-asked", "review-reminders-giving-up", "review-reminders-pinging",
              "review-reminders-taken-over", "tests-started"],
    "auxiliaries": ["help-queue-oldest", "review-reminders-oldest"],
    "goals": ["build-cache-under", "help-queue-on-time", "help-queue-picked-up", "model-fits", "morning-on-time",
              "regressions-draft-revert-clear", "regressions-find-culprit-clear", "regressions-label-clear",
              "regressions-none-stuck", "requests-handled", "review-reminders-none-given-up", "review-reminders-reminded"],
    "blocks": ["build-cache-correct", "fixer", "help-queue-answer", "help-queue-escalate", "improver", "judge",
               "keep-build-cache-under", "keep-help-queue-on-time", "keep-help-queue-picked-up", "keep-model-fits",
               "keep-morning-on-time", "keep-regressions-draft-revert-clear", "keep-regressions-find-culprit-clear",
               "keep-regressions-label-clear", "keep-regressions-none-stuck", "keep-requests-handled",
               "keep-review-reminders-none-given-up", "keep-review-reminders-reminded", "morning-writer",
               "regressions-draft-revert", "regressions-find-culprit", "regressions-label", "regressions-unstick",
               "review-reminders-pinger", "review-reminders-take-over"],
    "items": ["ergostat.claim", "ergostat.context", "ergostat.correction", "ergostat.decision", "ergostat.message",
              "ergostat.model-change", "ergostat.modelling-request", "ergostat.report", "ergostat.verdict", "help-queue",
              "morning", "regressions", "review-reminders"]}


def test_an_existing_example_compiles_to_the_same_full_names():
    spec, ps = sp.read(ROOT / "examples" / "small-requests" / "ergostat.yaml", extremes=False)
    got = {s: sorted(getattr(spec, s)) for s in ("systems", "stocks", "flows", "auxiliaries", "goals", "blocks", "items")}
    assert got == GOLDEN
    assert spec.belongs["stock.help-queue-waiting"] == Belongs("help-queue", "waiting")
    assert "stock.model-error" not in spec.belongs                      # a once template keeps its names: no owner
    for ref, b in spec.belongs.items():                                  # each owned part: its system's name, then its own
        assert ref.split(".", 1)[1] == f"{b.system}-{b.short}"
