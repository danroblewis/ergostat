# forecast-sentence-in-words: The forecast reads as a sentence in words, with p and the run count behind a disclosure

depends-on: []

Problem (R6 piece 2): the forecast in a goal's panel reads 'off at +8m15s with p≈0.07 (100 runs)' (shots/story-1-b3-users-detail.png, story-1-b2-loop-detail.png), which leaves a product manager unable to say whether to worry. The numbers come from ergostat/numbers/review.py:550 forecast().
Change: one function (server side, so every surface shares it) turns the forecast into a sentence and a short form: 'Likely to stay within its bound for the next 8 minutes (about 9 in 10)', 'Likely to cross its bound around 14:10 (about 7 in 10)', 'Expected back within its bound by 14:25', 'No estimate: too little history'. Clock times use filed Q34's format; odds are said as 'N in 10'; the horizon is always stated. The raw p, the run count and the method sit in the sentence's title and in a closed 'How this was worked out' disclosure. The panel (ergostat/web/static/details.js, control.js) prints the sentence; the short form is what the goal row's `expected` cell will carry.
Definition of done:
1. On :8796 the users goal's panel shows a sentence with a clock time or a duration and 'N in 10', and no 'p≈' or '(100 runs)' outside the disclosure.
2. The disclosure holds p, runs and the horizon.
3. A goal with no forecast says why.
4. A unit test covers the four sentence forms and the rounding of odds.
Files: ergostat/numbers/review.py (or a small forecast_words module), ergostat/web/server.py, ergostat/web/static/details.js, control.js, tests.
Acceptance tests: the unit test; a browser check of the panel on a fixture goal with a forecast.
Budget: 70 net lines.

Milestone: r6-off-tells-the-truth. Owner items: R6 piece 2. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. The choices below were made alone; each one is the easiest to undo.

- Where the line comes from: the panel's 'off at +… with p≈… (100 runs)' is `closedloop.risk_said`, served by
  `web/numbers_api.add_to_series` (the `/api/series` answer's `risk`), not `review.py forecast()`. So the words are
  made in a new module `ergostat/numbers/forecast_words.py` (`said()`), and `numbers_api.py` adds them to each `risk`
  entry, not `server.py`. `risk_said` is unchanged and still feeds `ergostat project --risk` and `said`.
- control.js prints no forecast. The other place that does is the strip's `riskLines` in `charts.js`, and it now uses
  the same `forecastEl`. control.js is not changed.
- Q34 is not in this clone. Clock times are local `14:10` for today, `Tue 14:10` within the week, and `Nov 30 14:10`
  after that (`forecast_words.clock`). If Q34 settles on another format, only that one function changes.
- The forms: off now, and back under half the runs within the horizon, gives 'Expected back…by'. Off now and staying
  off gives a fifth form, 'Likely to stay outside its bound for the next N (about N in 10)'. On track, and reaching half
  or more at some moment, gives 'Likely to cross…around' with the peak chance. Otherwise 'Likely to stay within…for the
  next N' gives 1 minus the peak chance. Odds are rounded half up, with 'under 1 in 10' and 'over 9 in 10' at the ends.
  The short form ('within, 9 in 10', 'cross ~14:10, 7 in 10', 'back by 14:25', 'off, 8 in 10', 'no estimate') is in
  the answer. The goal row's `expected` cell is not built here: the definition says it 'will carry' the short form.
- No forecast: `/api/series` gives `no_estimate` when the loops are held or the model has no controller, and when the
  model can't be read. A goal on the projected stock with no Monte Carlo result says 'No estimate: …' (the watchdog's
  reason when it stopped). The panel prints these where it used to print nothing.
- Done item 1 asks for a check on :8796, but that server is not reachable from this container. The browser check
  `tests/test_forecast_panel.py` runs on a fixture on/off loop goal (queue-short) instead.
- Tests: `tests/test_forecast_words.py` (the five forms, the odds rounding, no estimate, clock and durations) and
  `tests/test_forecast_panel.py` (Playwright: the sentence is visible, there is no p≈ or 'runs)' in visible text, the
  disclosure is closed, the title holds p, and the opened disclosure holds p, runs, horizon and method). The
  `test_closedloop` page-API test also checks the sentence keys and `no_estimate`. Both new tests were seen to fail on
  a planted break: `round()` for the half-up rounding (3 failed), and the raw line printed beside the sentence (the
  browser test failed on 'p≈').
Overrun reason: about 74 net lines against 70, because a second surface (the strip's riskLines) prints the forecast too, and the no-estimate reasons are wired at two points in add_to_series.
