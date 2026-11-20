"""What the redesigner learns from (SPEC §12e, *Redesign*; numbers/redesign_memory.py): its past change sets for the
system with what became of each, and the interventions about the system as evidence of missing loops, both bounded."""

from __future__ import annotations

from ergostat.inbox import interventions as iv
from ergostat.numbers import changeset as cs
from ergostat.numbers import proposals as pr
from ergostat.numbers import redesign_memory as rm
from ergostat.numbers import redesigner as rdr

from .test_inbox import MODEL, project

SYSTEMS = MODEL.replace("    ask: review the queue\n", "    ask: review the queue\n    system: review\n", 1).replace(
    "    mode: advise\n", "    mode: advise\n    system: ship\n", 1) + \
    "systems:\n  review:\n    description: the queue reviewed\n  ship:\n    description: what is pushed\n"


def redesign(p, pid, system, title, end, **data):
    pr.event(p, pid, "made", {"kind": "redesign", "system": system, "title": title, "summary": f"{title}, in short",
                              "made_by": "redesigner", "redesign": {"edits": [{"said": f"edit of {title}", "why": "w"}]}},
             source="redesigner")
    pr.event(p, pid, "checked", {"scorecard": {"verdict": "no better", "why": "nothing improves"}})
    if end == "dismissed":
        pr.event(p, pid, "dismissed", {"dismissed_because": data["because"], "dismissed_by": "owner"}, source="owner")
    elif end:
        pr.event(p, pid, "testing", {})
        pr.event(p, pid, end, {"verdict": {"verdict": end, "why": data.get("why") or ""}})


def test_the_memory_says_each_past_redesign_and_its_verdict(tmp_path):
    p, _ = project(tmp_path, SYSTEMS)
    spec = p.model.spec
    redesign(p, "r1", "review", "A pool for the reviewer", "dismissed", because="the reviewer is one person; no pool")
    redesign(p, "r2", "review", "Review split in two", "failed", why="the fit is 30% worse")
    redesign(p, "r3", "ship", "Push in batches", "dismissed", because="batches break the build")
    redesign(p, "r4", "review", "Waiting", None)
    pr.event(p, "c1", "made", {"kind": "parameter", "title": "the reviewer twice as fast", "parts": ["block.reviewer"],
                               "made_by": "improver"}, source="improver")
    pr.event(p, "c1", "checked", {})
    pr.event(p, "c1", "dismissed", {"dismissed_because": "the reviewer is not faster, only interrupted less",
                                    "dismissed_by": "owner"}, source="owner")
    got = "\n".join(rm.memory(p, spec, "review"))
    assert 'redesign "A pool for the reviewer": DISMISSED by the owner. the owner\'s reason: "the reviewer is one person; no pool"' in got
    assert 'redesign "Review split in two": judged NOT better' in got and "the fit is 30% worse" in got
    assert 'redesign "Waiting": proposed, not judged yet' in got and "edits: edit of Waiting" in got
    assert 'parameter "the reviewer twice as fast": DISMISSED' in got and "interrupted less" in got   # about its parts
    assert "Push in batches" not in got                                  # another system's
    assert "Push in batches" in "\n".join(rm.memory(p, spec, "model"))   # the whole model's: every system's
    assert rm.memory(p, spec, "ship") == ["- redesign \"Push in batches\": DISMISSED by the owner. the owner's reason: "
                                          "\"batches break the build\". scorecard: no better nothing improves. it did: Push in "
                                          "batches, in short. edits: edit of Push in batches"]


def test_the_memory_is_bounded_by_count_and_characters(tmp_path):
    p, _ = project(tmp_path, SYSTEMS)
    spec = p.model.spec
    for i in range(12):
        redesign(p, f"r{i:02d}", "model", f"Idea {i}", "dismissed", because=f"no {i}")
    got = rm.memory(p, spec, "model")
    assert len(got) == rm.MEMORY_MOST + 1 and got[-1] == f"- ({12 - rm.MEMORY_MOST} more changes not shown)"
    assert got[0].startswith('- redesign "Idea 11"')                                    # the newest first
    for i in range(12):
        redesign(p, f"long{i:02d}", "model", f"Long {i} " + "x" * 900, "dismissed", because="no " + "y" * 900)
    got = rm.memory(p, spec, "model")
    assert all(len(x) <= rm.ONE for x in got) and sum(map(len, got)) <= rm.MEMORY_CHARS + 60
    assert len(got) == 6 and got[-1] == "- (19 more changes not shown)"                  # the characters bound first
    assert rm.memory(p, spec, "review") == []                                         # nothing for a system with no past


def test_interventions_are_selected_per_system_with_their_notes(tmp_path):
    p, _ = project(tmp_path, SYSTEMS)
    spec = p.model.spec
    for n in range(3):
        p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3})
        p.events.add("agent.ran", item="reviewer", source="person", data={"done": 3, "note": f"the queue doubled again ({n})"})
    p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 2})
    p.events.add("block.denied", item="pusher", source="owner", data={"note": "pushing now would break the build"})
    item = iv.request_id("alarm:queue-high")
    p.events.add(f"{iv.MODEL_REQUEST}.opened", item=item, source="ergostat",
                 data={"class": "alarm:queue-high", "cause": "block reviewer", "count": 7, "hours": 5.0,
                       "remedies": ["add the missing loop: a goal and a controller on the queue"], "why": "it recurs"})
    p.events.add(f"{iv.MODEL_REQUEST}.investing", item=item, source="owner", data={"note": "it rises every Monday"})
    review = "\n".join(rm.interventions(p, spec, "review"))
    assert "- alarm:queue-high: 7 times, 5.0h blocked" in review and '"it rises every Monday"' in review
    assert "request investing" in review and "remedies" not in review          # generic: they misled (redesign-bench)
    assert "- person:reviewer: 3 times" in review and "answered: approved 3" in review
    assert '"approved: the queue doubled again (2)"' in review
    assert review.index("alarm:queue-high") < review.index("person:reviewer")          # the most hours blocked first
    assert "pusher" not in review
    ship = "\n".join(rm.interventions(p, spec, "ship"))
    assert "advise:pusher: 1 time" in ship and '"denied: pushing now would break the build"' in ship
    assert "reviewer" not in ship and "queue-high" not in ship
    whole = rm.interventions(p, spec, "model")
    assert len(whole) == 3
    assert rm.interventions(p, spec, "model", most=1) == [whole[0], "- (2 more classes not shown)"]


def test_the_prompt_carries_the_memory_and_the_interventions(tmp_path):
    p, _ = project(tmp_path, SYSTEMS)
    redesign(p, "r1", "review", "A pool for the reviewer", "dismissed", because="the reviewer is one person")
    p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 2})
    p.events.add("block.denied", item="pusher", source="owner", data={"note": "pushing now would break the build"})
    text = rdr.prompt(p, cs.Scratch(p), "review", ["asked"])
    assert "## What was proposed before for this system" in text and "the reviewer is one person" in text
    assert "## Interventions: evidence of missing loops" not in text            # the pusher is another system's
    whole = rdr.prompt(p, cs.Scratch(p), "model", ["asked"])
    assert "## Interventions: evidence of missing loops" in whole and "pushing now would break the build" in whole
    (tmp_path / "fresh").mkdir()
    q, _ = project(tmp_path / "fresh", SYSTEMS)
    assert "## What was proposed before" not in rdr.prompt(q, cs.Scratch(q), "model", [])
    assert "never propose again" in rdr.guides().lower() and "evidence of a missing loop" in rdr.guides().lower()


def test_a_note_is_said_once_and_a_broken_record_never_fails_the_prompt(tmp_path, monkeypatch):
    p, _ = project(tmp_path, SYSTEMS)
    for _ in range(2):
        p.events.add("block.advised", item="pusher", source="ergostat", data={"command": 2})
        p.events.add("block.denied", item="pusher", source="ci-bot", data={"note": "the build is red"})
    ship = "\n".join(rm.interventions(p, p.model.spec, "ship"))
    assert ship.count("the build is red") == 1 and "denied 2" in ship       # a note not the owner's reaches it, once

    def broken(*a, **k):
        raise KeyError("x")
    monkeypatch.setattr(rm, "memory", broken)
    monkeypatch.setattr(rm, "interventions", broken)
    text = rdr.prompt(p, cs.Scratch(p), "model", [])
    assert "(its past proposals could not be read: KeyError)" in text and "## The record" in text
