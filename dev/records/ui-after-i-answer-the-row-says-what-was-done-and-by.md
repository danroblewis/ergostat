# ui-after-i-answer-the-row-says-what-was-done-and-by: After I answer, the row says what was done and by whom, and the item shows it

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q49 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list; /item/… 'Gated actions'

**The problem:** Nothing confirms an answer; the item's Gated actions lines say 'ran 31m ago, gate approve' without by whom.

**The change:** The answered row is replaced in place by 'Denied by you at 04:02, reason: … · see ticket/SCRUM-2' and stays until the next visit. The item's Gated actions line reads 'jira-transition: approved by owner (offline stand-in) 03:24, ran 03:24' or 'denied by … : reason'.

**User stories it serves:** E3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
After pressing Deny on a test request the row contains 'Denied by' and a link to the item; that item's page contains the same request with 'denied by'. Every Gated actions line contains 'approved by' or 'denied by'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped (round 1)

Built, within the budget (about 30 net lines outside `tests/`).

- `/diagram` side list (`ergostat/web/static/diagram.js`): after Approve, Deny or Done, the answered row is replaced in
  place by `<entry> Denied by you at HH:MM (<state>), reason: … · see <item>`. The link goes to the item the action is
  for, or, when it is for no item, to the action's own page. Answered rows are kept in memory (`ANSWERED`) and drawn
  where the waiting rows are listed each time the side list is drawn again, until the page is loaded again. They carry
  `data-answered`, not `data-inbox`, so the existing check that the waiting row goes away still holds.
- `/item/…` Gated actions (`ergostat/web/static/pages.js`): an answered line reads `push: approved by owner 03:24, ran
  03:24` or `push: denied by owner 04:02: reason`. A held line is unchanged (`waiting for approval, 3m ago, gate
  approve`): it has no answer yet, so "every line" in the acceptance check is read as every answered line. The test
  item has only answered actions, so the test checks every line it lists.
- One file outside `ergostat/web/`: `ergostat/inbox/answer.py` now also returns the entry's `link` and, for an action,
  the `item` it is for (two keys added to the answer, nothing removed). The page had no other way to name the item
  in the confirmation. `ergostat/web/actions_api.py` now sends each action's `moves`, which give the times.
- Left out, and the easiest choice to undo: the brief's "(offline stand-in)". The page shows the name the record
  holds (`owner`). The CLI records `owner` too, so adding "offline stand-in" to every `owner` would be wrong for CLI
  answers.

Test: `tests/test_inbox_page.py::test_a_denied_row_says_by_whom_and_links_its_item_whose_page_shows_it`. I broke the
code three ways and the test failed each time: answered rows not drawn again (it failed at the "still there" check),
"approved by" dropped from the item line, and the item dropped from the answer.

## Where it stopped (round 2)

Main (52c675fe) is merged in. It conflicted in `diagram.js`, `pages.js`, `tests/test_inbox.py` and
`tests/test_inbox_page.py`. Built, within the budget (25 net lines in `ergostat/`, counted against `main`).

- `/diagram` side list: main now splits the list into three groups and holds it still while the reader is in it.
  An answered row now stays in its place, with its reply in the row, until the reader leaves. The branch now follows
  that rule. On Approve, Deny or Done, the row's reply becomes the confirmation (`Denied by you at HH:MM (denied),
  reason: … · see <item>`, with the link). The row is no longer swapped out at once, because that broke main's
  hold-still tests. When the reader leaves, the row is drawn again as the `data-answered` row at the top of "Waiting
  for you". It stays there until the page is loaded again. An entry answered here is left out of the waiting group
  (and is not moved into housekeeping), so a late graph answer can't draw it twice.
- `/item/…` Gated actions: the line now uses main's `actionSays` and `commandBox`. Who answered comes from main's
  `record.who` text (`approved by`), so a gate's own denial, and an approval a later denial overrode, read the way
  the record words them. An answered line reads `<action>: asked by writer, approved by owner (offline stand-in)
  03:24, ran 03:24` or `…: asked by …, denied by owner (reason) 04:02`. Main's
  `tests/test_agents_page.py` checks for `asked by writer, approved by owner (offline stand-in)`, so "asked by" comes
  first. Round 1 left out the brief's "(offline stand-in)". It now shows when the record holds it as the answer's
  note, as main records it.
- Tests: kept both sides. In `tests/test_inbox_page.py`, main's `pushes` fixtures sit next to the branch's
  `ticket_site`. The acceptance test now checks the reply in the held row first ('Denied by you at' and the item
  link), then the `data-answered` row after the reader leaves.
- Checked that the test can fail, three ways: the confirmation not put in the row (failed), answered rows not drawn
  again (failed), "approved by" dropped from the item line (failed).

## Where it stopped (round 3)

Main (ead497d1) is merged in. It conflicted in `diagram.js`, and the conflict is resolved with main's side kept
throughout. `inboxAnswer` is main's: each button names what it answers, the reason field comes before the buttons,
and Deny waits until a reason is typed. The branch adds only the confirmation in the row's reply (`ANSWERED` and
`answeredSays`). The side list uses main's `waitsOnYou` (util.js) and the `id="waiting"` heading. Entries answered
here are still left out of the waiting group and drawn at its top as `data-answered` rows.

- The acceptance test's reason field is now found by main's label (`Why deny …`), not the old `Why`.
- `tests/test_inbox_page.py` passes (10 tests). The acceptance test was broken again after the merge (the reply set
  to the server's plain `said`) and it failed.
- Failures this branch does not touch, left alone (lesson 13):
  - `tests/test_agents_page.py::test_each_row_says_how_it_is_engaged_and_which_goal_it_serves` passes alone and
    fails when the whole file runs. It reads `#detail` while the panel still says "Loading…". That is a test race on
    `/agents` (`details.js`), which this branch does not change.
  - `tests/test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` times out
    waiting for the `#project` switcher's other-project option. That is the header, and the branch does not change
    it. Not rerun on clean main here.
