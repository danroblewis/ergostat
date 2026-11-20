# modelling-core2: the spot-check's fixes to automatic redesign and carrying

Branch `modelling-core2`, from main at 169690e (modelling-core merged). The spot-check of `modelling-core` found no
unapproved write path; these are its fixes forward.

## Definition of done

- The rest after a redesign is keyed on the unit's own parts (a hash of their structure), not the model's version;
  units take turns fairly (among those equally due, the one reviewed longest ago first).
- A dismissed or superseded redesign starts the rest; so does a run that never ended (crashed or timed out: only
  `started` and `call` events), which also closes its `redesign-due` request.
- The redesigner checks the daily cap before it plans; `next_due` reads the requests and changes once, and the
  redesign-run events it reads are bounded in time.
- Scope: a parameter is inside a system only if that system's parts use it; following a rename compares only
  reference fields (never sensor selectors, labels or run strings); carrying a redesign checks its scope again
  (`outside`, its parts added, taken away and changed).
- Carrying: carried words go back to `checked`; a carried redesign says `rescoring` until the judge scores it again;
  carrying happens under the proposals' lock, in the judge and in Accept, so it never reopens an item being accepted.

## Acceptance tests

`tests/test_modelling_core2.py`:

- `test_the_rest_is_keyed_on_the_units_own_parts`
- `test_units_take_turns`
- `test_dismissed_superseded_and_unfinished_runs_start_the_rest`
- `test_an_unfinished_run_closes_its_request`
- `test_the_cap_is_checked_before_planning`
- `test_next_due_reads_the_store_once`
- `test_a_parameter_is_inside_a_system_only_if_its_parts_use_it`
- `test_following_a_rename_never_touches_selectors_labels_or_run_strings`
- `test_a_carried_redesign_is_held_to_its_scope`
- `test_carried_words_go_back_to_checked_and_a_redesign_says_rescoring`
- `test_carrying_runs_under_the_lock`

and the four suites with rc 0 (fast commands under `scripts/suite_watch.py`), `demo_check` on image-squeeze,
alert-triage, ticket-factory and the-job.

## Size budget

600 net lines outside `tests/` and `docs/`; expected about 150.
