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
