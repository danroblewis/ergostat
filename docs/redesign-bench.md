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
the whole model, 12), `--work` (where the models and records are made), `--results` (the JSON-lines file, `-` for
none).

## The cases

`tests/redesign_cases/cases.json`; a truth is a model there or a recovery-benchmark case (`bench:ID`,
`ergostat/bench/cases/`), the record its replay read every minute with 2% noise (`bench/truth.py`).

| Case | Truth | The cut | Found when |
|---|---|---|---|
| `capacity` | a ticket queue (ticket-factory's making step) started at `MIN(rate × waiting, capacity)` | the capacity | an outflow of `waiting` uses `MIN(` |
| `rework` | ladder 012: a → b, with rework b → a | the rework flow | a flow from b to a |
| `delay` | ladder 063: a DELAY3 supply line into b | the delay | a delay into b, or a stock between a and b |
| `goal` | ladder 011: orders = base − k × inventory | the goal gap (orders constant) | a flow into p that reads stock i |
| `merged` | ladder 004: a → b → c | stock b merged away | a stock between a and c (or a delay into c) |
| `outflow` | ladder 003: a → b → out | b's outflow | a flow out of b |

Found is structural: by the stocks' places and the equations' shapes, never by the names chosen; a renamed stock is
followed by its `formerly:`. Each case also seeds the record with one past redesign turned away (failed or dismissed,
with its reason) and one recurring intervention with a person's note, the same for every run, so the redesigner's
memory and its interventions (SPEC §12e) have something to read. The notes describe symptoms, never the repair.

## The scores

Per case: **found**; **compiles** (its best change set compiled); **verdict** (the scorecard's); **fit before → after
(truth)**, the scorecard's scaled error of the replay, the truth's beside it as the floor; **cost** (dollars, calls,
seconds). The table is printed; one JSON row a case (with the label, the commit, the model and the settings) is
appended to `docs/redesign-bench.jsonl`, so runs before and after a change can be compared.

The scorecard's verdict counts structure (findings, chains, coherence), not the fit: a repair that brings the fit
down to the truth's can still be "no better" (the stand-in's repairs are, on four cases of six).

## Results (2026-11-20, haiku, each case 4 times)

| Case | Before (harness only, f5a91a5) | After v1 (memory and interventions, 985aa5a) | After v2 (no generic remedies, fc2322a) |
|---|---|---|---|
| capacity | 1/4 found, 1 compiled | 1/4 found, 1 compiled | 3/4 found, 4 compiled |
| rework | 0/4 found, 4 compiled | 4/4 found, 4 compiled | 4/4 found, 4 compiled |
| delay | 0/4 found, 4 compiled | 4/4 found, 4 compiled | 4/4 found, 4 compiled |
| goal | 0/4 found, 3 compiled | 1/4 found, 1 compiled | 2/4 found, 4 compiled |
| merged | 0/4 found, 4 compiled | 4/4 found, 4 compiled | 3/4 found, 4 compiled |
| outflow | 3/4 found, 4 compiled | 0/4 found, 0 compiled | 4/4 found, 4 compiled |
| **all** | **4/24 found, 20/24 compiled, fit better 9/24, $0.28** | **14/24, 14/24, 5/24, $0.42** | **20/24, 24/24, 10/24, $0.29** |

What it says, and what it does not:

- **Before**, with nothing but the model, its findings and the record, haiku mostly closed craft notes (descriptions,
  units): the verdicts were "better" and the structure was not found. The record alone (a fit, each stock's level)
  rarely led it to the missing piece: the outflow (a stock that grows without bound) 3 times of 4, the capacity once.
- **After v1**, the generic remedies the interventions loop gives each request ("add the missing loop: a goal and a
  controller on what it watches") led haiku to add a goal and a controller block for every intervention, mostly
  written wrong (an unquoted setpoint, a block type that does not exist, a built-in block moving a flow); one edit that
  does not compile sinks the change set, so `outflow` went from 3 of 4 to 0. The remedies were left out of the prompt
  (the cause and the people's notes stay) and the guide says a settling level is a balancing flow, goals and blocks
  only for a controller the record shows: **after v2**.
- **The gain is mostly the notes.** Each case's seeded intervention has a person's note describing the symptom ("b
  levels off on its own; something takes items out of it"), written for this benchmark. They never name the repair,
  but they are much more direct than most notes an owner writes. The benchmark measures that the redesigner reads
  and uses the evidence it is given, not how often real notes carry such evidence. Memory and interventions were not
  measured apart.
- **Found is not fit.** The delay and merged repairs have the right structure, but the fit gets worse every time
  (0.48, 0.50, against 0.007 and 0.0016 cut): not yet looked into; a new middle stock with no reading for the replay
  to start it from is the likely cause. Capacity's limit is found with its parameter at a first guess, so the fit
  moves only when the guess is near (once of three). The scorecard's verdict counts
  structure, not fit: it says "mixed" for the right delay and merged repairs.
- Four runs of six cases is a small sample: one case moving by one is 4% of the total.

The rows are in `docs/redesign-bench.jsonl` (label, commit, every score and the cost per run).
