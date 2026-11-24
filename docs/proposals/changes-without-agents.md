# Changes made by programs, rules and models instead of AI sessions

Status: proposal, 2026-11-24 (`changes-without-agents-proposal`). Nothing here is built. The owner: "what if we had a
system rigorous enough that we no longer need to have the AI agents write code? ... We want to work all workers up
the ladder, and we want to decompose our workers and delegate and split."

In ergostat's words (NOTES.md) the owner's *worker* is an **agent**, and *up the ladder* is the refactor path: from the
universal AI agent (rung 1) to a narrow AI, a decision, a program, a rule, and finally no work at all (rung 6). A
**lane** below is the path a change takes to main by the rung of the agent that makes it.

The answer in one line: **the ladder is already core for repair approvals and action gates; make it general (any
block may have a cheaper candidate that runs in shadow, is replayed on the record, and is promoted on its agreement),
let model changes travel as data, and start with the one program the record shows paying at once: a resolver for
merge conflicts in files a model declares generated or union-merged.**

## What was measured, and how

The record is this factory's git history as cloned for this session (a copy; the live instance was not read). The
window is every commit dated from 2026-11-21 to the clone's last, the days the gap records (`dev/records/`) have
existed:

- **442 landed gaps**: the first-parent merges `Merge branch 'factory/NAME'` on main, each diffed against main before
  it (`git log main --first-parent --merges --since=2026-11-21 --diff-merges=first-parent --numstat`);
- **769 merges of main into a gap's branch** (`--grep=^Merge.main`), made by `dev/bin/implement.py` `merge_main`:
  a clean one is committed by the program, a conflicted one is left for the session to finish;
- **818 hand-written resolutions** in 395 of those merges: files whose combined diff (`git log --cc`) still shows a
  hunk, i.e. where the result differs from both parents. Each was classed from its combined-diff lines: a line marked
  ` +` came from the branch, `+ ` from main, `++` was written in the merge, and any `-` column dropped a parent's line.

The counts were taken with git and a text search over its output, since this session runs no scripts of its own.
Every figure below names its population; the commands are reproducible on any clone of main.

## 1. The ladder as a general core idea

**The idea.** A block's agent can be replaced by a cheaper one once the cheaper one is shown to be equivalent on the
work the block actually gets. Equivalence is evidence from the record, never a claim: replay on past items, shadow
runs on live ones, and an agreement rate with a floor of cases.

**What core already has, and reuses.** Four places do this today for one decision each:

| Where | What moves down | Rule |
|---|---|---|
| repair (SPEC §12r, `promote: true`) | the approver of a block's fixes: person, ai, program, rule | the last 10 answers at the current rung, ordered by `seq`, all approved and `ran`; any regression or denial sends it back to the owner's rung |
| actions (SPEC §12o) | a class of action, to `gate: auto` | approved 5 times or more and never denied: said to be ready; promoting is the owner's edit |
| the ladder hint (`ergostat/state.py`, `LADDER_MIN, LADDER_SHARE = 10, 0.8`) | a controller's decisions | 10 decisions or more, 80% the same: a rung lower is suggested |
| modelling (SPEC §12e) | a modelling request | a rule tier answers first and hands on what it cannot to an AI tier |

**Proposed, general, off unless declared.** A block may name a candidate: another block that takes the same items or
events, runs without its valves (`shadow`), and writes what it would have done as a `shadow.answered` event. Three
measures per candidate, each over a window and ordered by `seq`:

- **claims**: the share of the block's items the candidate answered rather than abstained on (a candidate may say
  "not mine", and must, for anything it does not recognise);
- **agreement**: of the claimed items, the share whose candidate answer equals the recorded outcome, compared as the
  block declares (`agree-on:` the item's next state, a field, the files written byte for byte, or a program that says
  same or not);
- **outcome-checked agreement**: the same, compared with what survived the gates after the block (what landed, what
  was not reverted), never with the acting agent's raw answer. The record shows why (§3): in 26 of the 39 hand
  resolutions of `docs/GAPS.md`, a generated file, the agent kept both sides' text, the splice review-lessons §7
  records; a candidate that agreed with the agent there would have agreed with a mistake.

**Bounds.** At most 3 candidates a block, refused above at `check`; each runs under its own block's `at-once`,
`timeout` and budget, and a shadow run never takes a slot or a lease from the acting agent; a candidate over its
budget stops being run and is said, never counted as agreeing.

**Replay** is the same comparison run on past items before any shadow run: the candidate is given each recorded
input (for a merge: its base, ours and theirs) and its answer is compared with the recorded outcome. It costs no
live risk and gives the first estimate of claims and agreement in minutes.

**Promotion** reuses repair's rule: the candidate becomes the block's agent for what it claims when its last N claimed
answers (by `seq`, default 10, at most 100) all agreed and the replay agreement over at least M items (default 30) is
at or above the declared floor; one disagreement after promotion sends the block back to its agent and only later
answers count again. As with `gate: auto`, ergostat **says** a candidate is ready and the promotion is the owner's
edit, unless the model declares `promote: true` as repair does. A record that cannot be read counts as no agreement.

```yaml
blocks:
  resolve-merge:                 # the acting agent (rung 1)
    type: ai
    takes: {kind: change, at: [conflicted]}
    candidates:                  # proposed; off unless declared
      merge-rules:               # another block, rung 4 or 5; runs in shadow until promoted
        agree-on: files          # byte-equal files, or: state | field NAME | program CMD
        floor: 0.95              # replay agreement needed, of at least `cases` claimed items
        cases: 30
        last: 10                 # consecutive agreements by seq, as repair's promote
        promote: owner           # or auto; owner: said ready, the owner edits
```

## 2. Changes that can become data instead of code

| Kind of change | Data in core today? | Lands in this factory as | What core needs |
|---|---|---|---|
| dashboards and panels | yes: `dashboards:` (SPEC §4f), compiled and checked, 24 panels at most | model text | nothing |
| thresholds and setpoints | yes: a goal's `hold:` and `tolerance:` | `dev/model/*.yaml`, or `times.py setpoints` rewriting a line | a model edit lane (below) |
| workflows | yes: a kind's states and their chain of stocks and flows, a block's `takes:` | model text | nothing |
| saved queries | in part: a panel's query; no named query of its own | a panel | a named `queries:` entry other parts can cite (small) |
| a measure of the record | no: each is a `sensor: {run: COMMAND}` and code in the command | `dev/model/*.yaml` plus `dev/bin/measure.py` plus a test: 16 gaps changed such a sensor line | a sensor declared as a query over the item record (`sensor: {query: ...}`), so a new measure is a line, not a program |
| a model change (structure, equations, descriptions) | yes for estimated proposals (Accept, SPEC §12b) | a gap through the implementor and the queue | the same Accept for any edit an agent or person proposes |

**The model edit lane.** A proposed change to a model that touches no program is an item of its own: its edit,
`ergostat check` on the model it leaves (8 to 16 s on the image-squeeze example, self-improvement.md), and the model's own
goals over the next window as its verification. It is applied through a valve the owner grants, so it needs no code
review and no test suite. Core has the parts (proposals, Accept, `model.changed` with its version); what is new is
letting an edit that did not come from the estimator use them.

**What the record says about the size of this lane.** Of the 442 landed gaps, 57 (13%) changed `dev/model/`, and 50
(11%) changed no program code outside `tests/` (26 of them, 6%, changed only prose: `docs/` and `*.md`). None of the
442 was a model edit alone: every gap that changed a model also changed a test or a program. So the data lane is
small in the recent work as it was cut, and grows only as measures become queries and model edits stop being filed
as gaps.

## 3. Program-made code

### 3a. Conflict resolution in generated and append-only files

The finding the record makes loudest: **395 of the 769 merges of main into a branch (51%) needed a hand-written
resolution**, 818 files in all, almost one conflicted merge per landed gap (395 for 442). By where they are:

| Files | Hand resolutions | Both sides kept, nothing written or dropped | Share |
|---|---|---|---|
| `tests/` | 231 | 103 | 45% |
| `docs/` (of which `docs/GAPS.md`) | 115 (39) | 33 (26) | 29% (67%) |
| `dev/` | 102 | 19 | 19% |
| `ergostat/` | 358 | 29 | 8% |
| other | 12 | 1 | |
| **all** | **818** | **185** | **23%** |

"Both sides kept" is a combined diff with only ` +` and `+ ` lines: the result is the branch's lines and main's lines
at that place, nothing new, nothing dropped. That is exactly what a union merge (`git merge-file --union`) makes, up
to order: a union puts the branch's lines first. In the 167 such resolutions the search could isolate with their
order, 157 (94%) have the branch's lines first and 10 have main's first.

**Two rules, each a file class a model declares:**

1. **generated**: the file is the output of a program (here `docs/GAPS.md`, which the queue renders from
   `dev/records/` on every landing, `dev/bin/gapsdoc.py`). Resolution: take main's side; the branch's intent lives in
   the source (its record), and the landing renders again. In all 39 hand resolutions of `docs/GAPS.md` the agent's
   result differs from main's (that is why they show); 26 of them kept both sides, which for a generated file is the
   splice that review-lessons §7 records six times (two Left clauses, a duplicated line, a dangling fragment).
2. **union**: both sides' added lines are kept, the branch's first; then the result must pass the same gates any
   change does (ruff catches a test defined twice; the suites run in the queue). Declared for the files where the
   record shows agents keep both: test files first (45% of their resolutions).

**Coverage, measured.** A resolver with these two rules, `docs/GAPS.md` generated and union declared for
`tests/` only, run before the session (in `merge_main`), would have finished **55 of the 395 conflicted merges (14%)**
entirely: in every test file its output is the agent's (up to the order counted above), and in `docs/GAPS.md` it is
main's, where the agent's was a splice or a hand edit of a generated file. Declaring union for every file would
finish 78 (20%), but outside `tests/` agents kept both sides in too few cases to declare it there (8% in
`ergostat/`). The other merges still need the session, with fewer files left: 103 test-file resolutions and 39
`docs/GAPS.md` ones of the 818 are the rules'. It removes a splice in `docs/GAPS.md` outright.

### Shown end to end: one recorded merge, the program's output against the agent's

Merge `dc3f5c13` (`Merge main (b9341591cb70) into the branch`; parents `08aee01c` the branch, `b9341591` main; base
`278f54a4`). `tests/test_graph_cli_web.py` conflicted: both sides had appended tests after line 453.

- the branch added 26 lines: `test_the_served_diagram_script_frames_what_is_drawn_and_its_edge_hint_names_the_way`;
- main added 33 lines: `test_a_search_or_filter_that_matches_nothing_answers_empty_and_a_match_is_counted_whole` and
  `test_the_record_answers_a_type_that_matches_nothing_with_no_events`;
- **the agent's resolution** (`git show --cc dc3f5c13`, hunk `@@@ -454,26 -454,33 +454,59 @@@`): 59 lines, the
  branch's 26 (` +`) then main's 33 (`+ `), no line written, none dropped;
- **the union rule's output**: the branch's lines then main's at the conflict, the same 59 lines in the same order.
  This is read from git's own combined diff of the three versions; running the union itself here
  (`git merge-file --union --object-id ...`) was refused in this session, so the first build gap repeats it as a test;
- **what landed**: main today has the three tests at lines 454, 480 and 495 of `tests/test_graph_cli_web.py`, in that
  order.

And the counter-case the generated rule exists for: merge `7ef0407c` (main `b20756c7`). The agent kept both sides of
`docs/GAPS.md`; its result is main's file plus 9 lines of the branch's older text for the repair entry, a second,
contradicting *Left* clause (`git diff --stat b20756c7 7ef0407c -- docs/GAPS.md`: 9 insertions). The generated rule's
output is main's file. Main's `docs/GAPS.md` today has none of those 9 lines (the landing rendered it again from the
records), so the agent's work on that file was thrown away, and the program's output is what landed.

### 3b. Codemods and templates for repeated shapes

| Shape | Seen in the 442 | A program could make |
|---|---|---|
| a gap's record and definition | 442 (every gap) | already does: `implement.py definition_first` commits it |
| tests for the definition's named acceptance tests | 415 gaps (94%) touched `tests/test_*.py` | the scaffold: one failing test per name the definition gives, in the file it names; the body stays the agent's |
| a factory measure: a sensor line in `dev/model/*.yaml`, its function in `dev/bin/measure.py`, a test | 16 gaps | the whole of it once measures are queries (§2); until then a template for the three pieces |
| a join gap (checks its sub-gaps landed) | 2 of the 7 joins changed only their record and docs | the verdict, from the sub-gaps' records |

### 3c. Generation from declarations

| Declared once | Written by hand today, in | Seen in the 442 |
|---|---|---|
| the model's keys (`schema/ergostat.schema.json`) | the compiler (`ergostat/spec/compile.py`, `ir.py`, `load.py`) and SPEC's key tables | 24 gaps changed `schema/`, 49 the compiler, 203 (46%) `docs/SPEC.md` |
| the gap entries (`dev/records/`) | `docs/GAPS.md` | generated already on landing; still 39 hand resolutions in branch merges, which the generated rule of §3a ends |
| a factory measure's description and unit | `dev/README.md` (90 gaps changed it) | the README's measure lists, rendered from `dev/model/` |

Each is a renderer with a check that the rendered text is current (as `gapsdoc.py render --check` is), never a second
copy written by hand. Which of them pays is measured first (§4), not assumed.

## 4. Mining the record for recurring change shapes

**Method.** Two passes over merged history, both reading only git:

1. **Per landed gap**: its diff against main before it, cut into a signature of path classes (prose, model, test,
   core code, interface code, factory tooling, schema) and hunk kinds (new file, append at end, edit). A shape is a
   signature that recurs at least N times in the window (N = 5 proposed). Its **coverage** is the share of gaps whose
   whole diff falls in shapes a program has been replayed against and agrees with (§1), and separately the share of
   changed lines.
2. **Per merge into a branch**: each hand resolution classed by its combined diff (both kept, branch's kept, main's
   kept, written, dropped) and by path. A resolution class a rule reproduces is covered.

**Measured on the copy (from 2026-11-21; path classes only, the hunk kinds are left to the miner, §7 gap 4):**

| What | Share |
|---|---|
| landed gaps that changed only prose | 26 of 442 (6%) |
| landed gaps that changed no program code outside tests | 50 of 442 (11%) |
| landed gaps that changed `ergostat/` Python / the interface's static files / factory tooling | 231 (52%) / 147 (33%) / 118 (27%) |
| merges of main into a branch that needed a hand resolution | 395 of 769 (51%) |
| of those, finished whole by the two declared rules of §3a (union on `tests/` only) | 55 of 395 (14%) |
| the same with union declared for every file | 78 of 395 (20%) |
| hand file resolutions a union reproduces (up to order) | 185 of 818 (23%) |

**The share, stated plainly.** Measured as whole changes, programs cover almost none of the recent work: no gap in
the window was of a shape a program reproduces end to end. The parts that recur are inside gaps: the conflicted
merge (51% of merges, a seventh of them finished by the two rules of §3a), the record (every gap, already a program's), the test file
(94% of gaps), the SPEC section (46%), the factory measure (16 gaps). The first coverage gain is in merges (14% of
conflicted merges finished, 142 of 818 hand file resolutions, 17%, taken over), which is why the build split starts there.

## 5. Routing: the cheapest agent able to do it, the AI agent as the fallback

Routing needs almost nothing new in core: a block already takes only the items its `takes:` selects, and an item's
state says who has it. The pattern, cheapest first:

1. **recognise**: each lane's block takes the items in the state before it (`at: [ready]`) whose fields its
   `where:` selects, or runs a recogniser program that answers *mine* or *not mine, because ...*;
2. **try**: the cheapest lane that claims an item makes the change and moves it on (`to: [built]`);
3. **hand on**: a lane that cannot finish, or whose result fails its gate, moves the item to the next lane's state
   (`to: [ready-for-ai]`) with why; the AI agent's block takes whatever reaches its state, and nothing is ever dropped;
4. **record**: each try is an event with its lane and outcome, so claims, hand-ons and agreement (§1) are measures
   of the record, and a lane that hands on most of what it claims is visible on its block.

The two additions core needs are small: an **abstain** outcome a block's run can give (counted per block, never a
failure), and the candidate comparison of §1, so a lane earns its place by the record. Routing by cost is then the
order of the states, declared by the model, never inferred.

In this factory the first lane sits inside the implementor: `merge_main` runs the resolver of §3a before the session;
a merge it finishes is committed by the program as a clean merge is today, and one it cannot is left for the session
with fewer files. Later lanes (a measure template, a test scaffold, a model edit) route at `ready` by the gap's
definition: its *Files to touch* all inside one declared shape.

## 6. The minimum time from request to main, per lane

From the copy: the time from a gap's definition commit (the implementor's start, `<gap>: the definition of done`) to
its landing merge, and the spacing of landings. The time before the definition (open and ready, waiting to be taken)
and the push wait are in the live record (`in-open-hours`, `in-ready-hours`, `gate-push-wait-minutes`,
dev/model/times.yaml), which this session may not read, so they are not in these numbers.

| Lane | What it waits for | Floor | Typical, from the copy |
|---|---|---|---|
| AI agent (today's lane) | a session's build, the reviewer, fix rounds, the queue | 43.5 min (`a-gap-rebuilt-in-round-after`, the fastest of the 30 gaps whose definitions were committed last, on 2026-11-23, all landed) | median 166 min over those 30 gaps (43.5 to 290 min) |
| program or rule making code | the build step, then the next queue run | one queue run, at most the shortest spacing of two landed batches: 19 min (1,125 s) | the median spacing of landed batches, 38 min (2,302 s), over the 34 spacings between the last 35 batches (2026-11-22 and 23) |
| program inside a branch (the resolver) | nothing: it runs before the session | 0 added; it takes the conflicted merge off the session | the session minutes it saves are in the live record (`gate-implementor-minutes`), not measured here |
| model edit (data) | `ergostat check` and the owner's valve | seconds: 8 to 16 s of `check` on the image-squeeze example | the owner's answer; no queue. For comparison, `model-split-oversized-systems`, a model change sent as a gap, took 3.5 h from definition to main |

A program-made change still lands only with the queue: the floor of every code lane is the queue's own run, and the
gain over the agent lane is the session, the review and the fix rounds (the medians differ by about two hours, 166
against 38 minutes; a difference of medians, not a measured saving). Only the data lane leaves the queue out.

## 7. The build split: the gaps that follow, smallest valuable first

Each general piece is in core as an option a model declares, off unless declared, naming no gap, program or factory;
this factory's choices are in its own model and `dev/` files.

1. **merge-resolve-declared-files** (about 150 net lines). Core: a program that finishes a conflicted merge in a work
   tree for the files a model declares, `files: {generated: {PATH: COMMAND}, union: [GLOB, ...]}`, leaving every
   other file conflicted and saying which. The factory: declares `docs/GAPS.md` generated (by `gapsdoc.py render`)
   and `tests/test_*.py` union, and `merge_main` calls it before leaving the merge to the session. Acceptance:
   `test_union_matches_recorded_merge` (the three versions of `dc3f5c13`, as fixtures, give the 59 lines that landed),
   `test_generated_takes_main_and_renders`, `test_undeclared_file_left_conflicted`, `test_nothing_declared_resolves_nothing`.
2. **agent-candidates-in-shadow** (about 250). Core: a block's `candidates:` run without valves, `shadow.answered`
   events, claims and agreement as measures on the block, and replay over recorded items. Acceptance includes the
   resolver of gap 1 replayed on recorded merges as its first candidate.
3. **ladder-promotion-general** (about 150). Core: repair's promotion rule lifted to any block with a candidate:
   ready said by ergostat, promoted by the owner's edit or `promote: auto`, sent back on one disagreement.
4. **change-shapes-measure** (factory, `dev/`). The counts of §4 as sensors in `dev/model/`, read weekly, so the
   share programs cover is a measure with a goal rather than this page's one reading.
5. **measures-as-queries** (core, about 200). `sensor: {query: ...}` over the item record, so the factory's measures
   become lines; the 16 measure gaps' shape is its acceptance.
6. **model-edits-as-data** (core and factory). Any proposed model edit through Accept and a valve, without a gap;
   `model-split-oversized-systems` replayed as its example.
7. **test-scaffold-from-definition** (factory). Built only if gap 4 shows the scaffold would have matched the first
   lines of the tests agents wrote in at least a quarter of gaps.

## Decisions taken alone (each the reversible one)

- The window is the three days the records exist; older history has no records to join, and is left out.
- Promotion defaults to the owner's edit, as `gate: auto` does; automatic promotion only when declared.
- The union rule is declared for test files only at first; agents kept both sides in too few resolutions elsewhere
  to start there (`docs/` other than `docs/GAPS.md` 7 of 76, `ergostat/` 29 of 358).
- The resolver runs before the session and never after it, so an agent's resolution is never overwritten.

## How each count was taken

Three listings of the clone, each searched with a multi-line regular expression (ripgrep's), counting matches:

- **L1**, landed gaps: `git log main --first-parent --merges --since=2026-11-21 --diff-merges=first-parent --numstat
  --format="@@@ %h %ct %s"`. A gap with a file of a class: a match of its header, then lines not starting with `@`,
  then a numstat line of that class (`ergostat/...py`, `ergostat/web/static/`, `dev/(bin|agent|conformance)/`,
  `dev/model/`, `schema/`, `docs/SPEC.md`, `tests/test_*.py`). Prose only and no code outside tests: 442 less the gaps
  with a line outside the class (416 and 392).
- **L2**, merges of main into a branch: `git log --merges --since=2026-11-21 --grep=^Merge.main --cc --unified=0
  --format="@@@ %h %ct %s"`. A resolution: a `diff --cc` line (818). One not "both kept": a `diff --cc` line, then
  lines inside its block, then a line starting `- `, ` -`, `--` (not `---`) or `++` (not `+++`) (633; per class:
  tests 128, docs 82 of which `docs/GAPS.md` 13, dev 83, ergostat 329). Merges with one (319); merges with one outside
  `docs/GAPS.md` (317, so 78 finished by keep-both everywhere); merges with a block neither `docs/GAPS.md` nor a
  both-kept `tests/` one (340, so 55). Order: of the both-kept blocks matched whole up to the next block or merge
  (167, an undercount of the 185, since a match consumes the next header), those with a `+ ` line followed by a ` +`
  line (10).
- **L3**, definition commits: `git log --since=2026-11-21 --grep=": the definition of done" --format="%at %s"`,
  paired by name with L1's landing times.
- The measure shape: `git log main --first-parent --merges --since=2026-11-21 --diff-merges=first-parent
  -G "run: python3 dev/bin/measure.py" -- dev/model` (16 merges).

## Questions for the owner

1. Should a candidate that earns its place be promoted by your edit (the default here) or by itself, as repair's
   `promote: true` does?
2. Should model edits that change no program stop being filed as gaps and go through Accept and a valve instead?
