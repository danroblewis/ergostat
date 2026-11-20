# identify: existing controllers identified from the record

Branch `identify`, from main at 4a4eda3. Gap (`docs/GAPS.md`, *Identifying existing controllers*;
`docs/proposals/external-systems.md`): real systems contain controllers ergostat does not run (a Kubernetes HPA, an
autoscaler, an alert rule that pages, a vendor's rate limiter). Today an `external` block is observed only: the
closed-loop projection runs a generic stand-in for it (`numbers/blockmodels.py`), and nothing says what its law is.

## Definition of done

An `external` block may say `identify: {input: SIGNAL, output: SIGNAL}` (a stock, flow or auxiliary each; checked
at compile). ergostat reads the two signals' record (the reference window, on a grid of the output's sensor
period), and fits candidate laws from input to output, each with a pure delay searched: **on-off** (two levels,
switching on past one threshold and off past another, hysteresis their gap, a time the condition must hold, and a
minimum on and off time), **proportional** with saturation, **PI** in velocity form with a deadband, and a
**stepper** (up by k when above a for a duration, down by k' when below b for a duration, each with a cooldown, within
its range: the HPA's shape). Each law's parameters are fitted on the first three quarters of the record and judged on
the last quarter: its **skill** (one step ahead, against holding the last value) and **R²** (run free from the
held-out record's start). The law is chosen by the held-out error with a parsimony penalty (Schwarz's, per
parameter). Reported: the family, each parameter with its standard error, the fit and the delay. The chosen law
becomes the block's model in the closed-loop projection (and so in what-if and risk), in place of the generic
stand-in, said "identified, external" in the projection's words; its output, when a stock, is moved through the
block's own flow. `check`'s record findings gain `external-unidentified` (identify: written but too little record, or
no family fits, with what it needs) and `external-law-changed` (the law identified on the window's first half and its
second differ: another family, or a parameter moved by more than three combined standard errors and a fifth:
someone retuned the controller). The Blocks view writes the law in the block as built-ins are, with a small
"identified" mark; no new panel. SPEC §12d, the agent guide (how to model an existing autoscaler or alert rule) and
GAPS (done) say so. **Validation:** `~/orchestra-kube-sim` does not exist on this machine, so a synthetic record is
built from a known HPA-like stepper in a closed loop (load → utilisation → replicas) and from an on-off alert rule,
and their parameters are recovered within tolerance (the numbers, true against identified, in the report).

## Acceptance tests

- `tests/test_extlaw.py::test_each_family_is_recovered_from_a_synthetic_record` (on-off, proportional, PI, stepper; with a delay)
- `tests/test_extlaw.py::test_the_selection_picks_the_true_family`
- `tests/test_extlaw.py::test_an_hpa_like_stepper_in_a_closed_loop_is_recovered` (thresholds, step, cooldowns)
- `tests/test_extlaw.py::test_an_alert_rule_is_recovered` (threshold, hysteresis, its `for:`)
- `tests/test_extlaw.py::test_a_retuned_controller_raises_external_law_changed`
- `tests/test_extlaw.py::test_too_little_record_raises_external_unidentified`
- `tests/test_extlaw.py::test_the_closed_loop_projection_runs_the_identified_law`
- `tests/test_extlaw.py::test_the_blocks_view_writes_the_identified_law_in_the_block`
- `tests/test_extlaw.py::test_identify_is_checked_at_compile`
- the four suites, rc 0, no page test skipped; `demo_check` on coordinator and ticket-factory.

## Size budget

600 net non-test lines (outside `tests/` and `docs/`); expected about 500.

## Where it stopped

After the gate review (merge after fixes): `external-law-changed` is **not built**. Comparing the numbers fitted on
each half of the window raised it on unchanged controllers (alert 24 of 30 seeds, HPA 7 of 30), and a held-out test of
two laws against one still raised it on some unchanged seeds (counts of moves mistold are small and noisy). The finding
was dropped, as the review allowed, and recorded in GAPS; `test_a_retuned_controller_raises_external_law_changed` is
gone with it. In its place: `external-not-run` (a law identified whose output the projection cannot move), and tests for
a day of record at the sensors' own period, every seed recovering the alert and the HPA with no spurious waits, and the
no-delay bias note.
