# agent-page-narrow-ai-and-decision: The Agent page shows a narrow AI's specification and a decision agent's means, as the proposal settles

depends-on: [agent-means-proposal, agent-show-page]

Problem: after agent-show-page the person, ai, program and rule rungs show how they work; narrow-ai and decision show only their contract and observed decisions, because nothing declares a specification or a set of answers (ergostat/spec/compile.py:83, KIND_RUNS :114), and no demo has either rung.
Change: implement what docs/proposals/agent-means.md settles: the declared key(s), if any, in spec/compile.py TYPE_KEYS with a check; the 'Its specification' section for narrow-ai and 'How it decides' for decision in static/agent.js (declared answers each with its count in the window from state.decisions, an answer outside them flagged, an answer never given shown as such); the ladder move shown as the same block's history; the demo or fixture agents the proposal names.
Definition of done:
1. The proposal's acceptance points hold on the named demo or fixture.
2. /agent/NAME for its narrow-ai agent shows its prompt rendered and its specification rows.
3. /agent/NAME for its decision agent shows its declared answers (if the proposal declares them) with counts, and an undeclared answer flagged.
4. `ergostat check` reports a decision line outside the declared answers (if declared).
5. SPEC and docs/vocabulary.md updated as the proposal lists.
Files: as the proposal lists; expected ergostat/spec/compile.py, ergostat/state.py, ergostat/web/agent_spec.py, ergostat/web/static/agent.js, docs/SPEC.md, one demo, tests.
Acceptance tests: a compile test for the key; an API test for the tally against declared answers; a browser test on the named demo.
Budget: 200 net lines; revise to the proposal's figure.

Milestone: agent-show-page. Owner items: 19. From the owner's list and the design review of 2026-11-22.
