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
