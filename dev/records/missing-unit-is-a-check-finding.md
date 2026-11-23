# missing-unit-is-a-check-finding: A missing unit is a Check finding drawn as 'unit ?' on the stock, not a request of the owner per stock

depends-on: []

Problem (R2 piece 7): a stock without a unit raises a request to the owner; on big that is 24 requests, which are 24 of the 26 attention entries (shots/pm-big-home.png, story-2-c6-modelling.png). A missing unit is a property of the model, found by checking it, not something a person approves or denies. Every reviewer named the result ('the tool is broken, or is about itself'), and the fix depends on nothing.
Change: the modelling template (ergostat/library/templates/modelling/template.yaml) stops raising a request per unitless stock and requests-handled no longer counts them (this gap owns that edit to requests-handled; demos-upkeep-holds-and-actions-wait follows it); `ergostat check` reports one finding per stock ('no unit', with file and line) which the Model page lists (in filed Q78's table); the Dynamics diagram prints 'unit ?' in the muted tone after the stock's value, with a legend row and the Guide frame that explains a stock's value updated. A fixer run that can infer the unit from the sensor proposes it as a model change as today.
Definition of done:
1. On a fixture with three unitless stocks no attention entry asks for a unit; /api/check lists each unitless stock once.
2. The stock's value on the diagram reads '12 unit ?' and the legend explains it.
3. requests-handled no longer counts unit requests.
4. `ergostat check` on a spec with a unitless stock exits with a warning naming file and line.
Files: ergostat/library/templates/modelling/template.yaml, ergostat/spec/findings.py (or where check findings are made), ergostat/web/static/dynamics.js, review.js, ergostat/guide.py, tests.
Acceptance tests: a check unit test; a browser check on the fixture (and on :8797 by eye).
Budget: 60 net lines.

Milestone: r2-system-first-upkeep-apart. Owner items: R2 piece 7 (second half). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. Net 28 lines outside tests/docs/dev (budget 60).

What was built: `no-unit` moved from a craft note (`spec/craft.py`) to a check finding (`spec/findings.py`, level
`finding`, file and line, template-made stocks left out). `numbers/requests.py` skips it (`CHECK_ONLY`), so the modelling
loop raises no request for it and `unanswered-requests`/`requests-handled` never count it. A unit request stored before
this change is answered with the reason "a check finding now, not a request". The fixer (`modelling rules`) reads the
finding from check itself (`rules.unitless`): it proposes a unit it can infer as a change, as before, never twice for a
stock while a change cites it, and never holds one for the owner. Dynamics draws `unit ?` (muted, italic) after the
value, with a legend row. The Guide's "fills" frame text says what `unit ?` means. The Model page's Tools table has a
"units" row naming each unitless stock. The template reading, SPEC §12, MODELLING-WELL and GAPS are updated.

Decided alone (the most reversible option each time; nobody to ask):
- There is no `/api/check` endpoint on main. The Check page reads `/api/status`'s `check` list, so done 1 is tested on
  that list (tests/test_missing_unit.py, and the browser test reads it over HTTP). No endpoint was added.
- Q78's table is not on main. The Model page lists the stocks as a "units" row in the existing Tools table
  (review.js), not in a new panel. Move it into Q78's table when that lands.
- "Exits with a warning": `ergostat check` exits 0 and prints the `no-unit` finding as a warning line
  (`no-unit  ergostat.yaml:N: stock X: no unit. ...`); findings never fail check, as before.
- Each stock's line is where its own mapping begins (the first line under its name), which is where every other
  finding about a stock points.
- The fixer runs only while requests-handled is off (another request open). On a model whose only issue is missing
  units, no unit is proposed until something else wakes the fixer or a person writes the unit. "A fixer run that can
  infer the unit" was read that way.
- As a finding, `no-unit` now counts in `ergostat.model.open-findings` and among a change's new or answered findings
  (judge, redesign scorecard), no longer among the craft notes.
- The Guide's frames are drawn bare (no readings), so `unit ?` appears only in the frame's text, not on its drawing.

Tests: tests/test_missing_unit.py (4: check finding once each with file and line, warn level on /api/status's list;
no unit request or attention entry, an old one answered, the fixer run holds nothing; the fixer proposes the unit its
sensor counts, once; `ergostat check` rc 0 with a warning naming file and line). Browser:
tests/test_diagram_rendering.py::test_a_stock_with_no_unit_reads_unit_query_after_its_value_and_the_legend_explains_it
('12 unit ?', muted fill, legend row, '3 tickets' for a stock with a unit, /api/status names each once, the Model page's
units row). Tests that expected a unit request were updated in test_self_improve.py and test_redesign.py.
Seen to fail when the code is broken: tspan removed (value read '12'), the request filter removed (a no-unit request is
raised), the Model page's regex broken (row read 'every stock has one').

Not run here: the :8797 check by eye (no server or screen in this session); `demo_check` and the full unit and browser
suites (left to the factory and the merge queue); a scan of the examples for unitless stocks (the shell refused the
scratch script and the loop over `ergostat check`). An example with a unitless stock now shows a `no-unit` warning on
Check and `unit ?` on its diagram, and one fewer request.

Round 2 (answering review/missing-unit-is-a-check-finding-1):
- Blocking (the judge and scorecard counted `no-unit` as a new finding): fixed. `requests.as_note` counts a note or a
  `CHECK_ONLY` finding as a craft note, and the change's findings (improve.py), the scorecard's findings and notes, and
  the redesigner's "check still finds" list use it. The judge and the redesign verdict read `no-unit` as they did on
  main: a change that adds a unitless stock makes no new finding (it is among `notes_new`), and a unit change answers a
  note. So the round 1 line above, that `no-unit` counts among a change's new or answered findings, is no longer
  true. It still counts in `ergostat.model.open-findings`, which the review left alone.
  Test: tests/test_missing_unit.py::test_a_change_adding_a_unitless_stock_is_judged_as_before_a_craft_note_not_a_new_finding
  (fails with `as_note` reduced to the note level: `new` reads ['no-unit@stock.closed']). test_redesign.py's scorecard
  assertion is back to main's (no-unit among craft closed).
- Non-blocking (template.yaml:3 said "everything check finds held as requests"): the description now says a stock with
  no unit is a check finding, not a request.
- Non-blocking (the new files are justified): nothing to change.
Run: tests/test_missing_unit.py (5 passed), tests/test_redesign.py (22 passed), tests/test_self_improve.py (passed
with test_redesign.py before its fix; its one failure was test_redesign's), ruff clean.
Not run: the browser file (this round touches no page), demo_check, the full suites.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:21).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:22).

Its runs failed past their attempts (a dead letter):
- attempt 9: nack exited 1
- attempt 10: nack given back
- attempt 11: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 12: nack the run ended with gap/missing-unit-is-a-check-finding still parked

## Where it stopped

Continued (gap/missing-unit-is-a-check-finding-continued, round 1): main (2a97eafb) merged in. Both conflicts were
resolved keeping both sides. The template's description is main's (without "SPEC §12e", which main took out of reader
text) plus the branch's no-unit clause. In tests/test_diagram_rendering.py, the branch's no-unit browser test and main's
new tests (the readers' pages, the Harris row, the caption, the three attention groups) are all kept, each with its own
server tail. Also fixed a missing space the branch had added in `OPEN = (...)` (numbers/requests.py).
Run after the merge: tests/test_missing_unit.py (5 passed), tests/test_redesign.py (22 passed),
tests/test_self_improve.py (10 passed), the no-unit browser test (passed), ruff clean.
Fails, and not because of this gap (lesson 13): main's
tests/test_diagram_rendering.py::test_needs_attention_is_three_headed_groups_in_a_fixed_order times out waiting for
/loops? off/ in #running. The page draws the three groups the test expects. But main's util.js:398, which this branch
does not touch, writes the header as "1 goal off, not running", counting modelling's goal apart as upkeep. The test's
regex and its "== 2" predate that change. I could not run the test on a clean main here (the shell refused
`git worktree add`), so this conclusion comes from reading the code and from one debug run of the page on this branch.
Not run: the full unit and browser suites and demo_check (left to the factory and the merge queue), and the :8797
check by eye.

## Where it stopped

Continued, round 2: main (52c675fe) merged in. Its one conflict, tests/test_diagram_rendering.py, came from both sides
adding tests at the same place. Both are kept: the branch's no-unit browser test first, then main's three Open all
tests and their helpers (`open_all`, `OPENED`, `LEVEL_SAID`). No code outside tests changed in this round.
Run after the merge: tests/test_missing_unit.py, tests/test_redesign.py and tests/test_self_improve.py (37 passed),
the no-unit browser test and main's test_open_all_on_a_model_that_fits_opens_every_system_as_before (2 passed, under
the watchdog), ruff clean.
Not run: main's two serial Open all tests (the-job, big), the rest of the browser files, the unit suite and demo_check
(left to the factory and the merge queue), and the :8797 check by eye.
