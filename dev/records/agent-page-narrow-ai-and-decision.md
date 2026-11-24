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

## Where it stopped

Built, round 1. The proposal (docs/proposals/agent-means.md) settles that **nothing new is declared**, so the
definition's conditional items read as follows (no one could be asked; this is the reversible reading, since a key
can be added later and could not be taken back):
- Done item 3, "declared answers (if the proposal declares them)": an item-taking decision's answers are its
  `takes.to`; they are shown with their counts, a state never reached as "never given", an end outside them flagged
  as "other" (given back, a dead letter, expired), and ends whose take is not in the record as "unattributed".
- Done item 4, "`ergostat check` reports a decision line outside the declared answers (if declared)": not
  applicable, as no answer key is declared. A controller's words are free text (the proposal's §2 rejects the check).
  `check` already refuses a `takes.to` state its kind lacks (`bad-states`).
- "A compile test for the key": there is no key, so the test pins that: `answers:` is refused as an unknown key, and
  no TYPE_KEYS entry names one (`tests/test_agent_means.py::test_no_key_declares_answers_a_decisions_are_its_takes_to`).
- Files: the proposal names `ergostat/agent_means.py`, `web/server.py` and `static/pages.js`. The agent page now lives
  in `web/agent_spec.py` and `static/agent.js` (agent-show-page), so those were changed instead; `server.py` was not
  touched. `ergostat/history.py` gained a `rungs` map in each `model.changed` (one line): without it the record has no
  block's rung per version, and a span list could not be read back. A version recorded before this has its rung said
  "not recorded", except the newest when it is the model loaded now.
- Version numbers: versions are hashes, so a span names them by their place in the record (v1 the oldest
  `model.changed` kept), ordered by `seq`.
- Builtin blocks (proposal §5): a built-in narrow AI (an intent judge on a model) shows its module, the first paragraph
  of its docstring and its declared keys. No test covers that path: no example has such a judge.

Demo: `examples/alert-triage`'s `triage` block moves to a new agent `triager: {kind: narrow-ai, at-once: 2}` (at-once
2 keeps its pool of 2 at work as under `claude`). The golden explain text changes in its one line ("on agent
triager"). `examples/docs-fresh` is unchanged.

Size: 217 net lines outside tests, docs and dev (agent_means.py 188), within the proposal's figure of about 250.

Tests run here: `tests/test_agent_means.py` (7, including the approver fixture, the controller fixture, the spans by
version and a same-name remake), `tests/test_agent_spec.py`, `tests/test_decisions.py`, `tests/test_remote.py`,
`tests/test_agents.py`, `tests/test_model.py`, `tests/test_dynamics_view.py`, all passing; `tests/test_agent_page.py`
whole under the watchdog with Playwright, 38 passed, rc 0, none skipped (new: the narrow AI's page on alert-triage,
the approver fixture's page, and the docs-fresh picker's said / commands-acted-on lists). Each new browser test was seen
to fail with its code broken (spec rows emptied; "other" rows dropped), as was the once-per-run count. ruff is clean.
Merged with `main`: already up to date.

Not run here: `scripts/demo_check.py alert-triage docs-fresh` was refused by this session's shell (as
`uv run python scripts/demo_check.py alert-triage docs-fresh`, and under `scripts/suite_watch.py`), and so was
`uv run ergostat check examples/alert-triage`. The agent-page sweep passed on both demos. The demo was walked with
`scripts/walk.py`, but `--shots /shots` failed with a permission error writing `/shots`, so there are no screenshots.
On the running docs-fresh, page-picker showed "few enough: wait (3)" said and `out: block.doc-writer` 0 acted on.

Outside this gap (the proposal's finding): SPEC §9.9 does not charge runs whose agent is a `decision`, so a decision
program that calls a model spends unseen. That belongs in a gap of its own.

## Entry

The Agent page shows a narrow AI's specification and a decision's means, nothing new declared
(docs/proposals/agent-means.md). For a narrow AI it shows its block's contract as written: what it works, may move,
may use, costs and how it is answered, and the event types its runs wrote, from the record. For an item-taking
decision it shows each `takes.to` state with its count in the window (0: never given), the other ends flagged, and the
ends whose take is not in the record. For a controller it shows what it said (once per run) and, per `out` port, its
commands acted on. A block's rung is kept with each recorded version, so the page lists its rung per span of versions,
each counted apart. alert-triage's triage runs on a narrow AI.
