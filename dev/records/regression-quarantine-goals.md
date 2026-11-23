# regression-quarantine-goals: The quarantine as a stock that must not grow, and the age of its oldest test as a measure

depends-on: [regression-guarantees-model]

Problem: the quarantine is a file only a reviewer reads, 'added and released by hand' (tests/quarantine.txt:1-3); it holds eight tests today, the oldest from 2026-11-21, and nothing says it is growing or stale (regression-guarantees.md sections 3, 4). It needs only what is on main: the list with its `when` column and fac.quarantine (dev/bin/fac.py:566-571), both from the merged quarantine-list-honest; it does not wait for flake-quarantine-continued. A goal that is off from its first reading would hold the coordinator's commander on for good, so the setpoint comes from the evidence. Change: new dev/bin/held.py reads the list on the pushed main and cross-checks it with the flake items marked quarantined. `held.py quarantined` gives the number listed; `held.py quarantine-oldest-days` the age of the oldest `when`. A list or date that cannot be read gives no value; a listed test with no quarantined flake item, or the reverse, is named on stderr. dev/model/guarantees-quarantine.yaml: stock quarantined; parameter quarantine-most, set to the count on main the day this is built (8 at filing; the implementor reads it and says the number in the record; the owner lowers it as tests are released); goal quarantine-small (<= quarantine-most, on-stale off), which holds on its first reading and goes off only when the quarantine grows, unserved until regression-guarantees-wired; auxiliary quarantine-oldest-days with no goal yet. Asked of the owner in the record in one sentence and not built: how many days a test may stay quarantined; a goal on the age is added only with that answer and only once the oldest test is under it. Done: count and oldest age match the list on a fixture; unreadable gives no value; mismatches are named; quarantine-small holds on main as it is and is off with one test added; check has no errors and no goal on the age. Files: dev/bin/held.py, dev/model/guarantees-quarantine.yaml, dev/README.md, tests/test_factory.py (four tests). Budget: 60 net lines.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1 (2026-11-23). The count on main the day this was built: **8** (tests/quarantine.txt, eight listed
lines; the two `# Released:` lines are not counted). quarantine-most is 8, and the oldest `when` is 2026-11-21.

Choices made with no one to ask, each the most reversible:

- **The goal's setpoint is written as the number 8, not as the name quarantine-most.** A goal's `hold` is a literal
  (ergostat/spec/ir.py `Setpoint.parse`: an operator and a number), so `<= quarantine-most` does not parse. The
  parameter quarantine-most holds 8, the goal says `hold: "<= 8"  # quarantine-most`, and
  `test_quarantine_small_holds_on_main_and_is_off_with_one_test_added` fails if the two differ. The owner lowers both
  together. The other way, a block setting the setpoint from the parameter (a cascade), would put a block in the loop
  before regression-guarantees-wired.
- **held.py reads `refs/remotes/<remote>/<base>` in the checkout as it is and never fetches.** It is a sensor that
  only reads. mend.py and the upgrader fetch. Not using fac.quarantine is on purpose: that function reads an unreadable
  ref as an empty list (every test blocks, which is right for the suites), and here that would read as 0 (lesson 3).
- **quarantine-oldest-days with nothing listed gives no value.** There is no oldest test. `quarantined` gives 0 then.
- **When the flake record cannot be read, the reading is still given and the failure is said on stderr.** The count is
  the list's, and the cross-check only reports.
- **Sensor periods:** quarantined every 10m, the age every 1h, each with a 1m timeout.

Asked of the owner, not built: how many days may a test stay quarantined before a goal on quarantine-oldest-days goes
off? Today the oldest has been there 2 days. A goal on the age is added only with that answer, and only once the oldest
test is under it.

Tests (tests/test_factory.py): `test_held_counts_the_quarantine_and_the_age_of_its_oldest_test`,
`test_held_gives_no_value_for_a_list_or_date_it_cannot_read`,
`test_held_names_a_listed_test_with_no_quarantined_flake_and_the_reverse`,
`test_quarantine_small_holds_on_main_and_is_off_with_one_test_added`. Each was seen to fail on a break:
- a date that cannot be read taken as today: the no-value test failed;
- the reverse cross-check dropped: the mismatch test failed;
- the goal's hold set to 9: the main test failed.

The whole of tests/test_factory.py, run serially: 213 passed and 2 skipped, rc 0. Both skips are at lines 2115 and
2370 and need Docker and the agent image, which this container lacks. They have nothing to do with this change.

Not run: `ergostat check ergostat.yaml` from the shell was refused in this session. The check is still made, through
`ergostat.spec.read` in the fourth test, which asserts no errors. Its warnings on the new parts were not read. An
unserved goal is expected to draw a missing-feedback warning until regression-guarantees-wired.

Overrun reason: 94 new lines in dev/ against a budget of 60, but most of the extra is not code. Of held.py's 61 lines,
22 are docstrings and blank lines. Of the YAML's 33, 10 are its header comment and blank lines. That leaves 62 lines
of code and model, 2 over. They are the `git:` defaults read with `.get`: a config without a `[git]` table reads
origin/main, as dev/factory.toml sets it, and does not crash.

## Where it stopped

Answering `ergostat check`'s four new findings (implementor, 2026-11-23). The definition has no `allows-findings`
line, and it was not edited. All four are fixed in dev/model/guarantees-quarantine.yaml:
- `stock-without-flows stock.quarantined`: two flows, the house pattern for a stock read whole (complexity.yaml).
  `quarantine-added` is the stock's rises over a day and `quarantine-released` its falls.
- `parameter-unused parameter.quarantine-most`: `quarantine-released` has the equation
  `MAX(quarantined - quarantine-most, 0) / quarantine-release-time`. Only the excess over the setpoint drains.
  `quarantine-release-time` (7d, estimate) is a guess used only for projecting, and no block reads it.
- `missing-feedback goal.quarantine-small`: the person block `release-quarantined` (agent coordinator, inside the
  system as `fix-main` is) reads `goal.quarantine-small.off` and moves `quarantine-released`. Loop: `quarantine-release`.
  This replaces "unserved until regression-guarantees-wired" in the definition: off, the goal now asks the
  coordinator. That is the reversible choice, since the goal holds on main as it is (8 <= 8), so nothing is asked
  until the quarantine grows. Deleting the block brings back only the finding.
- `auxiliary-without-causes auxiliary.quarantine-oldest-days`: `driven-by: [-flow.quarantine-released]`. A release
  is what lowers the age. Otherwise it rises with time.
- Pinned in `test_quarantine_small_holds_on_main_and_is_off_with_one_test_added`: no finding about any of the
  quarantine's parts. I took the equation out and the test failed on `parameter-unused`. I put it back and it passed.
- `uv run ergostat check ergostat.yaml` from the shell was refused again. The findings were read through
  `ergostat.spec.read`, which runs the same findings as check except the record's calibration and late checks.
- Run: that test (1 passed), ruff (clean). The other three held.py tests were not run again, since held.py did not change.

Overrun reason: the four check findings needed two flows, a parameter, a block and a loop in the model (about 30 more YAML lines in dev/), on top of the 94 explained above; no Python changed.
