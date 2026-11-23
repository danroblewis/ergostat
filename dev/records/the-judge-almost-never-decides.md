## Entry

section: Modelling

- **The judge almost never decides on a slow model** (owner, 2026-11-19: on the work model nearly every change is
  inconclusive, a few refused, none accepted; partly done on `slowjudge`, docs/roadmap/overnight/slowjudge.md; SPEC
  §12e): a change had to gain 2% in every window of at least twice its stock's time constant, above an absolute noise
  floor, so on a slow or noisy record each window was one noisy draw (measured: a change a fifth worse passed in 6 of
  20 records, one a fifth better failed in 11 of 20). *Done*: one replay of each over the whole record held out, the
  noise taken from the record about the better replay (AR(1), or a walk for a stock with no time constant), and a
  plug-in confidence sequence (a normal mixture, valid under that noise model) with its error
  rate stated (a change no better passes at most 5% of the time, however often looked at); an undecided change says
  about how much more record it needs and stays under test up to seven times the record it needs (a day at least); a
  change whose replay is the same as the model's waits for record in which it moves, rather than three hold-outs.
  Measured after (20 records each, a week of record): no worse change passed (0 of 60), 3 better changes failed in
  80, a drain twice off decided within a week, most changes a fifth off still undecided after one. *Done* too (on
  `the-judge-almost-never-decides`, docs/roadmap/overnight/the-judge-almost-never-decides.md): a change whose replay
  is exactly the model's, on a record that exercised a stock it touches, is judged by structural measures (the
  redesign scorecard: findings, chains, coherence, craft notes, the fit only against it; `numbers/unmoved.py`),
  a pass on structure written only by the owner. A change whose neighbourhood holds no stock is never taken as
  exercised (narrower, on purpose, than "any stock both replay"), and the scorecard of one under test is worked out
  again at each look, not cached. Measured on the slow queue (5 records each, a week, the judge every 6 hours), before
  and after: a change answering a finding passed 5 of 5 at 24 hours both ways (before by "answers a finding" on the
  record, now on structure, and no longer written by `auto`), one making a finding failed 5 of 5 at 24 hours both
  ways, one moving no measure undecided after a week both ways (that model has no items, so coherence cannot be
  measured, and it stays under test to the horizon); the share decided did not change there (10 of 20 each way),
  what it is decided on did. The no-difference case (k 0.05 → 0.0501) is still 0/0/20 inconclusive. *Left*: on a
  record as slow as the information allows (a fifth off a day-long drain) most changes still need more
  than a week; and a change should carry over edits elsewhere (above).
