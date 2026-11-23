# inbox-says-what-a-person-may-do: The requests group opens with one sentence saying what a person may do here

depends-on: []

Problem (R3 piece 9, story A4): decision 7 makes approving or denying the one thing people do, and nothing on the page says so. A newcomer cannot tell whether clicking a part changes the system (shots/story-4-home.png, ixdb-tf-approve-item.png).
Change: at the head of the requests group in Needs attention (ergostat/web/static/diagram.js:1347, the group filed Q42 heads 'Waiting for you'), and at the head of the Actions page, one muted sentence: 'You can look at everything. Approving or denying these is the only thing that changes the system.' With no request waiting the group reads 'Nothing waits for you. Looking never changes the system.' The sentence is announced once with the group (aria-describedby), not on every poll.
Definition of done:
1. On a fixture with requests waiting the sentence is the first text of the group; with none, the empty form shows.
2. The same sentence is on the Actions page.
3. A screen reader reads it once when focus enters the group (the group has aria-describedby pointing at it).
4. At 390 px it wraps without overflow.
Files: ergostat/web/static/diagram.js, pages.js (Actions), style.css, tests/test_diagram_rendering.py.
Acceptance tests: a browser test for 1-3.
Budget: 20 net lines.

Milestone: r3-needs-attention-is-the-inbox. Owner items: R3 piece 9 (pieces 1-8 are filed Q42-Q51, Q77; piece 10 is in demos-upkeep-holds-and-actions-wait). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. Two choices made with no one to ask, each the more reversible one:
- There is no 'Waiting for you' requests group on main yet (Q42 has not landed). So the sentence opens the whole
  *Needs attention* list (`.att`, now `role="group"` with `aria-describedby="may-do"`). The long form shows when any
  entry there has an answer (a request), and the empty form when none does. Once Q42 lands, the same `p#may-do` moves
  to the head of its group.
- There is no Actions page: gated actions are the Items page with `kind=ergostat.action`, and the house rules forbid
  new pages. So the sentence heads the Items page when that kind is chosen, and nowhere else on it.
Acceptance test: `tests/test_diagram_rendering.py::test_the_requests_group_opens_by_saying_what_a_person_may_do`
(waiting and none). It covers 1-4: first text of the group, the empty form, the Items-page sentence, aria-describedby
with no live region, a redraw that neither replaces nor changes the node, and no overflow at 390 px. "A screen reader
reads it once" is checked through those DOM facts, not with a real screen reader. Five breaks were each seen to fail
it: no aria-describedby, always the empty form, an attribute changed on each render, `white-space: nowrap` (fails
only the long form, since the short one fits at 390 px), and the Items-page sentence never shown.
Net lines outside tests and docs: 8, within the 20 budget.
Suites: the new test, tests/test_inbox_page.py and tests/test_items_page.py pass, and ruff is clean. The whole of
tests/test_diagram_rendering.py, run serially: 195 passed, 7 failed. On a rerun, 3 passed
(valve-upright, pages-are-ordinary-links, block-dragged), and 4 failed again, none in code this gap touches:
- `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]`: libavoid routing took 34 s and 32 s
  against a 20 s bound.
- `test_a_big_tangled_model_lays_out_in_time_and_cleanly`: the first draw took 3.2 s against 2.5 s.
- `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: 'Nothing waiting.' is missing from
  the Model page's review queue. A past review saw the same failure on other branches.
These four were not run on main: the command that put main's page code in place for the comparison was refused. The
unit suite and the other browser files were not run here (the factory runs them). main has not moved since the clone,
so there was nothing to merge.
Build fix: the factory's `build` step (affected_tests) chose only tests/test_diagram_rendering.py, a browser file.
Without Playwright it skips as a module, so pytest exits rc 5 (no tests run). The page code was not at fault. A unit
test that needs no browser now checks the sentence at its source:
`test_needs_attention_and_the_actions_page_say_one_sentence_of_what_a_person_may_do` in tests/test_graph_cli_web.py.
That test is outside the Files list, but it is the reversible choice: it changes no factory script and no ergostat
code, so the build has a real test to run. tests/test_graph_cli_web.py passes in full, run serially: 33 passed. Ruff
is clean. `suite_watch.py` around named_tests was refused, so the file was run without the watchdog.

Round 2: the merge of main (7a905955) is done. Main now has Q42's groups and a page of each kind's own, so:
- The sentence `p#may-do` is the first child of the *Waiting for you* list (`.att.needs`, now `role="group"`,
  `aria-describedby="may-do"`), above the answered rows. Main draws that group only when something waits, and the
  more reversible choice was to keep that rule: with nothing waiting no group is drawn, and the short sentence stands
  in its place, above *How to read it*. If the owner wants the group always drawn, only that `else` changes.
- The SPEC entry is main's text with the sentence added to it.
- The gated actions' own page (`/items/ergostat.action`) shows the sentence too. The acceptance test now checks
  that page and the Items tab's `?kind=` form.
- `GROUPS`, the row reader of main's `test_needs_attention_is_three_headed_groups_in_a_fixed_order`, now skips
  `p.may-do`, since the sentence is not an entry. The unit test now looks for the sentence in the waiting group.
Breaks seen to fail the acceptance test this round: no aria-describedby on the group (fails `waiting`), and the empty
form placed below *How to read it* (fails `none`).
Net lines outside tests and docs against main: 6.
Suites, each run serially under suite_watch with Playwright: the acceptance test (2 passed);
tests/test_inbox_page.py, 12 passed; tests/test_graph_cli_web.py (no browser), 48 passed; and by name from
tests/test_diagram_rendering.py, the side-panel tests (nothing waiting, waiting first, more than three fold,
one step from every page, changed count announced) all passed. Ruff is clean. Not passing, and not caused by this
gap (each failed the same way with the gap's lines undone by hand):
- `tests/test_diagram_rendering.py::test_needs_attention_is_three_headed_groups_in_a_fixed_order`: its first wait (3
  headed groups and "loops off" in the header) times out at 30 s. It also failed with main's renderSide code.
- `tests/test_items_page.py::test_actions_say_per_class_asked_approved_denied_and_whether_held` (the `.action-classes`
  line never shows on /items) and `::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` (wait
  timeout). Both failed with main's pages.js lines. The rest of that file passed: 56.
All three start `ergostat web` as a subprocess. Why they fail here was not found.
The whole of tests/test_diagram_rendering.py did not finish: its first run hit the tool's time limit and was stopped,
and a second run in the background, as `uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0
python scripts/named_tests.py tests/test_diagram_rendering.py > /tmp/dr.log 2>&1`, was refused.

Round 3: the merge of main (f086f76e) is done. It conflicted in four files, each resolved by keeping both sides:
- diagram.js: main's new `row`/`one` and the folded rows (alike requests as one entry), with the branch's `more`
  argument to `list` (the group's role and aria-describedby).
- pages.js: main's `found` in the filters and its removal of the `more` note, with the branch's `mayDo` after them.
- SPEC: main's fold sentence, then the branch's sentence text.
- tests/test_diagram_rendering.py: both sides' new tests, one after the other.
Net lines outside tests and docs against main: 11 added, 5 removed (6 net), within the 20 budget.
Suites, run serially with Playwright under suite_watch: the acceptance test (2 passed); from
tests/test_diagram_rendering.py by name, main's alike-requests fold, two folds keep their reasons, more than three
fold, and nothing waiting opens on the legend (all passed); tests/test_graph_cli_web.py (no browser), 48 passed;
tests/test_items_page.py, 59 passed and 2 failed. Ruff is clean. Still failing, the same three as in round 2, and the
same way (round 2 found each failing with the gap's lines undone): `test_needs_attention_is_three_headed_groups_in_a_fixed_order`
(the 30 s wait), and in test_items_page.py `test_actions_say_per_class_asked_approved_denied_and_whether_held` (the
`.action-classes` line never shows) and `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` (the
30 s wait). They were not run on main this round.
Refused this round, as given: `node --check ergostat/web/static/diagram.js` (the browser tests load the same files
without page errors instead), and `uv run python scripts/suite_watch.py -- uv run python scripts/named_tests.py
tests/test_graph_cli_web.py` (it was then run without the watchdog). The whole of tests/test_diagram_rendering.py was
not run.
