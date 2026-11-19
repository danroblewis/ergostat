# impact: the change-management package a fix comes with, built from the model

Branch `impact`, from main (07a07c1). Asked by the owner beside the `repair` branch (a failing `run:` program becomes an
`ergostat.failure` item, an AI fixes it, it is tested, a person approves): each fix, and each change to the model, comes
with the research a careful operator expects before approving a change, worked out from the models.

## Definition of done

`ergostat/numbers/impact.py` gives `report(p, parts, since=None, …)`, the impact of a change that restores or alters
parts of the model, bounded in wall time and in runs. **Input**: a block whose runs fail (its name, `block.NAME`, or an
`ergostat.failure` item naming it), or a model change (`ergostat.model-change/ID` or its id); when the failure began,
else read from the record (the first `agent.failed` of the block's last unbroken run of failures). **What broke**: the
flows the block moves, each one's rate before the failure and since (from the record), stopped or degraded, and the
stocks building up since. **Without the fix**: the closed-loop projection (`closedloop.closed`) with the block's
identified model (identified on the record before the failure) replaced by its failing self (its flow at the share of its
rate it still moves since the failure: 0 when stopped); for each goal, when it goes off, whether it is off at the
horizon, its hours off, and its risk (`closedloop.risk`: p of being off at the horizon, expected time off). **With the fix
at time d**, for evenly spaced rollout times over the next N units of the model's time scale (days, hours or minutes, by
its slowest time constant): the same projection with the block restored from d, and the cost of waiting (goal-off
hours, the backlog's peak, the recovery time after the fix). The **ideal rollout time** minimises goal-off hours plus a
configurable penalty times how busy that hour of the day is (the record's daily pattern of the arrivals feeding the
broken part), and the reason is said in one sentence. A model change gets what it touches, its forecast as the model is
and with the change, the goals' off-time under both, and the fields; its rollout time is not worked out (a change to the
model revises the forecast, not the world: said). **Change-management fields**: what else the block touches (other
blocks reading its flows or their stocks, goals on those stocks, blocks it commands, its gated actions and their gates);
whether it is read-only (no gated actions) or writes; the rollback (revert the fix's commit; the state its items would
be in); a risk level (low, medium, high) from writes, blast radius and test results, with its reasons; the projections'
confidence from each part's identified model (assumed or identified) and each stock's fit (R², skill) on the reference
window. One sentence sums it up. **Shown** on the existing item page of an `ergostat.failure` or
`ergostat.model-change` item (no new page): the sentence, the existing line charts for the stocks without the fix and
with it at the ideal time, the cost by rollout time, each goal's probability of being off, and the fields.
`GET /api/impact?block=NAME|item=ID|change=ID[&since=T]` (worked out in a thread of its own, `{"working": true}` till
then); `ergostat impact BLOCK|CHANGE [--since] [--within] [--penalty] [--json]`. The report's shape is in SPEC §12n,
for the repair branch to call.

## Acceptance tests (`tests/test_impact.py`)

- `test_a_synthetic_failure_names_the_broken_flows_and_the_stock_building_up`
- `test_without_the_fix_the_goal_goes_off_and_with_it_now_it_recovers`
- `test_the_failure_began_is_read_from_the_record`
- `test_the_ideal_rollout_time_avoids_a_planted_busy_period`
- `test_the_report_is_bounded_in_time`
- `test_the_change_management_fields_say_what_it_touches_and_whether_it_writes`
- `test_a_model_change_gets_its_forecast_and_fields`
- `test_the_cli_prints_the_report`
- `test_the_api_answers_once_worked_out`

Validation (not run by the suite): the coordinator and ticket-factory run for a while, a block's program made to fail
mid-run (a synthetic failure window in the record), and the report checked by hand for the right broken flows and
plausible goal failures. The four suites with rc 0, no page test skipped; `demo_check` on coordinator and
ticket-factory.

## Size

**Budget 600 net lines outside `tests/` and `docs/`.**

## Where it stopped

Done, within the budget (600 net lines). Three departures from the text above, each said in SPEC §12n:

- The API's failure start is `began=T`, not `since=T`: every page request already carries `since` (the window).
- The cost of waiting counts only the goals the failure puts off (`due`: holding when it began, off longer without
  the fix than with it made now). Validation showed why: on the coordinator and the ticket-factory a restored flow puts
  downstream "<= 0" goals off, which happens whenever the fix goes in and only leaves the horizon later, so counting it
  made every report advise waiting. Goals already off when the failure began are said apart and not priced.
- What waiting loses (`moved`, the block's flows over the horizon) is said beside each rollout time but not priced;
  the owner may want it in the cost.

### After the gate review (merge after fixes)

The review found the cost empty (0h at every rollout time in both validations). Fixed: each rollout time is scored
against rolling out now over the same span (to T after it, T at least twice the recovery when fixed now), so the
goal exclusion is gone; the cost adds the outage hours, (1 − share) × the wait, so a busy hour must outweigh a real
loss; the extra goal-off counts every goal, and putting off the fix's own effects earns waiting nothing (without that,
on both demos a downstream goal the restored flow keeps off made every wait look free). Throughput lost is said. A
low-confidence report opens with its worst part, never advises waiting, and shows the model's ideal time muted;
confidence counts every model the projection runs. Also: `horizon_of` moved to `numbers/simulate.py`; the fields and the
change report in `impact_fields.py`; the API keyed on the first answer's `at`, its own five-minute store, two threads
at most, the page's polling stopped when it is left; `began` everywhere; `began` and `tests` validated; recovery needs
the stocks settled; the 500-run cap and an unmeasured rate said.

**Size: 666 net lines, over the 600 budget by 66.** The overrun is the review's own list: the equal-span scoring and
its second pass for T, the outage and throughput terms, the low-confidence path with its words, the API's store and
thread cap, and the validations it asked for, each a few lines; nothing was added beyond it.
