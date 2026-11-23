# Goal vocabulary and the headline: designer's notes (2026-11-22)

Cluster: the owner's two decisions: (a) "goal", not "loop", wherever the UI means what is held or off; the Loops
page becomes Goals; "feedback loop" and "control loop" stay for the structures. (b) The modelling system's own
goals come out of the headline and are shown beside it.

## What a user sees today

Screenshots (DESIGN/shots/): plan-goalvocab-8791-loops.png, plan-goalvocab-8791-diagram.png,
plan-goalvocab-8797-loops.png, plan-goalvocab-8792-blocks.png, plan-goalvocab-8792-phone-home.png.

- ticket-factory (:8791): the header says **"2 loops off"** in red. Both are modelling's (`requests-handled`,
  `model-fits`); all 14 of the factory's own goals hold. The Loops page lists those two first, in red. The side
  list says "loop requests-handled ... excess 36". So the first lesson is "your system is failing" when it is not.
- the-job on a phone (:8792, `/` redirects to `/loops`): the first screen is "2 loops off", and the two red rows
  are again modelling's; the job's own goals hold (one "open").
- software-factory (:8796) and big (:8797): same pattern ("2 off", "1 loop off, 1 unknown": all modelling).
  The switcher repeats it ("software-factory (2 off)").
- In Blocks (:8792) the side list heading is "Loops 25" over rows with holding/off; the goal panel's kind line
  is "Loop" or "Open loop"; details.js defines `loop` as "Feedback loop: a goal on a stock and what serves it",
  which is exactly the conflation the owner is objecting to. In Dynamics the same view also has a "Feedback loops
  49" list of R/B loops, so one screen uses "loop" for two different things.
- The live factory (:8798): GET /api/status and /api/loops each timed out at 60s on the first try and the
  server refused connections a few minutes later (owner item 2; not this cluster, recorded for that designer).

## Where "loop" means a goal today (to change)

UI (ergostat/web/static): index.html nav "Loops" `/loops`; util.js `UI_PAGES`, route table, headline
`${off} loop(s) off` (util.js:374), `statusEl` comment; main.js:53 phone redirect to `/loops`; split.js
OTHER_PAGES; pages.js `pageLoops` (h1 "Loops", column "loop", tooltip "the loop spent off"); diagram.js:1362
"N more on Loops and Model", diagram.js:1382 Blocks side list "Loops N" / "No loops in view."; details.js:141
panel kind "Loop"/"Open loop", WHAT.loop text, "Draw this loop alone"; control.js:298/315 comments and
"The loop ${goal}" sentences (these are the goal's control loop: keep "loop", make it "the control loop of goal
X"); review.js:58 `loop ${goal}`.
Server (ergostat/web/server.py): UI_PAGES, `/api/loops`, `/api/loops/NAME`; status payload key `loops`;
snapshot.py request list. Python wording: state.py attention `"what": f"loop {name}"` and hints "loop X was off
N% of the time", dynamics.py:462. CLI: cli/system.py table "LOOP" and "no loops: a loop is a [[controller]]"
(stale), cli/status.py "LOOP", cli/running.py "LOOPS" column and "no loops". Docs: docs/vocabulary.md row
"A goal-seeking loop ... ergostat: Loop (holding, off)"; DESIGN.md (3 mentions of the Loops page, "loops off");
SPEC.md (3 Loops-page mentions); DISCIPLINES.md (1). Tests: test_graph_cli_web.py (`/loops`,
`/api/loops/disk-under-80`), test_page_polling.py (`/loops`), test_diagram_rendering.py (the Loops page's
sparkline).

## What must not change

- The record's event types `loop.off`, `loop.holding` and the `loop.*` queries (29 uses in code, tests and
  fixtures, persisted in every project's record, read by spec/watch.py and blocks). The Record may print them in
  words; the types stay.
- The spec format: `goals:` is already right; `loops:` (names for R/B feedback loops, SPEC §12a) is right;
  `open_loop` is the control term. No YAML changes, no migration.
- Internal names: `snap["loops"]`, `Model.controllers`, `model.loop()`, `Controller`, CSS classes, `data-loop`
  attributes on R/B markers. Renaming them is churn with no reader.
- Correct uses of loop: Dynamics "Feedback loops", R/B, "loop dominance"/Loops That Matter (`/api/dominance`);
  Blocks "control loop", "inner loop (cascade)", "open loop", "closed loop"; `/api/loop-control`,
  `/api/loop-scope` (the goal's control loop, analysed as such); `ergostat.model.unidentified-loops`;
  `/api/series?loops=closed|held` and "with the loops running".
- Old addresses keep working: `/loops` (redirect to `/goals`, query kept), `/api/loops` (alias), status key
  `loops` (the switcher, remotes, `--json` consumers, saved snapshots). Saved snapshot files carry their own page
  code, so they keep working unchanged.
- `ergostat loop` stays a CLI command (no new CLI: integrations, not CLI); only its words change.

## The headline: which goals are "ergostat's own"

Nothing the page receives says which system a goal is in, or that it is ergostat's own: `/api/loops` rows carry
no `system`. The code already has the predicate: `spec/ir.py once_made(spec, x)`, a part a `once` library
template made ("the template's own system and boundary, never the model's"). Four once templates exist:
`modelling`, `upkeep`, `repair`, `interventions`. Recommendation: take `modelling` (the owner named it) and
`upkeep` (ergostat's own engine) out of the headline; keep `repair` (a program of the system failing) and
`interventions` (the people's load) in it, as they are the system's own trouble. One named set in one place
(`OWN_TEMPLATES = {"modelling", "upkeep"}`), so the owner can move one with a line.

Design: the headline counts the system's goals off ("3 goals off", or "Running" when none); beside it, muted,
never red, one short part per own system with goals off: "· modelling 2 off". ticket-factory then reads
"Running · modelling 2 off". The switcher, `ergostat projects`/`ergostat` status and the Goals page use the same
numbers from the server, not a count each page makes. Unknown goals are counted apart (as Q14 says).

## Agreement and conflict with the review

- R11 (one word for each thing) is exactly decision (a); the review left it to the owner and recommended it;
  the owner has made it. No conflict.
- R2 and Q14 are decision (b). Q14 (filed) says '0 goals off · model upkeep 2'. The owner says "shown beside
  it": same design. Two refinements: name the system ("modelling 2 off", not "model upkeep 2", since upkeep is
  also a template and the owner thinks in system names), and the classification must come from the server, which
  Q14 does not say and the page cannot do today. Proposal: the new gap supersedes Q14 (same acceptance, plus the
  classification); Q13, Q16, Q42 and Q17 read the same classification.
- R1 suggests the Goals page may later fold into the system boxes. Renaming now is still right: the owner asked,
  the page exists, and the rename is cheap; whether it survives R1 is decided later by use.
- Q62 (filed) changes the Dynamics side list to "goal X" and adds "serves goal X" on R/B rows. The gap below
  changes the server's attention wording at its source (state.py), so Q62's word part becomes a no-op and its
  "serves goal" part stays. Overlap, not supersession.
- Q46 (filed): the rewrite never touches an identifier. The gap below follows it (no regex over sentences).
- Q16, Q17, Q18, Q23, Q26, Q29, Q36, Q72 all edit the Loops page or link to `/loops`. Schedule the rename early
  and alone among gaps touching pages.js/util.js/details.js, then let the others rebase; or they write `/goals`
  from the start. The `/loops` redirect keeps any link they add working either way.

## Questions for the owner (one sentence each)

1. Should `repair`'s and `interventions`' goals stay in the headline (my default: yes) while modelling's and
   upkeep's move beside it?
2. A goal whose loop cannot close shows "open" today; may it read "no feedback" (R5's word), with `open` kept as
   the API value?
