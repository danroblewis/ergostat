# ui-the-vocabulary-rewrite-never-touches-an-identifi: The vocabulary rewrite never touches an identifier

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q46 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list (Dynamics wording)

**The problem:** The Dynamics wording is a find-and-replace: 'queue-goal-tolerance on goal.ci-upgrade-planned' becomes 'queue-desired level-tolerance on desired level.ci-upgrade-planned', and 'a desired level's desired level and tolerance'. The same request reads 'decision tier' in one view and 'rule tier' in the other.

**The change:** Translate only the sentence's own words, never codes, ids or part names (render them as separate tokens). The tier named comes from the request, not the view.

**User stories it serves:** E2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8792/ in Dynamics the text of request/80fe1e93e1 contains 'queue-goal-tolerance' and 'goal.ci-upgrade-planned' or its plain name, and does not contain 'desired level.' or 'desired level-'; its text in Blocks names the same tier.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built.

- The change: the Dynamics wording is `words()` in `ergostat/dynamics.py`. It runs on the server
  (`/api/graph?view=dynamics` rewrites the side list's attention cards); nothing under `ergostat/web/` rewrites.
  So the fix is in that one function, not under `ergostat/web/` as "Files to touch" guessed: the most reversible
  place. Before it translates, it sets aside what is not the sentence's own words, then puts it back. That is any
  word joined to the next by `.`, `-`, `/` or `:` (a code, an id, a part name: `queue-goal-tolerance`,
  `goal.ci-upgrade-planned`, `request/80fe1e93e1`) and a tier (`rule tier`, `ai tier`, `owner tier`), so a request
  names the same tier in both views. "a goal's setpoint" now says "a desired level" (it said "a desired level's
  desired level"). A part whose name is one plain word (no joiner) and is one of the rewritten words is still
  translated: the text carries no mark of what is a part name, and the acceptance names only joined ids. The SPEC's
  Dynamics view section says this in one sentence.
- Size: +17 net lines in `ergostat/dynamics.py`, within 60.
- Tests: `tests/test_diagram_rendering.py::test_the_dynamics_wording_never_touches_a_requests_code_id_or_tier`
  is the acceptance. It holds request 80fe1e93e1 (queue-goal-tolerance on goal.ci-upgrade-planned) and a rule-tier
  request in the-job, and reads both from the side list in Dynamics and in Blocks.
  `tests/test_dynamics_view.py::test_the_dynamics_wording_keeps_codes_ids_and_tiers_as_they_are` is the unit test.
  Each break was seen to fail the browser test: with nothing set aside it fails on "queue-desired level-tolerance on
  desired level.ci-upgrade-planned"; with ids kept but tiers not, it fails on "the decision tier".
- Run: tests/test_dynamics_view.py, 11 passed; ruff clean. tests/test_diagram_rendering.py in full, twice, under
  the watchdog, nothing skipped: 199 passed and 2 failed, then 200 passed and 1 failed. The failure both times is
  `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` (line 3346: the /model page does
  not say 'Nothing waiting.'). It fails the same way with this change taken out of `dynamics.py` (back to main's
  code), and the /model page never calls `words()`: unrelated, left alone (lesson 13). The first run's second
  failure was not named (only the output's tail was kept) and did not happen in the second run.
- Not run: the unit suite, the other three browser files and demo_check (left to the factory). No merge of main
  was needed: the branch was made from the current `main`.
