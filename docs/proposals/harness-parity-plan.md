# Harness parity: the plan

Status: agreed 2026-11-17 (owner: "Those sound fine. That's a good list of things to try ... each of these
needs to be expanded and detailed, and a grander plan needs to be devised"). Followed overnight
2026-11-17 until 11:00 and after. Companion to [harness-as-control-system.md](harness-as-control-system.md),
whose sixteen functions this plan recovers, one by one, inside ergostat.

## 0. What this plan is for, and how it is judged

The aim is **parity** with the long Claude Code session that built ergostat: an ergostat deployment that
orchestrates many sessions must do what that one session did, as well. Not a claim that ergostat is
better at some things; the measure is outcomes, on this project's own history.

Rules for the work (the owner's, from this project):

- **No shortcuts.** The Fit page was a shortcut: machinery built, nothing usable, nothing discoverable. Each
  item below is done when it is usable from the existing UI and CLI, documented in MODEL-TOOLS.md or a
  sibling, measured, and tested. "Exists in a module" is not done.
- **Modelled in ergostat.** Each function is a system in ergostat's own terms (stocks, flows, items, goals,
  blocks), like the `modelling` system: it is visible in both diagrams and charted, and the improvement
  loop can work on it.
- **Two kinds of outcome**, marked per item: **resource** (a reusable part of ergostat, for any future
  model: an item kind, a block type, a projection recipe, an output line, a built-in measure) and
  **wiring** (configuration in a project's YAML that uses resources; can be slapped in).
- **Ground truth is this session.** Its transcript (local only, never committed: it is the owner's
  conversation) gives the questions, tasks, decisions and corrections that the parity benchmark scores
  against.
- **Every merge after its suites pass** (exit codes checked); each branch reviewed with screenshots;
  nothing outward-facing; nothing pushed but code and docs to the ergostat repository.
- **Token budget** for benchmark and agent runs overnight: **$20** cap (the owner did not name one; this is
  the figure proposed). Stand-ins are used where they answer the question.

## 1. Foundations (everything below reads or writes these)

### F1. The changeset log (in progress: branch `changesets`)

Events are changesets folded in sequence: JSON Patch (`patch`), whole-document `set`, plain `data` folded
by per-kind fold rules; every field's history; items projected as of any time. Claude Code transcript lines
as `claude.*` events folding into their session items, `causedby` following `parentUuid`. *Resource.*

### F2. Storage that holds a real load (new; the owner's report, 2026-11-17)

Running ergostat under a real load for long ends in failures; the visible symptom was a `BrokenPipeError`
while the server wrote a large JSON response (the page gave up waiting). Events and measurements are in
SQLite with JSON payloads; responses grow with the record; nothing is ever rolled up or expired. The owner
wants a real solution, not SQLite for everything, and asked for **periodic rollup**: archive and compress
the oldest events of an item and replace them with a wrap-up event that preserves the item's state at that
time.

1. **Measure first.** A load test: image-squeeze and the-job at 10× speed for hours (stand-ins), recording
   store sizes, query times per API, response sizes, and memory; find what grows and what breaks.
2. **Rollup (compaction) for items**, which changesets make natural: for an item, events older than a
   horizon are replaced by one `ergostat.item.snapshot` event (a `set` of the folded document as of that
   time, with each field's history summarised), and the originals move to a compressed archive segment
   (per item kind and month), still readable on demand ("show full history" reads the archive). The
   record's meaning is unchanged: folding the snapshot plus later events gives the same item.
3. **Retention and downsampling for measurements**: raw points for a recent window, then rollups (min,
   max, mean, last per bucket) at coarser tiers, with retention per tier (configurable).
4. **Backends behind the existing interfaces** (`Events`, `Measurements`), chosen by measurement, not
   habit. Candidates to evaluate in the load test:
   - Events: an append-only segmented log (compressed segments, an index by item, type and time); NATS
     JetStream; DuckDB with Parquet segments.
   - Measurements: VictoriaMetrics (single binary, Prometheus-compatible, retention and downsampling built
     in; it also lets ergostat's own series be queried by PromQL like any other source); a local columnar
     store.
   The default must still run on a laptop with no services; a real backend is an option a project names.
   Orchestra already had bus and metrics-store backends with conformance suites
   (`~/orchestra_2/tests/bus`, `tests/metrics`): reuse the design and the conformance tests.
5. **The web API bounded**: no response proportional to the whole record (pagination, windows, bucketed
   series, limits), and a client that went away (`BrokenPipeError`) is a quiet, logged event, not a
   traceback.

*Resource.* Done when the load test runs for hours with flat query times and bounded responses, and the
rollup's equivalence (fold before = fold after) is tested.

### F3. The parity benchmark

From this session's transcript (ingested into a private scratch project, never committed):

- **Questions only the long session could answer** (what was decided, why, what the owner means by a
  phrase, what was rejected), with answers taken from the owner's own words.
- **Tasks it actually did**, with the owner's corrections as the judge of a result.
- Fresh sessions given different starting contexts (projection recipes, section 2.10) answer and redo
  them; scored against the ground truth. The score is the measure of parity for every item below.

*Resource* (the harness and scorecard), plus a private dataset.

## 2. The sixteen functions

Each: what the long session did; what is built (data, behaviour, UI, CLI); how it is modelled in ergostat;
resource or wiring; how it is measured; dependencies.

### 2.1 Generating and revising setpoints

- **Session did:** turned vague goals into sub-goals and re-planned after every observation.
- **Build:** a work item's goal is a field with history (F1), not a fixed ticket. A worker emits a
  `revise` line (like `propose`): a new goal text with its reason, for its own item or for items that
  follow it. Revisions to the worker's own item apply if the item's policy allows; others become
  proposals for whoever owns that goal. Each item shows its goal's history.
- **Modelled:** stock *items with open goal revisions*; flow *revisions proposed*, *revisions applied*;
  goal on *revisions pending* ≤ n.
- **Kind:** resource (the `revise` output, goal-as-field convention); wiring per project.
- **Measure:** items revised before finishing, and whether revised ones were accepted more often (F3).
- **Depends on:** F1.

### 2.2 Knowing when it is done

- **Session did:** decided "good enough" or another round.
- **Build:** every work item carries `done-when`, verbatim from the message that started it. A built-in
  judge mode, `judge: intent`, runs a reviewer session from the item's projection (2.10) and the
  done-when, asked "is this done as meant?", with evidence lines; its verdict sits beside the tests'. A
  reopened item records `reopened` with the reason.
- **Modelled:** stock *done, not reopened*; flow *reopened* (the false-done rate); goal on it.
- **Kind:** resource (`done-when`, the intent judge); wiring per project.
- **Measure:** false-done rate (passed, later reopened) against tests-only.
- **Depends on:** F1, 2.10.

### 2.3 Inferring intent: asking or acting

- **Session did:** chose between a question and a guess.
- **Build:** a `question` output line: becomes an `ergostat.question` item. Policy decides who answers:
  the owner, or first an inference session started from the projection of the owner's words on the
  question's topic (2.13), its answer marked *inferred* until confirmed. The worker continues on an
  inferred answer or waits, by the question's stakes.
- **Modelled:** stocks *questions open*, *inferred answers unconfirmed*; flows *asked*, *answered*,
  *overruled*; goal on *open questions* ≤ n.
- **Kind:** resource (the `question` line and item kind); wiring.
- **Measure:** inferred answers later overruled; rework traced to unasked assumptions (F3).
- **Depends on:** F1, 2.13.

### 2.4 Absorbing interruptions

- **Session did:** folded mid-work messages into the work.
- **Build:** the owner's messages are `ergostat.message` events (from the page, the CLI, or an AI
  front-end). Work items subscribe to messages about their parts or topic (a matcher: explicit item
  mention, part names, or a classifier session). A running session receives a matching message as its
  next turn (resume with it); a finished one gets a follow-up item.
- **Modelled:** stock *messages unrouted*; flows *routed*, *redone because missed*.
- **Kind:** resource (message events, routing, resume-with-message); wiring.
- **Measure:** messages reaching the right work in flight; work redone because a message didn't.
- **Depends on:** F1.

### 2.5 Gating by risk, with thresholds that adapt

- **Session did:** read freely, asked before outward acts, stopped asking what was already allowed.
- **Build:** `ergostat.consent` items: each approval of a kind of action (scope, what, by whom) recorded;
  gates read the consents, so a second identical approval is not asked; consents expire or are revoked;
  every gated action names the consent it relied on.
- **Modelled:** stock *standing consents*; flows *asked*, *granted*, *revoked*; goal on *repeat asks* = 0.
- **Kind:** resource.
- **Measure:** questions the owner had already answered.
- **Depends on:** F1.

### 2.6 Diagnosing failures

- **Session did:** diagnosed and varied, not repeated.
- **Build:** a failed step becomes an `ergostat.failure` item folding its output and diff. A retry is a
  session from that item's projection, prompted to state a diagnosis (a `diagnosis` line with evidence)
  before acting. Diagnoses are checked against what fixed it.
- **Modelled:** stocks *failures open*; flows *diagnosed*, *fixed first time*, *retried blind*.
- **Kind:** resource.
- **Measure:** first-time fixes after diagnosis versus blind retries.
- **Depends on:** F1, 2.10.

### 2.7 Running experiments before acting

- **Session did:** measured before designing; re-ran the one test; read before editing.
- **Build:** worker instructions (a shared prompt section, versioned as a resource) and an `experiment`
  event line (question, method, result). Reviewers check that claims rest on experiments in the record;
  "assumed without checking" is a finding kind.
- **Modelled:** stock *claims without evidence*; flow *experiments run*.
- **Kind:** resource (prompt section, event type, finding kind).
- **Measure:** "assumed without checking" findings over time.
- **Depends on:** F1, 2.16.

### 2.8 Checking state before acting and effects after

- **Session did:** `git status` before merging, read before trusting.
- **Build:** a *current state* projection (what moved on main, what is running, open findings on the
  item's parts) included in every session's start; an *effects check* run by ergostat after the session:
  tests, audits, the claims (2.16), not left to the worker's choice.
- **Modelled:** flows *started on stale state*, *effects claimed and missing*.
- **Kind:** resource (the projection recipe; the post-session check as a built-in judge mode).
- **Measure:** conflicts, duplicates, missing effects.
- **Depends on:** F1, 2.10, 2.16.

### 2.9 Allocating attention

- **Session did:** chose what to look at and what to tell the owner.
- **Build:** a digest block (the-job's morning brief, generalised as a resource): what changed, what needs
  the owner, what is blocked, at the owner's level, from the record; notifications only for items marked
  as needing the owner; a page section (no new page: the Items page's `digest` kind).
- **Modelled:** stock *needs the owner*; flows *raised*, *resolved*; goal on age of the oldest.
- **Kind:** resource (digest block, `needs-owner` mark); wiring.
- **Measure:** things the owner asked about that were already known; digests not opened.
- **Depends on:** F1.

### 2.10 Delegating, and trusting what comes back

- **Session did:** wrote briefs that carried the owner's words verbatim, and reviewed results according
  to track record.
- **Build:** **projection recipes** as named, versioned objects in the YAML (`contexts:`), each a recipe
  for a starting context from the log: an item's history; the owner's words on topics; confirmed
  decisions (2.12); corrections for this kind of work (2.13); current state (2.8); a fork of a session
  (all or some of it). `ergostat context <recipe> [--item X]` renders one; any `ai` block can start from
  one; the recipe used is recorded on the session. Outcomes link back to the recipe. A **trust** stock
  per worker type and model (rework, findings, contradicted claims) sets review depth.
- **Modelled:** stocks *trust* per worker; flows *briefs*, *reworked*; projection recipes compared in F3.
- **Kind:** resource (the core of parity).
- **Measure:** outcome quality by recipe (F3); review effort against defects found later.
- **Depends on:** F1.

### 2.11 Translating in both directions

- **Session did:** turned the owner's words into work, and the work into what the owner needs to know.
- **Build:** inward: a message becomes an item with its `done-when` and the owner's words kept verbatim
  (an intake block: rule-based first, an AI session where needed). Outward: reports generated from the
  record (what ran, what passed, what changed), never from a worker's own claims.
- **Modelled:** stock *messages not yet items*; flows *translated*, *corrected by the owner*.
- **Kind:** resource (intake block, record-based report).
- **Measure:** reports contradicting the record; the owner's corrections of translations.
- **Depends on:** F1, 2.16.

### 2.12 Coherence with earlier decisions

- **Session did:** checked every action against conventions and earlier decisions.
- **Build:** `ergostat.decision` items: the decision, its reasons, the alternatives rejected, the owner's
  words, going proposed → confirmed → superseded. Proposed by an extractor session reading session logs
  (this one first); confirmed by the owner. The confirmed set is included in every session's start within
  a size budget (most relevant first, the rest as pointers). A reviewer checks each diff against it; a
  contradiction needs an explicit supersede with a reason.
- **Modelled:** stocks *decisions confirmed*, *proposed awaiting the owner*; flows *superseded with
  reason*, *contradicted without*.
- **Kind:** resource.
- **Measure:** "we already decided this" corrections; supersessions without a reason.
- **Depends on:** F1.

### 2.13 Learning from correction

- **Session did:** turned one sentence of correction into changed behaviour.
- **Build:** corrections are events: dismissals with reasons, reopened items, messages classified as
  corrections. A corrections projection, per kind of work, is included in later sessions of that kind
  (2.10). Repeated corrections are found and raised.
- **Modelled:** stock *corrections active*; flow *repeated corrections* (should be ~0).
- **Kind:** resource.
- **Measure:** the same correction given twice.
- **Depends on:** F1, 2.10.

### 2.14 Coordinating concurrent work

- **Session did:** a worktree per agent, merges one at a time, telling agents what moved.
- **Build:** a worktree per item, a lock on the parts an item touches, a merge block (one at a time, after
  its judges), and every running session told what moved on main (2.4).
- **Modelled:** stocks *waiting to merge*; flows *merged*, *conflicts*, *main broken*.
- **Kind:** resource (merge block, part locks); wiring.
- **Measure:** conflicts, collisions, merges that broke main.
- **Depends on:** F1, 2.4.

### 2.15 Filtering by value

- **Session did (sometimes badly):** refused scope creep, queued instead of building.
- **Build:** proposed work carries the outcome it should move and its expected cost; a value judge
  compares predicted value against the cost it adds (complexity as a stock); low-value proposals dropped
  with the reason, the owner can overrule. The anti-drift loop of the harness note §3.
- **Modelled:** stocks *complexity*, *proposals pending*; flows *built*, *dropped for value*, *called
  pointless later*.
- **Kind:** resource (value judge); wiring.
- **Measure:** items the owner later called pointless; outcome moved per feature added.
- **Depends on:** F1, the model improver's judge.

### 2.16 Reporting truthfully

- **Session did (not always):** said what was done.
- **Build:** a worker's claims are `claim` lines ("tests pass", "done", "fixed X") checked by ergostat
  against the record (test results, diffs, runs); a contradicted claim is a finding against the worker and
  lowers its trust (2.10).
- **Modelled:** flows *claims*, *contradicted*; per-worker contradiction rate.
- **Kind:** resource.
- **Measure:** contradicted claims per worker type (this session's two failing-test pushes are the test
  case).
- **Depends on:** F1.

## 3. Order of work

1. **F1** changesets and transcript events (in progress), **F2** storage (load test, rollup, retention,
   bounded API, then backends), in parallel.
2. **2.12 decisions and 2.13 corrections**: extracted from this session's transcript (private), proposed
   for the owner to confirm in the morning; the decision item kind and the corrections projection.
3. **2.10 projection recipes**: the `contexts:` section, `ergostat context`, sessions started from a
   recipe, recorded on the session.
4. **F3 parity benchmark**, first run: questions from this session, answered by fresh sessions given
   different recipes (none, owner's words, decisions, decisions + corrections, a fork), scored. This says
   which recipes recover the most, and informs everything after.
5. **2.2 intent judge** and **2.16 claim checks**.
6. Then 2.3, 2.4, 2.6, 2.8, 2.11, 2.14, 2.1, 2.5, 2.7, 2.9, 2.15, each with its model in ergostat and its
   measure.
7. A `harness` example (or the root `ergostat.yaml`) that wires them together on ergostat's own
   development, observe-only first.

## 4. Progress log

(Appended as work lands: date, item, branch and commit, measure, what's next.)

- **2026-11-17 ~03:30, F1 landed** (ce593ba). Items fold events as changesets: JSON Patch (own RFC 6902
  implementation, all-or-nothing), `set` as remove-all-and-add, per-kind `fold:` rules; every field's
  history (`ergostat item ID --history`, the item page); as-of for fields. Claude transcripts ingested as
  `claude.*` events into their session items (2,000 lines of a real transcript in ~55 ms; item counts
  unaffected thanks to a partial index). Every example folds exactly as before where no rules were added
  (a property test). 562 unit tests pass. Next: F2 (storage) and 2.12/2.13 (decisions, corrections) are
  running; they rebase onto this.
- **Flaky browser test fixed**: the line-panel link test waited a fixed 400 ms for a panel; it now polls
  up to 5 s. It failed only under load.
- **2026-11-17, F3 harness** (branch `parity`). `ergostat bench parity run | context | draft`
  (`ergostat/bench/parity.py`, `contexts.py`, `parity_draft.py`; [docs/parity-bench.md](../parity-bench.md)):
  fresh `claude -p` sessions per case and variant, the context as their system prompt, judged by a separate
  session (correct / partly / wrong / contradicts) plus exact checks; scorecards in Markdown and JSON with cost
  and tokens; resumable, with a cost cap. Built-in variants: none, docs, the owner's words, a fork, memory files;
  any projection (`ergostat context ...`, when it lands) is a file. The first run's dataset, answers and scores
  are private (outside the repository). Tests on made-up data (`tests/test_parity.py`).
- **F3 first run** (48 cases from the session: 40 questions, 8 tasks; sonnet answering and judging; ~$5.6).
  Score by starting context: none 0.03 · docs 0.33 · fork of the last 20 turns 0.28 (0.95 inside its window,
  0.11 outside) · memory files 0.21 · all the owner's messages 0.94 (an upper bound: the truths are quoted
  from them). Learned: the owner's messages are small (~30k tokens) and carry most of what matters; docs and
  memory carry outcomes, not reasons or rejections; fresh sessions repeat corrected mistakes on tasks (what
  2.13 should carry); truths need "as of" (a decision later reversed). Next dataset: truths from the
  assistant's turns and the commits, not only the owner's words.
- **2026-11-17, 2.16 claims** (branch `claims`). A `claim` output line any block may print
  (`{"claim": {"says", "about", "check"}}`), recorded as the built-in item kind `ergostat.claim` (made → verified,
  contradicted or unchecked; events `ergostat.claim.*`) and checked by ergostat after the run, never by the claimant:
  `tests` (the declared test command, `claims: {tests: {run, in}}`, run in a folder or on an exported copy of a
  commit or an item's branch; else the latest test run in the record), `changed`, `state`, `exit`, `level`, and
  checks a project declares. Trust: `ergostat.trust.contradicted[@block | @rung:K | @model:M]` and counts, built-in
  measures; a contradicted claim is the finding `contradicted-claim` and needs attention. `ergostat claims`, MCP
  `trust`, Items → `ergostat.claim` (trust table, a claim's verdict and evidence); SPEC §12g, docs/CLAIMS.md. The
  test case: pytest piped through tail, a run exiting 0, a claim that tests pass; contradicted by running the
  declared command. image-squeeze: the developer claims "tests pass" and "submitted hypothesis/N"; `FACTORY_LIE=1`
  plants a liar: 16 claims, 8 contradicted (every lie), 8 verified; honest, 10 of 10 verified; goal
  `developer-honest`. Next: 2.10's trust stock reading these, a reviewer depth set by it.
- **2026-11-17, 2.12 decisions and 2.13 corrections** (branch `decisions`). Built-in item kinds
  `ergostat.decision` (proposed → confirmed → superseded; dismissed) and `ergostat.correction` (proposed →
  confirmed → retired; dismissed), the owner's words verbatim with session, line and time, folded as `append`;
  a supersede needs a reason and the replacing decision; a correction given again is linked to the first and
  raised (`correction-repeated`). The extractor is an ordinary block: a free stand-in and an `ai` mode
  (`ergostat decisions extract FILE|DIR|ITEM [--since] [--model sonnet --max-cost N] [--print --new]`), every AI
  quote checked against the owner's turn. `ergostat context decisions [--scope] [--budget]`, `ergostat context
  corrections --kind`, MCP `context`; the item page's Confirm, Dismiss, Supersede, Retire, each with a reason;
  SPEC §5a, docs/DECISIONS.md. On this session (private run): the AI extractor proposed 45 decisions and 30
  corrections (5 linked repeats) from 161 owner turns for $1.28; sampled precision 0.75 (decisions), 0.95
  (corrections), 0.5 (repeats); the stand-in 0.28 and 0.83. As a parity variant, the decisions context (34k
  characters, all still proposed) scores **0.49** (none 0.03, docs 0.33, fork 0.28, memory 0.21, owner's
  messages 0.94): strong on decisions and rejections (0.71, 0.63), weak on meanings and state. Everything waits
  for the owner to confirm.
- **2026-11-17, F2 storage** (branch `storage`). Measured first (`scripts/loadtest.py`: each demo run two
  minutes with its stand-ins, that record tiled to 1, 7 and 30 days with the bulk writers, every page's API
  asked at 1h and 7d windows with a 30 s client, then the demo run on top for a minute; `--compare` prints
  the table). On main (117378c's parent line, SQLite): image-squeeze answered 48 of 48 at 1 day, 21 of 48
  at 7 and 30 days; the-job 21 of 48 at 1 day and **none** at 7 days; one slow answer (the Model page's
  fit, 24 s on a day of record) left the server computing for clients that had gone, so every later
  answer timed out, and each hang-up was a `BrokenPipeError` traceback. What grew with the record, not
  the window: a loop's crossings (every one ever, per loop, per snapshot), item folds (the whole record,
  per sensor tick and per page, and again per model tried by the fit), items-flow; the events file
  (~490 bytes an event); the-job's engine fell from 4.4 to 0.02 events a second on a week's record.
  After: the API bounded (events 1,000, items 500 with offset, a kind's finished items 1,000 dots, a
  client gone is one line); a loop's crossings read for the window; the fold of every item kept and
  followed (shared by every model with the same kinds; moves are history, so a past span's moves read
  it); item roll-up into `ergostat.item.snapshot` (a `set`, both folds where transcript lines went too,
  archived per kind and month, full history on the item page); measurements in raw (2d) then 1m/10m/1h
  tiers; the segmented log the default for events (a fifth of SQLite's size, as fast or faster),
  VictoriaMetrics an option for readings (its engine reads are requests: the engine kept to 0.8 readings
  a second against 5.8). image-squeeze: 48 of 48 at 1, 7 and 30 days (slowest 9, 11, 16 s: the fit's
  first, cold, answer), engine at its template rate at 30 days, events 474 MB for 4.9 M (SQLite 2,278 MB),
  the 30-day record rolled up in 244 s (656 k events of 49 k items into 18 MB of archive). the-job:
  48 of 48 at 1 and 7 days (slowest 4 s and 19 s), engine 3.2 events a second at 7 days (main 0.02);
  at 30 days it still breaks: the speeded-up world makes 19,000 new items a day, so the record holds
  524,000 live items; rolled up in 584 s (2.26 M events into 104 MB of archive, readings 2,771 to 722 MB)
  it answered 15 of 48 (main: 0) and the engine ran at 1.6 events a second (template 4.0), because the
  kept fold of every item is in each process's memory (13 GB at peak) and a fresh one takes about a
  minute. Equivalence: `tests/test_rollup.py` (every example's kinds, random data/patch/set/refused
  and transcript lines, rolled up three times over, with and without transcripts, both backends) and
  `demo_check` on each demo's own record. Next: the fold persisted (an item index), so a record of
  half a million live items starts in seconds; the engine reading VictoriaMetrics through a cache.
