# Changes made by programs, rules and models instead of AI sessions

Status: proposal, 2026-11-24 (`changes-without-agents-proposal`). Nothing here is built. The owner: "what if we had a
system rigorous enough that we no longer need to have the AI agents write code? ... We want to work all workers up
the ladder, and we want to decompose our workers and delegate and split."

In ergostat's words (NOTES.md) the owner's *worker* is an **agent**, and *up the ladder* is the refactor path: from the
universal AI agent (rung 1) to a narrow AI, a decision, a program, a rule, and finally no work at all (rung 6). A
**lane** below is the path a change takes to main by the rung of the agent that makes it.

The answer in one line: **the ladder is already core for repair approvals and action gates; make it general (any
block may have a cheaper candidate that runs in shadow, is replayed on the record, and is promoted on its agreement),
let model changes travel as data, and start with the one program the record shows within reach: a resolver for
merge conflicts where both sides only added lines, in files a model declares, run in shadow until its replayed
agreement clears the promotion floor.** It does not clear it yet: replayed on the record it agrees with the agent's
file in 131 of the 170 test-file conflicts it claims (77%), against a floor of 95% (§3a).

## What was measured, and how

The record is this factory's git history as cloned for this session (a copy; the live instance was not read). The
window is every commit dated from 2026-11-21 00:00 UTC to the clone's last, the days the gap records
(`dev/records/`) have existed. (Round 1 wrote `--since=2026-11-21`, which git reads as that day at the current time
of day, so its counts moved by the hour: 769, 768, 764 merges on three runs. The window is now pinned.)

- **450 landed gaps**: the first-parent merges `Merge branch 'factory/NAME'` on main, each diffed against its first
  parent;
- **812 merges of main into a gap's branch** (`--grep=^Merge.main`), made by `dev/bin/implement.py` `merge_main`
  with a plain `git merge --no-ff`: a clean one is committed by the program, a conflicted one is left for the
  session to finish;
- **408 of them conflicted, 823 conflicted files in all**: recomputed for each merge from its two parents with
  `git merge-tree --write-tree --name-only` (git 2.47.3), the files git itself could not merge. The session's
  resolution of each is that file in the merge commit.

Every figure from the replay of §3a was produced by running the rules, not inferred: a scratch program (run once
through the test runner, then removed, as this session keeps no scratch code) gave each conflicted file's three
versions (the branch, main, and their first merge base) to `git merge-file` and compared the output with the merge
commit's file byte for byte. *How each count was taken*, at the end, gives each step.

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
  was not reverted), never with the acting agent's raw answer. The record shows why (§3a): in 4 of the 39 test files
  where the resolver and the agent disagree, they differ only in whitespace, and in merge `06b5257e`
  (`tests/test_diagram_rendering.py`) the slip is the agent's (`MAY_DO ="You can look ...` where the side the line came from
  had `MAY_DO = "`); judged against the agent alone, the better answer counts as a disagreement. This page's agreement figures are against the agent's merge commit, the raw answer: the
  outcome-checked rate was not measured (§7 gap 2 does).

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

**What the record says about the size of this lane.** Of the 450 landed gaps, 58 (13%) changed `dev/model/`, and 54
(12%) changed no program file (`*.py`, `*.js`, `*.css`, `*.html`, `*.sh`) outside `tests/` (29 of them, 6%, changed
only prose: `docs/` and `*.md`). None of the 450 was a model edit alone: every gap that changed `dev/model/` also
changed a file outside `dev/model/`, `dev/records/`, `docs/` and `*.md`. So the data lane is
small in the recent work as it was cut, and grows only as measures become queries and model edits stop being filed
as gaps.

## 3. Program-made code

### 3a. Conflict resolution in generated and append-only files

The finding the record makes loudest: **408 of the 812 merges of main into a branch (50%) conflicted**, 823 files
in all, about one conflicted merge per landed gap (408 for 450). Each was left to the session.

**The rule, defined by what it keeps.** *Both sides whole, at git's unsplit conflict blocks; claimed only where both
sides only added.* The resolver asks git for the conflict blocks at the `diff3` level (`git merge-file --diff3`,
which git runs at its *eager* merge level, so a conflict is never split around lines the two sides share), and
claims the file only if every block's base section is empty: both sides inserted at the same place and neither
changed a line of the base. It then writes each block as the branch's lines, then main's, whole. A file with any
block that changed base lines is not claimed: it is left conflicted for the session, with why.

This is **not** `git merge-file --union`. At git's default merge level a conflict is split around the lines both
sides share, and `--union` joins the pieces; the worked example below shows the difference on the record, and the
replay shows its size.

**Replayed on every conflicted file** of the 408 merges (the three versions given to `git merge-file`, its output
compared byte for byte with the file in the session's merge commit):

| Files | Conflicted | Claimed (both sides only added) | Claimed and equal to the agent's file | `git merge-file --union` equal to the agent's |
|---|---|---|---|---|
| `tests/test_*.py` | 215 | 170 | 131 (77% of claimed) | 4 |
| `ergostat/` | 367 | 39 | 26 (67%) | 21 |
| `dev/` | 138 | 31 | 17 (55%) | 13 |
| `docs/` (of which `docs/GAPS.md`) | 78 (0) | 14 | 7 (50%) | 2 |
| `schema/` | 4 | 4 | 1 | 0 |
| other (top-level files, `tests/` files not `test_*.py`) | 21 | 1 | 0 | 0 |
| **all** | **823** | **259** | **182 (70%)** | **40 (5%)** |

Of the conflicts it does not claim, keeping both sides whole would have matched the agent in 1 (in `ergostat/`), so
the claim test gives up almost nothing. All 170 claimed test files parse as Python (`ast.parse`); whether they pass
ruff and the suites was not run.

**Where it disagrees with the agent, in test files (39):** 4 differ only in whitespace, 7 hold the same lines in
another order, and in 28 the agent changed the content: it adapted the branch's lines to main's renames (`c9f0496f`,
`/loops` to `/goals`), dropped a test both sides had kept (`7854cf26`), or wrote new lines (`7fa7c386`). Those 28
are judgments the rule cannot see from the three versions: nothing in the conflict blocks tells it to abstain.

**Coverage of merges.** With the rule declared for `tests/test_*.py` only, it claims every conflicted file of **77
of the 408 conflicted merges (19%)**, and agrees with the agent in every file of **67 (16%)**. Declared for every
file it claims 106 (26%) and agrees in 89 (22%), but outside test files its agreement is 50 to 67%, too low to
declare there. 186 of the 408 had at least one conflicted test file; in the other merges a claimed test file only
leaves the session fewer files.

**What that means for the ladder (§1).** 77% is below the floor of 95% the promotion rule asks, so the resolver
does not act alone on this record: it runs in shadow, writing what it would have done beside the session's merge,
and the measure that could promote it is outcome-checked agreement (against what survived to main), which this
page did not measure. The 4 whitespace cases show why it may come out higher than 77%.

**The generated-file class: nothing to do in this window.** `docs/GAPS.md` conflicted in **0** of the 408 merges.
Round 1 counted 39 "hand resolutions" of it from combined diffs (`git log --cc`), but a combined diff also shows a
clean merge of two nearby changes, so those were not conflicts. The splice it cited is git's own: in merge
`7ef0407c` the file in the merge commit equals git's clean three-way merge of it (the replay's output), main's file
plus 9 lines of the branch's older repair entry, a second, contradicting *Left* clause. A declared *generated* class
(take main's side, render again) would have prevented it, but it would have to apply to **clean** merges too, and
since the queue now refuses a branch that edits `docs/GAPS.md`, it has no work here today. It stays a core option
(off unless declared) and is left out of the first build gap.

### Shown end to end: one recorded merge, the program's output against the agent's

Merge `dc3f5c13` (`Merge main (b9341591cb70) into the branch`; parents `08aee01c` the branch, `b9341591` main; merge
base `278f54a4`). `tests/test_graph_cli_web.py` conflicted: both sides had appended tests after line 453. Each output
below was produced by running `git merge-file -p` (git 2.47.3) on the three versions, not read from a diff.

- **the conflict as the session saw it** (git's default level): the branch's 24 lines against main's 31; the two
  blank lines both sides end with are taken out of the conflict and put after it.
- **the conflict blocks at the `diff3` level**: one block, the branch's 26 lines (one test,
  `test_the_served_diagram_script_frames_what_is_drawn_and_its_edge_hint_names_the_way`), an empty base, and main's
  33 (`test_a_search_or_filter_that_matches_nothing_answers_empty_and_a_match_is_counted_whole` and
  `test_the_record_answers_a_type_that_matches_nothing_with_no_events`): claimed.
- **the rule's output**: 59 lines, the branch's 26 then main's 33. The whole file is **byte-equal to the agent's**
  in the merge commit (`git show --cc dc3f5c13`, hunk `@@@ -454,26 -454,33 +454,59 @@@`: the branch's lines ` +`,
  then main's `+ `, none written, none dropped).
- **`git merge-file --union`, for comparison**: 57 lines. The branch's last line
  (`assert js.count("showSystem(svg, opened)") == 2`) is followed directly by main's `def
  test_a_search_or_filter_...`, with no blank lines between the two functions; the two shared blank lines come after
  main's tests. It parses, but it breaks PEP 8's two blank lines between functions (ruff was not run on it), and it is
  not the agent's file. (The review of round 1 expected
  `--union` to interleave the shared `try:`/`finally:` lines; on this merge it did not: only the trailing blank lines
  were taken out of the conflict.)
- **what landed**: main today has the three tests at lines 454, 480 and 495 of `tests/test_graph_cli_web.py`, in that
  order, as in the rule's output.

### 3b. Codemods and templates for repeated shapes

| Shape | Seen in round 1's 442 landed gaps | A program could make |
|---|---|---|
| a gap's record and definition | 442 (every gap) | already does: `implement.py definition_first` commits it |
| tests for the definition's named acceptance tests | 415 gaps (94%) touched `tests/test_*.py` | the scaffold: one failing test per name the definition gives, in the file it names; the body stays the agent's |
| a factory measure: a sensor line in `dev/model/*.yaml`, its function in `dev/bin/measure.py`, a test | 16 gaps | the whole of it once measures are queries (§2); until then a template for the three pieces |
| a join gap (checks its sub-gaps landed) | 2 of the 7 joins changed only their record and docs | the verdict, from the sub-gaps' records |

### 3c. Generation from declarations

| Declared once | Written by hand today, in | Seen in round 1's 442 landed gaps |
|---|---|---|
| the model's keys (`schema/ergostat.schema.json`) | the compiler (`ergostat/spec/compile.py`, `ir.py`, `load.py`) and SPEC's key tables | 24 gaps changed `schema/`, 49 the compiler, 203 (46%) `docs/SPEC.md` |
| the gap entries (`dev/records/`) | `docs/GAPS.md` | generated already on landing; never conflicted in the window, but git's clean merges spliced it (§3a, `7ef0407c`) until branches were refused it |
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
2. **Per merge into a branch**: each file git leaves conflicted (`git merge-tree` on the two parents, never the
   combined diff, which also shows clean merges of nearby changes), replayed through each candidate rule, its output
   compared byte for byte with the session's merge commit. A conflict a rule claims and agrees on is covered.

**Measured on the copy (from 2026-11-21 00:00 UTC; path classes only, the hunk kinds are left to the miner, §7 gap
4):**

| What | Share |
|---|---|
| landed gaps that changed only prose | 29 of 450 (6%) |
| landed gaps that changed no program file outside tests | 54 of 450 (12%) |
| landed gaps that changed `ergostat/` Python / the interface's static files / factory tooling (round 1's listing, of 442, its window not pinned) | 231 (52%) / 147 (33%) / 118 (27%) |
| merges of main into a branch that conflicted | 408 of 812 (50%) |
| conflicted merges whose every file the §3a rule (declared for `tests/test_*.py`) claims / claims and agrees on | 77 (19%) / 67 (16%) of 408 |
| the same with the rule declared for every file | 106 (26%) / 89 (22%) |
| conflicted files the §3a rule claims / claims and agrees on | 259 (31%) / 182 (22%) of 823 |
| conflicted files `git merge-file --union` reproduces | 40 of 823 (5%) |

**The share, stated plainly.** Measured as whole changes, programs cover almost none of the recent work: no gap in
the window was of a shape a program reproduces end to end. The parts that recur are inside gaps: the conflicted
merge (50% of merges), the record (every gap, already a program's), the test file (94% of gaps, round 1's count),
the SPEC section (46%), the factory measure (16 gaps). The first coverage gain is in merges: 16% of conflicted
merges, and 131 of 215 conflicted test files (61%), would have been resolved as the agent resolved them, which is
why the build split starts there, in shadow, since the rule's 77% agreement on what it claims is below the
promotion floor.

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

In this factory the first lane sits inside the implementor: `merge_main` runs the resolver of §3a beside the
session, in shadow, writing what it would have done for each file it claims; the session resolves every file as
today. Once promoted (§1), a merge whose every conflict it claims is committed by the program as a clean merge is
today, and one it cannot finish is left for the session with fewer files. Later lanes (a measure template, a test scaffold, a model edit) route at `ready` by the gap's
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
| program inside a branch (the resolver, once promoted) | nothing: it runs before the session | 0 added; it takes a claimed conflicted merge off the session | the session minutes it saves are in the live record (`gate-implementor-minutes`), not measured here |
| model edit (data) | `ergostat check` and the owner's valve | seconds: 8 to 16 s of `check` on the image-squeeze example | the owner's answer; no queue. For comparison, `model-split-oversized-systems`, a model change sent as a gap, took 3.5 h from definition to main |

A program-made change still lands only with the queue: the floor of every code lane is the queue's own run, and the
gain over the agent lane is the session, the review and the fix rounds (the medians differ by about two hours, 166
against 38 minutes; a difference of medians, not a measured saving). Only the data lane leaves the queue out.

## 7. The build split: the gaps that follow, smallest valuable first

Each general piece is in core as an option a model declares, off unless declared, naming no gap, program or factory;
this factory's choices are in its own model and `dev/` files.

1. **merge-resolve-declared-files** (about 150 net lines). Core: a program that, given a conflicted merge in a work
   tree and the globs a model declares (`files: {both-added: [GLOB, ...]}`), writes for each declared conflicted
   file the rule of §3a (git's `diff3` blocks, claimed only when every base section is empty, the branch's lines then
   main's, whole) and answers which files it claimed and which it left, with why; it never runs `--union`. The
   factory: declares `tests/test_*.py`, and `merge_main` runs it **in shadow** (its output kept beside the merge,
   the session resolving every file as today), plus a replay command that gives this page's §3a table from git.
   Acceptance: `test_both_added_matches_recorded_merge` (the three versions of `tests/test_graph_cli_web.py` in
   `dc3f5c13`, as fixtures, give the agent's file byte for byte), `test_union_is_not_the_rule` (the same fixtures
   through `--union` give the 57 lines, so a resolver that falls back to it fails), `test_changed_base_lines_left_conflicted`,
   `test_undeclared_file_left_conflicted`, `test_nothing_declared_resolves_nothing`.
2. **agent-candidates-in-shadow** (about 250). Core: a block's `candidates:` run without valves, `shadow.answered`
   events, claims and agreement as measures on the block, and replay over recorded items, with the agreement
   checked against the outcome (what survived to main), not only the acting agent's answer. Acceptance includes the
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

- The window is the days the records exist, from 2026-11-21 00:00 UTC; older history has no records to join, and is
  left out.
- Promotion defaults to the owner's edit, as `gate: auto` does; automatic promotion only when declared.
- The rule is the both-added, whole-block one, not `git merge-file --union`, which reproduced the agent's file in 4
  of 215 conflicted test files against the rule's 131.
- The rule is declared for test files only at first; elsewhere its agreement on what it claims is lower (`ergostat/`
  26 of 39, `dev/` 17 of 31, `docs/` 7 of 14).
- The resolver starts in shadow, since 77% is below the floor; once promoted it runs before the session and never
  after it, so an agent's resolution is never overwritten.
- The generated-file class is left out of the first gap: `docs/GAPS.md` never conflicted in the window, and branches
  may no longer edit it.

## How each count was taken

Round 2 ran a scratch program (Python's `subprocess` around git 2.47.3, through the test runner, then removed) over
the clone. With `W` = `--since="2026-11-21 00:00:00 +0000"`; it gave the same counts on two consecutive runs:

- **Landed gaps**: `git log main --first-parent --merges W`, the subjects `Merge branch 'factory/...'` (450); each's
  files `git diff --name-only M^1 M`. Prose only: every file under `docs/` or ending `.md` (29). No program file
  outside tests: none ending `.py .js .css .html .sh` outside `tests/` (54). Model: any under `dev/model/` (58); of
  those, all files under `dev/model/`, `dev/records/`, `docs/` or `*.md` (0).
- **Merges of main into a branch**: `git log --merges W --grep=^Merge.main --format="%H %P"` (812). Conflicted:
  `git merge-tree --write-tree --name-only --no-messages -z P1 P2` exits 1 (408); its file names are the conflicted
  files (823). The base: the first of `git merge-base --all P1 P2` (14 merges have more than one).
- **Each conflicted file**: the three versions by `git show REV:PATH`, written to a temporary folder. The rule:
  `git merge-file -p --diff3 --marker-size=31` (markers no file holds), claimed when every section between `|||`
  and `===` markers is empty, then each block written as its ours-lines then its theirs-lines. The union:
  `git merge-file -p --union`. Equal: the output's bytes against `git show MERGE:PATH`. Parses: `ast.parse`. The
  disagreements were classed by comparing after removing all whitespace (4) and as sorted lists of lines (7).
- **Coverage of merges**: a merge is claimed when every one of its conflicted files is in a declared class and
  claimed, and agrees when, in addition, each of those files is equal.
- Kept from round 1, not re-counted with the pinned window: the per-class counts of landed gaps (`ergostat/` Python,
  static files, tooling: 231, 147, 118 of 442), the 415 gaps that touched tests, the 203 that changed SPEC, the 16
  measure gaps (`git log main --first-parent --merges --since=2026-11-21 --diff-merges=first-parent -G "run: python3
  dev/bin/measure.py" -- dev/model`), and the §6 times (`git log --since=2026-11-21 --grep=": the definition of done"
  --format="%at %s"`, paired by name with the landing times; its population, the last 30 definitions, does not
  depend on the window's start).

## Questions for the owner

1. Should a candidate that earns its place be promoted by your edit (the default here) or by itself, as repair's
   `promote: true` does?
2. Should model edits that change no program stop being filed as gaps and go through Accept and a valve instead?
