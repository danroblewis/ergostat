# ui-a-request-reads-as-a-sentence-what-will-happen-t: A request reads as a sentence: what will happen, to what, who asks and why

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q44 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list; action and request item pages

**The problem:** Entries read 'person/approve@3156 approve is asked: Outward acts wait for your approval. `ergostat actions` lists them (and the p...', cut off; an action's first line is 'ran jira-transition, class jira-transition, gate approve' with the plain description buried in Fields; 'modelling holds no-unit on stock.api-q0 … the decision tier has no certain change for it'.

**The change:** First line from fields the entry already has: '{description} {target}, for {item}, asked by {block} because {why}', for example 'Move SCRUM-7 to Done in Jira, for ticket/SCRUM-7, asked by close'. Person asks print in full (a <details> for anything past three lines). The exact command sits in a collapsed <details>. A modelling request reads 'api-q0 has no unit: modelling cannot decide one. Deny tells it to stop asking; the unit is yours to set through the Supervisor.'

**User stories it serves:** E2, A4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8792/ no entry under 'Waiting for you' contains '...' or a backtick; each has a first line ending before any 'python3'; the command is inside a closed <details>; every Deny-only entry contains a sentence starting 'Deny '.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
