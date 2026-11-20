# The redesign benchmark

How we know whether a change to the redesigner (SPEC §12e, *Redesign*) makes it better at finding the structure a
model lacks. Models whose structure is known each have one piece cut out; the record is made from the whole model;
the redesigner is asked to repair the cut one; each case is scored.

## Running it

```sh
# the harness alone, no AI (what CI runs, tests/test_redesign_bench.py)
uv run python scripts/redesign_bench.py --stand-in --results -

# on haiku, every case, at most $3 for the run, labelled for comparison
uv run python scripts/redesign_bench.py --label "my change" [--repeat 2] [--cases capacity,rework]
```

On this machine, run it through the shared slot and the watchdog like any suite:
`suite-slot.sh uv run python scripts/suite_watch.py -- uv run python scripts/redesign_bench.py ...`.

Options: `--model` (haiku), `--cap` (dollars for the whole run, 3: no case starts once it is spent; a call already
started may overshoot by its own cost), `--budget` (dollars a case, the redesigner's 0.5), `--rounds` (3), `--repeat`
(each case this many times: haiku's answers vary, so one run of six cases says little), `--hours` (record made from
the whole model, 12), `--without memory,interventions` (left out of the prompt: an ablation), `--work` (where the models and records are made), `--results` (the JSON-lines file, `-` for
none).

## The cases

`tests/redesign_cases/cases.json`; a truth is a model there or a recovery-benchmark case (`bench:ID`,
`ergostat/bench/cases/`), the record its replay read every minute with 2% noise (`bench/truth.py`).

| Case | Truth | The cut | Found when |
|---|---|---|---|
| `capacity` | a ticket queue (ticket-factory's making step) started at `MIN(rate × waiting, capacity)` | the capacity | an outflow of `waiting` has a `MIN` that binds on the record (the flow differs from each of its arguments alone by more than 5%) |
| `rework` | ladder 012: a → b, with rework b → a | the rework flow | a flow from b to a that moves at least 1% of b an hour |
| `delay` | ladder 063: a DELAY3 supply line into b | the delay | a DELAY or SMOOTH into b of what leaves a, or a stock between a and b, each flow moving |
| `goal` | ladder 011: orders = base − k × inventory | the goal gap (orders constant) | a flow into p that reads stock i and falls when i is higher (the gap closes) |
| `merged` | ladder 004: a → b → c | stock b merged away | a stock between a and c (or a delay of what leaves a, into c), each flow moving |
| `outflow` | ladder 003: a → b → out | b's outflow | a flow out of b that moves at least 1% of b an hour |

Found is judged by structure and on the record: the stocks' places and the equations' shapes, never the names chosen
(a renamed stock is followed by its `formerly:`), and each part replayed on the truth's record (every part the truth
measured taken as it was, a new stock integrated) to see that it works as the expectation says. **Found is necessary
for a repair, not sufficient**: the fit and the parts it added say the rest.

Each case also seeds the record with one past redesign turned away (failed or dismissed, with its reason) and one
recurring intervention with a person's note, the same for every run, so the redesigner's memory and its interventions
(SPEC §12e) have something to read. The notes say what a person would see on the charts ("b's count climbs for the
first hours, then stays flat although a keeps feeding it"); some, and some of the owner's reasons for turning a past
redesign away ("a level that settles whatever it starts from"), still point at the structure more directly than most
real notes would.

## The scores

Per case: **found**; **extra parts** (the parts its change set adds beyond what the known repair adds, a template it
uses counted once); **compiles** (its best change set compiled); **verdict** (the scorecard's); **fit before → after
(truth)**, the scorecard's scaled error of the replay, the truth's beside it as the floor; **cost** (dollars, calls,
seconds). The table is printed; one JSON row a case (with the label, the commit, the model, the settings and the
change set's edits, so a run can be scored again) is appended to `docs/redesign-bench.jsonl`.

The scorecard's verdict counts structure (findings, chains, coherence), not the fit: a repair that brings the fit
down to the truth's can still be "no better" (the stand-in's repairs are, on four cases of six).

## Results (2026-11-20, haiku, each case 4 times, commit c9676c6)

The ablation, with the found test above and the notes as they are now:

| Case | Neither | Memory only | Interventions only | Both |
|---|---|---|---|---|
| capacity | 1/4 (+19) | 2/4 (+9) | 1/4 (+16) | 4/4 (+6) |
| rework | 0/4 (+7) | 0/4 (+3) | 1/4 (+3) | 0/4 (+1) |
| delay | 0/4 (+8) | 3/4 (+14) | 3/4 (+11) | 4/4 (+13) |
| goal | 0/4 (+26) | 3/4 (+10) | 4/4 (+21) | 1/4 (+23) |
| merged | 0/4 (+0) | 0/4 (+0) | 3/4 (+15) | 4/4 (+7) |
| outflow | 4/4 (+6) | 4/4 (+4) | 4/4 (+4) | 4/4 (+5) |
| **all** | **5/24, fit better 13/24, $0.27** | **12/24, 17/24, $0.28** | **16/24, 13/24, $0.31** | **17/24, 10/24, $0.31** |

Found per case, with the extra parts its four change sets added together in brackets; every change set compiled in
every arm. "Neither" is the redesigner with the guide as it is now and no memory or interventions in its prompt.

- **Both help, interventions more**: 5 of 24 found with neither, 12 with the memory alone, 16 with the interventions
  alone, 17 with both. The two overlap (both carry notes about the same symptom), so they do not add up.
- **Case by case the noise is large**: goal is 4 of 4 with the interventions alone and 1 of 4 with both; four runs
  a case cannot tell such differences apart. Rework is hardly ever found: its note, rewritten as a symptom, no longer
  leads haiku to the loop.
- **Found is not fit.** The fit improved in fewer runs with both (10) than with neither (13): the right structure
  with first-guess parameters, or a new middle stock with no reading for the replay to start it from (delay and
  merged: 0.48, 0.50 against 0.007 and 0.0016 cut), replays worse than the cut model with its fitted numbers. Not
  yet looked into further.
- **Extra parts are many**: 40 to 70 over 24 change sets in every arm. Over the four arms' 96 change sets, the
  parts added are mostly parameters (105; the known repairs add one each), then flows (29) and stocks (16), and only
  5 goals or blocks; 90 file edits add a `uses:` line (the modelling loop, counted once each).

**Earlier runs** (in the results file, kept, not comparable): `before`, `after: memory and interventions` and `after
v2` (commits f5a91a5 to fc2322a) were scored with a looser found (any MIN, any delay, any flow, any reference) and with
three notes that named the repair; they read 4/24, 14/24 and 20/24. The generic remedies of the interventions loop
were taken out of the prompt between v1 and v2 (with them, haiku added a goal and a controller for every intervention,
and its change sets stopped compiling). The `v3` rows (860955b, d5648ba) are wrong: found could not replay a change
set that added the modelling loop, and scored it not found.

The rows are in `docs/redesign-bench.jsonl` (label, commit, every score, the cost, and from c9676c6 the edits).
