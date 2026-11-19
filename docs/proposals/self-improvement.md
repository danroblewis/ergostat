# Self-improvement: the modelling subsystem improves the model

Status: built on `selfimprove`, 2026-11-18; verified 2026-11-19 (*Results*). The owner's direction: ergostat's own `modelling` subsystem improves models;
there is no separate review agent; if modelling works, the examples improve themselves, and verifying modelling is the
test. This page says what was built, and what running every example with it on showed.

## What was built

**Everything `check` finds is work for modelling** (`ergostat/numbers/requests.py`, SPEC §12e *Requests*). Findings,
chain findings, craft notes and (once there is record) coherence mismatches each become a request, an item of the
built-in kind `ergostat.model-request` (open, proposed, held, answered), with what it is about, why (check's words),
where, its source and the tier that answers it first. A fit that cannot be worked out is a request too (`fit-unknown`,
saying why: no stock read, no flow moving the stocks read, too little record), so a model with no equations, the one
that most needs improving, wakes modelling whatever its fit says. The collector is the sensor of the template's
`requests-raised`; the requests are counted (`unanswered-requests`) and held at 0 by the goal `requests-handled`.

**The craft in `check`, as notes** (`ergostat/spec/craft.py`, SPEC §12 *The craft*): a part with no description, a
stock with no unit, a flow between stocks with no equation, an undescribed collector, event types in mixed forms, a
takes queue's goal with a tolerance (or a setpoint above 0) that stops its block running, a process nobody identified.
Notes are listed after the findings, grouped by code, never counted as findings.

**A tiered improver**, each tier an ordinary block of `use: modelling`, the cheapest first:

- **rule tier** (`rules`, a program, on by default; `ergostat/numbers/rules.py`): the chain's exact rewiring (the whole
  kind at once when its stocks are in pieces), the structure tests' own fixes, units carried along flows from the
  stocks they join (or the plural of the kind a stock counts), a first-order outflow with its time from Little's law
  for a flow between stocks that names no other cause, event types named `KIND.STATE` (the old names kept as
  `formerly:` so the record still folds, and written into the project's programs where they are quoted literals), a
  queue's goal held at 0, a guessed process taken out, and an equation that makes an unmeasurable fit measurable.
  Each change cites every request it answers;
- **AI tier** (`modeller`, an `ai` block, only with `ai: true`, haiku by default; `ergostat/numbers/modeller.py`):
  the requests the rule tier hands on, eight at a time, each with its neighbourhood as written and the first lines of
  the programs it runs, and a prompt that is the skill and the two guides made short
  (`library/templates/modelling/modeller.md`, about 820 words; a prompt with eight requests and their neighbourhood is about 12,000 characters). Each answer is tried as `try_change` tries it, and
  what would be turned away goes back once with why. Its cost is recorded on the requests.

**Change classes, the gate and the judge.** `description`, `unit` and `rename` join `parameter`, `equation`,
`structure`, `measurement` and `control`, decided by what the edit does (`improve.kind_of`). A change of words skips the
replay and is judged by `check` alone (passed when it makes no new finding or note); values, equations and structure are
judged on the record as before; control and measurement wait for the owner. `accept:` promotes a class (`accept:
{description: auto}`); a rewired chain or a removal waits for the owner whatever the policy. Words are written as many
a pass as have passed; a change written moves the lines of those waiting, and a description or unit waiting survives a
change to the model when its edit still applies. A **rename** of a part updates every reference, says `formerly:` its
old name, and on Accept its sensors' readings are written again under the new series (the old series stays: the
record is never edited). Edits may be given as `{"part": "stock.x", "set": {...}}` and `{"add": SECTION, "name", "set"}`.

**Never silent.** `ergostat status` and the Model page say, in one line, what modelling is doing or waiting for: the
fit (holding, off, or unknown and why), the requests (open, with a change waiting, held), when the rule tier last ran,
how many are held for an AI tier that is off, and how many changes wait for the owner.

**Every example uses it** (`uses: {modelling: {use: modelling}}`; the three that had it keep their own parameters). The
template's defaults are unchanged for those who had it: the free stand-in improver, nothing accepted automatically,
and the AI tier off.

## Results

Run 2026-11-19 on the branch rebased onto main, all on haiku; costs are what Claude Code reported.

**Every example** (`scripts/self_improve_runs.py --seconds 240 --model haiku --approve --parallel 3`): each on a
scratch copy for 4 minutes on its stand-ins, the rule tier every 20 s, the AI tier every 90 s, the test policy
(parameters, descriptions, units and equations written when the judge passes them), and the owner's approval
simulated for the rule tier's structure, renames and goals. Findings and notes are `check`'s, before → after.
"Rule" and "AI" count what each tier proposed; "written" is what reached the model.

| Example | Findings | Craft notes | Requests | Rule tier proposed | AI tier proposed | Written | Cost |
|---|---|---|---|---|---|---|---|
| alert-triage | 1 → 1 | 0 → 0 | 1 (fit-unknown) | 0 | 0 | 0 | $0.003 |
| backups | 1 → 1 | 9 → 0 | 10 | 1 equation (failed) | 9 descriptions | 9 descriptions | $0.006 |
| big | 7 → 7 | 174 → 154 | 181 | 24 equations (15 failed, 5 superseded, 4 testing) | 19 descriptions, 3 units | 17 descriptions, 3 units | $0.012 |
| coordinator | 0 → 0 | 37 → 15 | 38 | 10 equations (6 failed, 4 testing) | 24 descriptions | 22 descriptions | $0.016 |
| deps | 2 → 2 | 12 → 1 | 14 | 2 equations (1 failed) | 11 descriptions | 11 descriptions | $0.008 |
| disk-space | 1 → 1 | 4 → 0 | 5 | 1 equation (passed, written) | 4 descriptions | 1 equation, 4 descriptions | $0.003 |
| docs-fresh | 3 → 3 | 10 → 2 | 13 | 1 equation (testing) | 9 descriptions, 1 control (waits) | 8 descriptions | $0.011 |
| file-queue | 2 → 2 | 10 → 1 | 12 | 2 equations (failed) | 9 descriptions | 9 descriptions | $0.007 |
| first-loop | 2 → 2 | 7 → 1 | 9 | 1 equation (failed) | 7 descriptions | 6 descriptions | $0.006 |
| git-hygiene | 2 → 2 | 10 → 1 | 12 | 2 equations (failed) | 9 descriptions | 9 descriptions | $0.008 |
| image-squeeze | 4 → 4 | 71 → 57 | 75 | 6 equations (3 failed) | 21 descriptions (2 refused) | 14 descriptions | $0.015 |
| ops | 2 → 2 | 24 → 3 | 26 | 1 equation (failed) | 22 descriptions | 21 descriptions | $0.012 |
| plain-crontab | 5 → 5 | 14 → 2 | 19 | 1 equation (failed) | 14 descriptions | 12 descriptions | $0.011 |
| roadmap | 3 → 4 | 6 → 2 | 9 | 2 equations (failed) | 4 descriptions | 4 descriptions | $0.009 |
| small-requests | 6 → 6 | 0 → 0 | 1 (fit-unknown, held) | 0 | 0 | 0 | $0.005 |
| software-factory | 2 → 2 | 35 → 14 | 38 | 3 equations (1 passed, written) | 20 descriptions, 1 control, 1 structure | 1 equation, 20 descriptions | $0.013 |
| talking-scripts | 6 → 6 | 19 → 4 | 25 | 1 equation (failed) | 16 descriptions | 15 descriptions | $0.012 |
| the-job | 1 → 2 | 96 → 81 | 98 | 17 equations (7 failed, 8 superseded, 1 written), 1 goal | 16 descriptions (2 refused) | 1 equation, 13 descriptions; the goal by the owner | $0.015 |
| this-mac | 1 → 1 | 13 → 0 | 14 | 1 equation (testing) | 13 descriptions | 13 descriptions | $0.007 |
| ticket-factory | 2 → 2 | 34 → 31 | 36 | 1 rename (event types, the owner's) | 7 descriptions, 1 rename | 3 descriptions; the rename by the owner | $0.004 |

Every example ran with `use: modelling`; none was stopped by the watchdog (peak 66 threads, 0.93 GB). The AI tier
over all twenty cost **$0.18**. What it shows:

- **The craft notes are answered**: 585 notes before, 369 after (to 0 in backups, disk-space and this-mac; most others to 1–4),
  nearly all by the AI tier's descriptions, which `check` judges and the policy writes at once.
- **The findings are not.** No example ended with fewer findings. The rule tier's first-order equations were failed
  by the judge or still under test in all but three examples (disk-space, software-factory and the-job each got one
  written): four minutes of record is short of their time constants, and a guessed outflow is seldom better in every
  window. The findings left are mostly `template-stand-in` (the examples run on stand-ins) and
  `acting-on-its-own` / `missing-feedback`, which no tier answers mechanically. This is what `redesign` was built for.
- **What got worse was the record, not a change.** roadmap (3 → 4 findings, 0 → 2 coherence mismatches) and the-job
  (1 → 2) wrote only descriptions, one first-order equation and a goal; the new findings (`move-without-flow`,
  `rework-without-flow`, `chain-skipped`) are moves the longer record showed that the model has no flow for.
- **A model with no equations wakes modelling**: alert-triage and small-requests raised only `fit-unknown`; the
  request was answered (alert-triage) or held for the AI tier with nothing it could do in 4 minutes (small-requests).
- **Changes nobody asked for wait**: the AI tier's control and structure proposals (docs-fresh, software-factory)
  waited for the owner; the rule tier's renames and goal were written only by the simulated owner.

**The planted cases** (`scripts/craft_bench.py`; defects planted in alert-triage, ticket-factory's
chain broken, and the owner's thirteen disconnected stocks):

| Case | Defect | Rule tier only | With the AI tier (haiku) |
|---|---|---|---|
| alert-triage-craft | unit removed | fixed | fixed |
| alert-triage-craft | equation removed | fixed | fixed |
| alert-triage-craft | chain broken | fixed | fixed |
| alert-triage-craft | event misnamed | fixed (owner) | fixed (owner) |
| alert-triage-craft | description removed | not proposed | fixed |
| alert-triage-craft | collector undescribed | not proposed | fixed |
| ticket-factory-chain | chain broken | fixed (owner) | fixed (owner) |
| thirteen-stocks | state stocks disconnected | fixed (owner) | fixed (owner) |

Every defect was visible to `check` and held as a request. The rule tier alone fixed 6 of 8 (the two it cannot are
words, by design); with the AI tier 8 of 8, for $0.052 (alert-triage $0.013, ticket-factory $0.034, thirteen $0.006).
One piece of damage in both arms: alert-triage-craft ends with `extreme-conditions@stock.alerts-investigating`, from a
first-order outflow the simulated owner accepted. The whole verification cost $0.23.

Two fixes came from checking the examples' pages afterwards (`scripts/demo_check.py`): the tiers' changes are now
recorded and checked in the tier's own process rather than printed as propose lines for the engine to check (checking
one runs the model it leaves through `check`, 8–16 s on image-squeeze, which in the engine's process held the page up
for as long), and a change is searched for findings once, not twice. A rerun of backups, disk-space and ticket-factory
after them made and wrote the same kinds of change (rule 1, AI 9 / 4 / 15; $0.019).

## What still needs the owner

- Whether the rule tier's first-order outflows should wait for the owner (as a structure change does) rather than be
  judged on a record usually too short for them: in the runs they were mostly failed, and the one the bench's owner
  accepted raised an extreme-conditions finding.
- Findings that need a design change (`acting-on-its-own`, `missing-feedback`, moves with no flow) are left to
  `redesign`, which lands on top of this branch.
