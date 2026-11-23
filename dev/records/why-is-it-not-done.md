# why-is-it-not-done: one plain answer to "why isn't this done?" for any item

The owner, 2026-11-22: "figure out what is holding up processes, figure out why certain things have not been done yet." This must work on any model, from what the model declares, with nothing about this factory in core code.

Change: `ergostat why ITEM`, `GET /api/why?item=`, the same through MCP, and a short "Why isn't this done?" block at the top of an unfinished item's page. The answer reads the item index and the model, and states:

- **Now:** its state, for how long, and whether that is unusual for its kind (against the kind's time-in-state).
- **The cause**, followed to its end rather than one hop: what it waits on, what that waits on, down to the root. A root is one of: unfinished work (an item), a person (an inbox item, who, and since when), a full pool, a gate or budget refusing runs, a dead or stale lease, a block that is failing or not running, a closed goal or intake, a parked or dead dependency, or nothing taking this state at all.
- **Next step and owner:** who or what must act, and the exact action or command.
- **Evidence:** the events or readings each claim comes from, with links. When the record cannot tell, it says so and says what is missing. It never guesses.
- A one-paragraph **plain summary** fit to paste to a stakeholder, and `--json`.

Definition of done:
1. Fixture tests for each kind of root above give the right root, owner and next step.
2. Replays of this factory's real stalls of 2026-11-22 as fixtures: a dependency chain; a queue held by a lease whose process died; every build refused by the budget guard; a gap waiting on a parked gap. Each names the true cause.
3. A cycle, a missing dependency or an unreadable field gives a clear answer rather than an error.
4. It answers in under 100 ms on a factory-size record, with no event-log scan for an item's current state.

## Where it stopped

Built in round 1: `ergostat/why/` (the walk, the blocks' causes, the words), `ergostat why ITEM [--json]`,
`GET /api/why?item=`, MCP `why`, the *Why isn't this done?* block first on an unfinished item's page, SPEC §5a and the
agent guide. Tests: `tests/test_why.py` (30) and
`tests/test_items_page.py::test_an_unfinished_items_page_says_why_it_is_not_done_at_its_top`. About 590 net lines of
code outside tests, docs and dev.

What is narrower than the definition, and the choices made with nobody to ask (each the most reversible):

- Item 2: the clone holds no record of 2026-11-22, so the four stalls are fixtures rebuilt in their shape on a
  factory-like gap kind (`test_stall_*`), not replays of the real events.
- Item 4: measured on a synthetic record of 3,000 gaps and about 12,000 events, not on the factory's own record.
- A person as a root: the model refuses a person block (or an advised one) that takes items or gates a block that
  does (`check`), so a person holds an item here only through a gated action about it awaiting the owner, or a gate
  input read by a manual sensor. Both are tested.
- `ergostat why` with no item prints how to name one and exits 1 (the read topics' fallback contract), not a list.
- A gate is analysed by its top-level product of factors (`a * b * (1 - c)`); any other expression is named whole.
- `tests/test_agents.py::test_a_rerun_is_timed_by_the_suite_that_failed` fails here with `ModuleNotFoundError:
  flakes` (imported by `dev/bin/onmain.py`): unrelated to this change, left alone.
- `tests/test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` fails here, alone
  too (a 30 s wait for the header's project switcher to list the other project). It reads the Items listing's header
  and `/api/projects`, neither of which this change touches; it was not run on main here (the checkout of main's
  files to try it was refused). The other 33 tests of the file pass.

### Round 2

The three review findings, each answered:

- A lease whose process died while an engine runs (`ergostat/why/blocks.py`, `holder`): the root's owner is now the
  running engine's watchdog (its pid), its action is to wait until the lease's expiry plus the watchdog's grace
  (`leases.terms.grace`), given as a time and as `ends`, or to give the item back by hand now, and its command is that
  give-back (`ERGOSTAT_ITEM=… ERGOSTAT_LEASE=FENCE ERGOSTAT_RUN=RUN ergostat lease --nack 'its process is gone'
  --no-count`). `ergostat run` is the command only when no engine runs. `test_dead_lease_its_process_gone` and
  `test_stall_queue_held_by_a_lease_whose_process_died` now pin the right command with the engine up and `ergostat run`
  with it down.
- A taking with no pid (no `budget:` declared): whether its process still runs is said to be unknown (root `unknown`,
  named under `missing`), never `work`. A full pool whose holders have no pid stays `pool-full` and names them under
  `missing`. The pid is read only from this lease's own taking (its run and fence), never from a refused or earlier
  one. Tests: `test_a_lease_taken_with_no_pid_says_its_process_is_not_known` (a model with no budget),
  `test_a_full_pool_whose_holder_has_no_pid_says_so`, `test_a_pid_of_another_taking_is_not_read_as_this_leases`.
  SPEC §5a's `work` now says what liveness is checked (the recorded pid running, an engine running).
- The item page (`pages.js`): `/api/why` is asked only for an unfinished item (not in its kind's final states), and
  outside the page's 304 accounting. The page redraws for it only when what it says changes (its roots' kinds, items,
  owners, actions, commands, since, paths, evidence links and times, and how many things are missing), not its time or
  durations. `tests/test_items_page.py::test_an_idle_unfinished_items_page_is_left_untouched_and_a_finished_one_never_asks_why`
  counts `patch` calls over two polls of an idle page (0) and the `/api/why` requests of a finished item's page (none).
  It counts from the second poll on: on this page the first poll after the first draw redraws once anyway, because
  one of the page's other answers (items, messages or actions) differs from the first. That is outside this gap.

Lesson 9, each broken by hand and seen to fail: fetching why through the page's answers again (2 patches on the idle
page); asking why for a finished item (two requests seen); reading the pid without the run and fence match (1 test
fails); letting a pid-less lease fall through to `work` (3 tests fail).

Tests run in round 2: `tests/test_why.py` (33 pass); `tests/test_items_page.py` whole: 34 pass, and
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` fails as in round 1 (the project switcher's
30 s wait), which is unrelated as said above; ruff clean. `main` has not moved since the clone, so there is nothing to
merge in.

Overrun reason: about 630 net lines of code against 600, because the three blocking fixes of round 1's review (a liveness that is not recorded said as unknown, the running engine's watchdog and the by-hand give-back as the lease's next step, and the page redrawing only when the answer's content changes) add about 40 lines to the 590 of round 1.
