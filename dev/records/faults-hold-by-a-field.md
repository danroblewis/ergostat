# faults-hold-by-a-field: failures that cluster on a field hold only that group

depends-on: [faults-healthy-pauses-the-queue]

Level 2 of the fault-isolating queue. Owner's use: to-dos on a bastion or a VPN, which fail together when that access is down, while everything else should carry on.

Change. `faults: {hold-by: [vpn]}` names item fields.

- When recent failures in a queue cluster on one value of the field (a stated, conservative rule, with its defaults documented), that value's items are **held**: not taken, and given back uncounted when they fail.
- Other values keep flowing.
- A held group is probed by retrying one item after a back-off, as a circuit breaker does (open, half-open, closed). One success releases the group.
- The hold records the field, value, evidence and when it began, for example "12 items held: vpn=prod, 5 of 5 failed since 14:02".
- An item with no value for the field is never held by this rule.

Definition of done.
1. All failures on `vpn: prod` hold that group, and `vpn: corp` items keep running.
2. A single failure holds nothing.
3. A probe's success releases the group, a probe's failure lengthens the back-off, and only one probe runs at a time.
4. Held items spend no attempts.
5. A restart of the engine keeps the holds (they are events).

Files: ergostat/leases/ (a small new module for holds), tests/test_faults_hold_by.py (new), docs/SPEC.md section 9.5.

## Where it stopped

Round 1: built. Every definition-of-done item has a passing test in tests/test_faults_hold_by.py (31 tests).
tests/test_faults_healthy.py, tests/test_leases.py and tests/test_spec_schema.py also pass with the change. Net 220
lines outside tests, docs and dev (budget 600). The unit suite and the four browser files were not run here (the
factory runs them); no page is changed.

- 1: test_all_failures_on_one_value_hold_that_group_and_others_keep_running; also
  test_an_item_with_no_value_for_the_field_is_never_held, test_a_model_without_hold_by_holds_nothing.
- 2: test_a_single_failure_holds_nothing (also one item failing again and again),
  test_failures_older_than_the_window_are_no_evidence.
- 3: test_a_probe_after_the_back_off_one_at_a_time, test_the_back_off_has_a_ceiling,
  test_a_probe_s_failure_lengthens_and_its_success_releases_in_the_engine.
- 4: test_held_items_spend_no_attempts, test_a_held_group_s_probe_that_goes_silent_expires_uncounted,
  test_a_held_group_s_failure_is_not_counted.
- 5: test_a_restart_keeps_the_holds, test_a_restart_takes_up_the_back_off_and_the_release.
- Seen to fail: with the held-group fault check taken out of `_finish` (item 4) and out of `expire`; with the take
  filter taken out (items 1, 3, 5); with the 2-item rule dropped (item 2); with the back-off not doubled (item 3); with
  more than one probe let through in a look (item 3).

Choices made with nobody to ask (the most reversible ones):

- The rule and its numbers are fixed constants in ergostat/leases/groups.py, documented in SPEC 9.5, not model keys:
  3 failures in a row on a value, of at least 2 items, within 10 min; the first probe 60 s after the hold, doubling
  on each failed probe, at most 30 min. Making them settable later adds keys; removing keys would break models.
- The 2-item minimum goes beyond the definition: one item failing all its attempts is that item's fault, not its
  group's.
- The evidence is this engine's own run ends, kept in memory. Failures from before a restart are not taken up, but
  the holds are. Ends given back uncounted for an outage of `healthy:` are not evidence, so level 1 and level 2 do
  not both hold for one outage.
- The events are `ergostat.group.held` / `.probed` / `.released` about the block, kept apart from `ergostat.queue.*`
  so level 1's take-up of its own last hold is unchanged. schema/ergostat.schema.json now takes `hold-by` (with or
  without `healthy`).
- No UI: the definition asks for none. The hold is in the record (the block's events). Showing it on the block's box
  is left for a gap of its own.
- `ergostat block NAME --now` takes whatever is held, as it does for `healthy:`.
