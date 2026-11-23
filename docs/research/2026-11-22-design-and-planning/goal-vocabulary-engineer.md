# Goal vocabulary and the headline: engineer's notes (2026-11-22)

Cluster: the owner's decisions (1) "goal" for what is held or off, the Loops page becomes Goals, "feedback loop" and
"control loop" stay for the structures; (2) the modelling system's own goals leave the headline and are shown beside it.
Code read at DESIGN/ergostat main (2468c59b). Paths below are relative to that checkout.

## What is there now

The model's YAML already says `goals:` (templates, SPEC); the Python core calls them controllers (`m.controllers`,
`spec.goals`), and the snapshot keys their state `loops`. Only the reader-facing words say "loop" for a goal.

Reproduced: :8796 header reads "2 loops off" (both `requests-handled` and `model-fits`, modelling's); :8793 "6 loops off";
/loops on :8796 is h1 "Loops", first column "loop" (shots/plan-goalvocab-sf-home.png, plan-goalvocab-sf-loops.png).
All six demos have `requests-handled` off (and `model-fits` off or unknown) at all times.

### Where "loop" means a goal (reader-facing; these change)

| Place | file:line | Now |
|---|---|---|
| Nav | web/static/index.html:13 | `<a href="/loops">Loops</a>` |
| Page list (server, client, split pane) | web/server.py:35, web/static/util.js:15, web/static/split.js:26 | "loops" |
| Router | web/static/util.js:508 | `"/loops": pageLoops`; old names redirect at :510 (`/fit`, `/residuals` to `/model`): the pattern to reuse |
| Phone start | web/static/main.js:53 | `replaceRoute("/loops")` |
| Page | web/static/pages.js:20-63 | h1 "Loops", column "loop", tooltip "the loop spent off" |
| Header | web/static/util.js:364-374 | `${off} loop(s) off` over every goal with status `off` |
| Switcher | ergostat/projects.py:44-48, util.js:384-391 | counts `off` and `open` (the header counts only `off`: two definitions) |
| Side list, more | web/static/diagram.js:1362 | "N more on Loops and Model" |
| Side list, Blocks | web/static/diagram.js:1382 | heading "Loops" (filed: Q62 makes it "Control loops") |
| Goal panel | web/static/details.js:140-141 | kind "Loop" / "Open loop"; `whatIs("loop")` |
| Glossary | web/static/details.js:27 | `loop: ["Feedback loop", "a goal on a stock and what serves it..."]`: the conflation in one line |
| Legend | web/static/diagram.js:1013, web/static/export.js:67,72 | "a loop off: its lines in red", "loop holding" |
| Model page | web/static/review.js:395 | heading "Loops" over the identification table (that one is control loops: "Control loops") |
| Attention `what` | ergostat/state.py:632-655 | `"what": f"loop {name}"` (bad and warn entries) |
| Hints `says` | ergostat/state.py:524, 554, 560, 563, 589 | "loop {name} was off N% of the time..." |
| CLI summary | ergostat/cli/running.py:360-362 | "3 loops: 2 holding, 1 open" |

### Parsers of the "loop " prefix (must move with the words, or the links break)

- ergostat/dynamics.py:450-462: reads the name from `what` ("loop "/"controller ") and rewrites it.
- ergostat/cli/status.py:113: `a["what"] == f"loop {n}"` to append "items about it".
- web/static/diagram.js:1372: `/^loop (\S+)/.exec(a.says)` gives a hint its Evidence link.
- web/static/review.js:58: finds the panel heading containing `loop ${goal}`.
- ergostat/cli/status.py:118: `--system` filter splits `what` on the first space (works for any one-word prefix).

Each should read a structured field (`goal: NAME`) on the attention entry, not parse words. Then the words can change
without breaking a link again (Q46's lesson: the Dynamics wording is a find-and-replace).

### What must not change

- Event types `loop.off`, `loop.holding` (record, `on:` triggers, spec/watch.py:33-36,155, spec/triggers.py:285,
  segments.py:1003-1009, runner.py, every example README, SPEC §2339). The record is append-only: a renamed type breaks
  every existing record and every model that triggers on it.
- The YAML: `goals:` (already right) and `loops:` (SPEC:574, names for feedback loops: right).
- Wire names: `/api/loops`, `/api/loops/NAME`, the snapshot's and `/api/status`'s `loops` key, `counts.loops`,
  projects' `loops`/`off`/`unknown`. Readers: remotes (web/remote_api.py:89-90 serve another instance's goal from
  `snap["loops"]`), exported snapshots (web/snapshot.py:33,42 store answers under `loops` and `loops/NAME`; old snapshot
  files must still open), `ergostat status --json` and its scripts, tests (test_graph_cli_web.py:19,171,179,219,338,
  482; test_goal_per.py; test_closedloop.py). Renaming gives a reader nothing and breaks three contracts; SPEC says
  once that the API's `loops` are the goals' states. No `/api/goals` alias (an alias nobody reads is code to delete later).
- Names of structures, which are right: `loop-scope`, `loop-control` (a goal's control loop), `around=loop/NAME`
  (graph.py:24, draws a control loop), `causal=` and `causalLoops` (feedback loops), SD_WHAT.loop (dynamics.js:543,
  "Feedback loop", R/B: right), the Guide's frames (guide.py:166-227 say loop only of feedback and control loops: no
  change needed), localStorage `ergostat.loops` (the feedback-loop markers toggle).
- Internal identifiers: `pageLoops`, `openLoop`, `.looprow`, `data-loop`, `snap["loops"]`, `m.controllers`, `m.loop()`.
  Keeping them keeps the rename's diff small and out of the way of the filed gaps editing pages.js (Q16, Q17, Q18, Q72).
- The CLI command `ergostat loop` (agents' guides and skills call it): its output words may change, not its name.

### The headline and modelling's goals

- The predicate exists: `ergostat/spec/ir.py:336 once_made(spec, x)` is true of a part a `once` template made. Checked
  on software-factory, big and the-job: true for exactly `requests-handled` and `model-fits`. The once templates are
  modelling, upkeep, repair and interventions (library/templates/*/template.yaml, `once: true`), so on the live factory
  the index-file and repair goals would be set apart too. That is the right reading ("ergostat's own upkeep"), but the
  label must then not say "model upkeep" (question below).
- A precedent for leaving a goal out: state.py:625-629 skips a remote's goals in attention.
- The snapshot's goal entry (state.py:304-312) carries no system and no upkeep mark; the client computes the headline
  from every goal (util.js:364), and the switcher from projects.py:44-48 with a different status set. So the change is
  server first: each goal's state carries `system` (`spec.goals[n].system`, as correspond.py:48 reads it) and
  `upkeep: true` when `once_made`; projects' rows add `upkeep_off`; then the header (filed Q14) and the side list
  (filed Q42) and Loops grouping (filed Q16) read the fields instead of each guessing.
- Filed Q14 (`gap/ui-the-headline-counts-the-system-s-goals-and-the-m`) is the owner's decision 2 word for word. No new
  gap for the header itself; the quick server gap below is what Q14, Q16 and Q42 should depend on, so three gaps do not
  invent three predicates.
- Live factory: `GET :8798/api/status` did not answer in 300 s once and was reset after 110 s the second time, so on
  the large case the header (polled from it every 5 s, util.js:348) never shows a count. That is item 2's (load times),
  noted here because the headline depends on it.

## Gaps proposed

1. `goal-state-says-its-system-and-upkeep` (quick): the server fields. Enables Q14, Q16, Q42.
2. `goals-page-replaces-loops-page` (incremental): routes, nav, page, header word, panel, glossary, legends, docs.
   After Q14 (both edit util.js:374), before or beside Q16/Q17/Q72 (it keeps internal names, so their diffs still apply).
3. `attention-names-goals-as-goals` (incremental): the `what`/hint words and a structured `goal` field; parsers read
   the field. After Q46 and Q62 (both rewrite dynamics.attention and the Dynamics side list).

None is large; no proposal is needed. The open design question (keep the Goals page or fold it into the boxes, R1/R12)
stays the owner's call after R1 is in use, as the review says.

## Questions for the owner

- Set apart only modelling's goals, or every goal a `once` template made (modelling, upkeep, repair, interventions)?
  Recommended: every one, labelled "ergostat's upkeep" (not "model upkeep").
