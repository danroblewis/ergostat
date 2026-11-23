# frequency-refuses-noise: a frequency response from data is not drawn when the data cannot support one

Found 2026-11-23: the server computes a correct per-frequency coherence floor, but `ergostat/web/static/plots-freq.js` ignores it and uses a fixed 0.6, so unrelated noise passes. A per-frequency floor alone is also not enough: in a check, 98% of 1,024-sample noise records had some frequency above it.

See `docs/research/2026-11-23-charts/catalog.md`, item B2 and guardrail G5.

Change.
- The panel uses the server's floor, and the fixed 0.6 is removed.
- The server applies a correction across frequencies and decides, per guardrail G5, whether the record supports a response at all.
- When it does not, the panel says this data cannot support a frequency response and why, and draws no curve as if it were one.
- The default dashboard stops presenting arrivals against completions as a working Bode or Nyquist example.

Definition of done.
1. Uncorrelated input and output are refused in at least 95% of generated records, at the default settings.
2. A known first-order system with a real excitation is still drawn, with gain and phase within the stated tolerance.
3. The decision is made on the server and tested there; the page only shows it.

## Where it stopped

Built, round 1. Net code outside tests, docs and dev: +54 −23 (31 net), well inside the 600-line budget.

Missing source, and the reading taken. `docs/research/2026-11-23-charts/catalog.md` (item B2, guardrail G5) is not on
main or in this clone, so G5's exact wording could not be read. The reading taken, which is the most reversible one:
the record supports a response only if at least one frequency's coherence reaches the per-frequency floor corrected for
the number of frequencies looked at (Bonferroni: the floor at ALPHA / m, m the frequencies kept). Under unrelated
signals this bounds the chance of a false "supported" at 5% per record. If G5 asks for more (for example a minimum
count of coherent frequencies, or another correction), that is one line in `estimate` and `family_floor`.

What changed.
- `ergostat/query/frequency.py`: `family_floor(windows, frequencies)`. `estimate` sends `coherence_floor` (the corrected
  floor, which decides; it is also the floor points are marked against and phase is unwrapped against),
  `coherence_floor_each` (the old per-frequency one) and `supported`. When no frequency reaches the corrected floor (or a
  coherence is NaN), it answers `supported: false`, with `refused` (why, in words), `coherence_peak`, and empty
  frequency lists, so there is no curve to draw. This is a result, not an `error`: the other refusals (too few samples,
  a flat input) stay errors as before.
- `plots-freq.js`: the fixed 0.6 is gone. A point is unreliable under the server's `coherence_floor`, and the legend
  names that floor. Coherence with no floor sent marks every point unreliable (fails closed). Bode and Nyquist have a
  `check` that turns `supported: false` into "This data cannot support a frequency response: <why>.", and the panel
  draws nothing (the "empty" state, its message).
- `dashboard-examples.js`: arrivals to completions is no longer offered as a Bode, Nyquist or pole-zero example. When
  a goal declares a process, the three examples are that goal's model response. Otherwise there is no frequency
  example.
- `docs/SPEC.md` §4e: a bullet on frequency responses and the refusal.

Tests (done items).
1. `tests/test_query_frequency.py::test_uncorrelated_input_and_output_are_refused_in_at_least_95_percent_of_records`
   (200 seeded 1,024-sample records, default 4 segments), plus
   `test_unrelated_noise_is_refused_at_other_lengths_and_averages_too` (512/4, 2048/16, 2048/64). Seen to fail with the
   per-frequency floor put back: 1.5% refused at 1,024/4, and 17%, 4%, 45% on the others.
2. `test_a_first_order_system_with_a_real_excitation_is_still_drawn_within_tolerance`. Stated tolerance: a lag with
   tau = 20 s driven by white noise, 4,096 samples (1,024-sample stretches), default segments, output noise about an
   eighth of the output's spread, five seeds. Each record is supported, at least four frequencies up to twice the corner
   are coherent, and each coherent one there is within 1 dB and 5° of the exact response. Not reached: at 1,024 samples
   (405-sample stretches) the estimator's own bias near the corner was 7.5° on one seed. That is the Welch estimate as
   it was, not the gate, so the stated case uses the longer record.
3. Server: `tests/test_query_axes.py::test_unrelated_signals_through_the_api_are_answered_as_no_response_with_no_curve`
   and `test_an_unsupported_record_says_why_and_carries_no_curve`. Page only shows it:
   `tests/test_plot_forms.py::test_a_record_the_server_refuses_is_said_and_no_curve_is_drawn[bode|nyquist]`,
   `test_bode_marks_unreliable_points_by_the_servers_floor_not_its_own` and
   `test_coherence_with_no_floor_sent_is_all_unreliable`. The first two were seen to fail with the Bode `check` removed
   and with the 0.6 put back. Dashboard:
   `tests/test_dashboard_page.py::test_the_default_draws_no_response_from_arrivals_against_completions`.
   `test_the_default_has_a_panel_of_every_chart_family` now declares a goal, since Bode and Nyquist appear only with
   one.

Run here, one file at a time: test_query_frequency.py (24 passed), test_query_axes.py (58 passed), and under the
watchdog with Playwright test_plot_forms.py (126 passed, none skipped), test_dashboard_page.py (29 passed) and
test_panel_editor.py (33 passed). ruff is clean. Not run here, as the rules say: the whole unit suite, the four browser
files, and demo_check (no example was touched). Main has not moved since the branch began (merge-base = main), so
there was nothing to merge.
