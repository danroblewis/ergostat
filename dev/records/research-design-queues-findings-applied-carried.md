# research-design-queues-findings-applied-carried: The knowledge queue holds findings: a sourced research answer is proposed as a finding, applied by lesson-apply and carried by area

depends-on: [research-design-queues-research-sources-checked, research-design-queues-research-in-gap-briefs]

Problem: the knowledge base holds only the house rules, the review lessons and the decisions. A `finding` entry kind exists, but such entries are "synced as items but not yet carried in briefs" (dev/knowledge/README.md:24). What research learns about the code or the world never reaches the next gap in the same area (docs/proposals/knowledge-graph.md:19). The knowledge queue (lesson items, the knowledge-change gate, lesson-apply; dev/bin/lesson.py:1-11) works, but it takes only lesson entries and "seen as" lines (lesson.py:30-40; knowledge.applied, knowledge.py:103-127). The kb-* gaps that would carry facts are parked because their facts became gaps (kb-proposals: "approval makes a gap"), which the owner refused.

Change: let lesson items take kind `finding`.
- When research.py says research.answered with at least one checked source, it proposes one: lesson/finding-<slug of the question, at most 40>-<hash6>, kind finding. Its entry is the summary plus "Source: research/<id>" and the checked sources. Its areas are the --areas given to ask.py, or for a planner's question the gap's touched packages. It is asked as knowledge-change, as the librarian does, at most one per answer, and never again for an id in any state.
- lesson-apply applies an approved finding into the record.
- knowledge.applied turns each applied finding into an entry `finding-<slug>` of kind finding with its areas.
- knowledge.block carries findings for the implementor, planner and researcher roles by the same area-word match as decisions, under "What the factory has found", recorded carried or dropped.
- `lesson.py retire` works on findings.
- In the model: the stock lessons-proposed counts findings too (description), and a stock findings-active counts the active findings.

Definition of done:
1. A checked answer proposes exactly one finding, asked through knowledge-change. An unsourced one proposes none.
2. Approved and applied, it is an entry finding-<slug> carried in the brief of a gap whose text names one of its areas, and not in one that names none.
3. A denied finding is never proposed again.
4. Retiring a finding stops it being carried.
5. No gap is made at any step.
6. dev/knowledge/README.md describes findings, and says each is approved before it lands and that private material never does.

Files to touch: dev/bin/research.py, dev/bin/lesson.py, dev/bin/knowledge.py, dev/bin/ask.py (--areas), dev/model/knowledge.yaml, ergostat.yaml (the lesson kind's description and show), dev/knowledge/README.md, tests/test_factory_knowledge.py.

Acceptance tests (tests/test_factory_knowledge.py):
- test_checked_answer_proposes_one_finding
- test_unsourced_answer_proposes_nothing
- test_applied_finding_carried_by_area
- test_denied_finding_never_proposed_again
- test_retired_finding_not_carried
- test_no_gap_requested_for_a_finding

Size budget: 150 net lines (code and YAML; tests and docs excluded).

Area: research-design-queues. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
