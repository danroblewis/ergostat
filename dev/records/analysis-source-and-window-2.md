# analysis-source-and-window-2: the analysis calls pair, psd, spectrogram and ccf, each answering one result shape from the guarded raw source
depends-on: [analysis-source-and-window-1]

## Definition of done
1. In the `analysis` source (built by analysis-source-and-window-1), a panel query can call `pair(A, B)`, `psd(A, ...)`,
   `spectrogram(A, ...)` and `ccf(A, B, ...)` on the panel's other queries. Each call reads its signals only through that
   source's raw re-read on one grid and its window ledger, never from the windowed values the panel drew.
2. `pair(A, B)` answers `points` ordered by time (x from A, y from B, `t` ascending), one point per grid time where both
   hold a value. If the signals had different windows or steps, it carries the source's G4 warning and names each window.
3. `psd(A, detrend=linear|mean|none, segments=N)` answers `points` ordered by x: period (or frequency) against Welch power,
   with a `lower`/`upper` confidence band for the number of stretches used. It reuses `query/frequency.py`'s FFT,
   resampling, detrending and gap-aware stretches; no second FFT is written. Periods shorter than 2 × max(scrape, step)
   are not answered as values and are marked not observable (G2). A spectrum asked of a signal whose raw values cannot be
   read is refused (G1), never computed on the windowed values.
4. `spectrogram(A, length=...)` answers a `table` of stretch start time × frequency → power, using the same guards as psd,
   with the number of cells bounded.
5. `ccf(A, B, most_lag=...)` answers `points` ordered by lag in seconds, with a ±band. A positive lag means B moves after A.
   SPEC says the band holds only for independent white signals; nothing claims more than that.
6. Each call refuses, with words naming the cause, a record that is too short, a signal that holds a NaN or ±inf, no
   stretch long enough between gaps, or a flat signal. A refusal never reads as zero power, zero correlation or an empty
   curve. Every count a call takes (segments, length, most_lag, cells) has a hard maximum and is refused above it.
7. SPEC's data source section and the agent guide list the four calls, their arguments, their shapes and their
   refusals. The record `dev/records/analysis-source-and-window-2.md` has the `## Entry`. Ruff is clean, and the unit
   suite and the four browser files pass after origin/main is merged in.

## Relation to other work
- analysis-source-and-window-1: waits for it. It builds the `analysis` type, the call language, the raw re-read, the ledger and the G1–G4 guards; this gap only adds calls on them.
- result-frames-and-verdicts: builds on it through -1. The refusals and warnings use its verdict and envelope.
- event-marks-and-aligned-response, bottleneck-and-operating-curve, loop-roles-and-loop-panels: these come later and use `pair`/`ccf`. Their files are avoided.
- frequency-refuses-noise (merged): `query/frequency.py`'s floor and estimate are reused unchanged in behaviour.

## Files to touch
- `ergostat/query/spectra.py` (new): psd, spectrogram, ccf and pair arithmetic, in the standard library
- `ergostat/query/frequency.py`: expose the helpers that spectra reuses, without changing their behaviour
- `ergostat/datasources/analysis.py` (new, from analysis-source-and-window-1): register the four calls, their arguments and bounds
- `docs/SPEC.md`
- `docs/AGENT-GUIDE.md`
- `dev/records/analysis-source-and-window-2.md` (new)
- `tests/test_analysis_calls.py` (new)

## Risks
- lesson-3: a short, gappy, NaN or unreadable-raw signal could come back as a flat zero spectrum or zero correlation instead of a refusal.
- lesson-4: segments, length, most_lag or spectrogram cells could be taken from the query with no ceiling, which multiplies FFT work.
- lesson-8: the ccf band, the psd band or the G2 shading could be stated wider than the code supports (for example "significant" for an autocorrelated signal).

## Acceptance tests
- `tests/test_analysis_calls.py::test_psd_finds_a_planted_period`: a 300 s sine plus noise peaks at 300 s within one frequency bin, its band holds the peak, and the shape is `points` ordered by x.
- `tests/test_analysis_calls.py::test_psd_refuses_a_windowed_signal_without_raw`: A is a `rate(...[5m])` whose raw values are unreadable; psd refuses, naming G1, and draws no curve (fails if psd falls back to the windowed values).
- `tests/test_analysis_calls.py::test_psd_marks_periods_below_twice_the_step_unobservable`: no value is answered for a period under 2 × step, and the band is marked not observable.
- `tests/test_analysis_calls.py::test_spectrogram_shows_when_a_period_starts`: a period that starts halfway has low power in the rows before and high power in the rows after; the cells are within the bound.
- `tests/test_analysis_calls.py::test_ccf_names_the_lag_and_its_sign`: B = A delayed 120 s peaks at +120 s, and swapping A and B peaks at −120 s.
- `tests/test_analysis_calls.py::test_pair_is_ordered_by_time_on_one_grid`: two series with different steps give ascending `t` on one grid and carry the G4 warning naming both windows.
- `tests/test_analysis_calls.py::test_calls_refuse_short_gappy_flat_or_nonfinite_records`: each of the four calls refuses each of these four cases with words and never answers zeros (lesson-3).
- `tests/test_analysis_calls.py::test_every_count_a_call_takes_has_a_ceiling`: segments, length, most_lag and cells above their maximum are refused with the bound named (lesson-4).

## Size budget
240 net lines
size: L (confidence: low)

## Where it stopped

Built: every item of the definition, with the eight named acceptance tests in `tests/test_analysis_calls.py`, all
passing. Nothing is left in this gap.

Choices made alone (the most reversible, each easy to change):
- The calls are registered in `ergostat/query/analysis.py`, not `ergostat/datasources/analysis.py`: the files list
  names the latter as "from analysis-source-and-window-1", but that gap built the source in `query/analysis.py`, and
  no `datasources/analysis.py` exists. The engine's `_analysis` (`query/engine.py`, not in the files list) gets the
  one branch that sends a call other than `raw` to `analysis.called`, and `_reread`, which raises a re-read's refusal
  as the call's.
- Two verdict codes are added to the closed list in `query/verdicts.py` (not in the files list): `windowed` (G1: a
  spectrum of a data source's query under a range window, or whose windows are not read) and `unanalysable` (a record
  too short, non-finite, gappy or flat). Both refuse.
- `frequency.py` exposes its helpers under public names by one alias line (`runs`, `windows`, `stretch`, `cells`,
  `detrended`, `varies`, `smooth`); nothing in it changes behaviour.
- A spectrum of a data source's query with no range window (`x`) is answered from its re-read, warned `not-raw` and
  `scrape-unknown`; one with a window, or whose language's windows are not read, is refused (G1). `pair` and `ccf` of a
  windowed source are answered from its re-read, with its `not-raw` warning.
- `psd`'s x is the period in seconds (the definition allows period or frequency). Its band is an approximate 95%
  interval per period: chi-square with `dof` = 2 × round(9/11 × stretches), the same 9/11 count of a half-overlapping
  Hann stretch as `frequency.floor`; the quantile is exact for that even dof (its closed form, bisected).
- `spectrogram`'s `length` and `ccf`'s `most_lag` are durations (`90`, `90s`, `10m`, `2h`, `1d`). Their ceilings are
  in samples (1,024 and 256), checked once the step is known. Past `cells`, the stretches are thinned evenly and warned
  `partial`; a single stretch with more frequencies than `cells` is refused.
- `ccf` also carries the G4 warning when its two signals differ in step or windows: it puts them on one grid as
  `pair` does, so the same thing is true of it.
- G2: on a raw grid the step is never under the scrape, so `2 × max(scrape, step)` is the FFT's own shortest period and
  the cut takes nothing more. It cuts more only when the scrape is the longer. The engine-level part of
  `test_psd_marks_periods_below_twice_the_step_unobservable` checks the bound and the mark; the cut itself is checked
  on `spectra.psd` with a scrape of 60 s over a 10 s grid. SPEC says so.
- A NaN or ±inf cannot reach a call through the engine today (the store and the source frames turn them into gaps).
  The refusal is tested on `spectra` directly for all four calls. The short, gappy and flat cases are tested both
  there and through `/api/query`.

Checked by breaking the code, each seen to fail and then restored: with the G1 check off,
`test_psd_refuses_a_windowed_signal_without_raw` fails (psd answered the windowed sine); with the G2 cut off,
`test_psd_marks_periods_below_twice_the_step_unobservable` fails; with the cells thinning off,
`test_spectrogram_shows_when_a_period_starts` fails (1,357 rows for 100 cells); with the ccf lag's sign flipped,
`test_ccf_names_the_lag_and_its_sign` fails; with the non-finite check off,
`test_calls_refuse_short_gappy_flat_or_nonfinite_records` fails; with the psd band ten times too narrow,
`test_psd_finds_a_planted_period`'s coverage check fails (0.68 inside).

Not measured: the time of the largest call. A ccf is at most 513 lags over at most 2,048 samples (about a million
products), a spectrogram at most 5,000 cells. Writing a timing script outside the repository was refused (the file
tools are confined to `/work`), so no number is claimed.

Tests run here: `tests/test_analysis_calls.py` (8 passed), `test_analysis_source.py`, `test_query_frequency.py`,
`test_result_frames_and_verdicts.py`, `test_query_engine.py`, `test_result_shapes.py`, `test_data_sources.py`,
`test_model_data_source.py`, `test_query_fixes.py` and `test_sql_source.py`, all passing. ruff is clean. No page
changed, so no browser file was run. Main is already merged into the branch (`git merge main`: already up to date).
The whole unit suite and the four browser files were not run here (the factory runs them).

Overrun reason: 292 lines added and 19 removed outside tests, docs and dev against the branch's base, 273 net against 240. The four calls, each with its four refusals, its bounds and its words naming them, the G1, G2 and G4 guards, an exact chi-square quantile in the standard library for the psd band, the common grid for two signals, and the engine's re-read of each query are each asked for and cost a few lines; the rest is docstrings.

## Entry

section: Done recently

- **The analysis calls** (analysis-source-and-window-2). Beside `raw`, the `analysis` source answers `pair(A, B)`
  (`points` in time order on one grid, the coarser step), `psd(A, detrend=, segments=)` (`points` by period: Welch
  power with an approximate 95% band per period), `spectrogram(A, length=, detrend=, cells=)` (a `table` of stretch
  start × frequency → power) and `ccf(A, B, most_lag=)` (`points` by lag in seconds, positive when B moves after A,
  with ±1.96/√n, which holds only for independent white signals). Each reads its queries only through the raw re-read,
  never the values the panel drew, and reuses `query/frequency.py`'s FFT, coarsening, detrending and stretches. A
  spectrum of a data source's query under a range window is refused (`windowed`, G1); a period under 2 × max(scrape,
  step) is never answered and is marked `not_observable_s` (G2); two signals of different steps or windows warn
  `mixed-windows` (G4). A record too short, non-finite, with no stretch of 16 samples between gaps, or flat is refused
  in words (`unanalysable`), never zeros. `segments` (64), `length` (1,024 samples), `most_lag` (256 samples) and
  `cells` (5,000) each have a ceiling, and a value past it is refused. Left: the page's batching still does not rewrite
  the ids inside an analysis text (from analysis-source-and-window-1).
