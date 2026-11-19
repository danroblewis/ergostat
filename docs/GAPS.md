# Known gaps

What ergostat is known to lack, kept current as work lands. Each entry says where it came from and its
state: **open**, **in progress** (with the branch), or **done** (with the commit, then removed at the next
review into *Done recently*). Newest decisions from the owner first within each section. Last reviewed 2026-11-18.

## Remote systems and libraries

- **Remote systems** (first slice done, 72da4e1, merged from `remote`; what is left below is open;
  `docs/proposals/remote-systems.md`, SPEC §4c): a system run by
  another ergostat instance, composed into a local model. Its model is served by the remote instance and changes
  while it runs; its event log and metrics are queried where they live; its agents run on the remote machine,
  never locally. The local model reads it, links to its parts, and draws it as a subsystem; it never runs it.
  (Owner, 2026-11-18.)
  - *Done*: the read-only remote API on every page server (`/remote/v1/`: status, model with
    version and ETag, events by cursor, items, counts, readings, series, process; bearer tokens per consumer,
    hashed at rest, rate-limited); `remotes:` in the YAML (fetched, cached, refreshed on `every:` and when a
    reading says the version moved; parts brought in as an external subsystem, blocks never run, sensors
    reading the remote, `systems:` to narrow); source type `ergostat` (one batched request per remote a
    period, stale readings refused); local references checked against the remote's current model
    (`remote-reference-unresolved` with a stand-in, `remote-output`, `remote-unreachable`,
    `remote-insecure`); drawn in Dynamics, Blocks and Process, marked remote with version and age;
    `ergostat remote` (status, token, events, refresh); edits to remote parts refused; the demo
    `examples/remote-pair/` and its two-instance test.
  - *Left*: the remote's events in the Items and Record pages (the cursor cache exists, only the CLI reads
    it); lines in the process map between our items and theirs (needs an id both logs carry); proposals
    written as text for the remote's owner (the refusal is built, the text is not); serving the IR beside
    `ergostat-model/1` once it exists; a remote that is itself composed of remotes (its imported parts are
    not served); a remote's measures on its closed box (`show:` of the remote's systems); mutual TLS.
- **Shared libraries** (open): templates and reference models shared between projects and people, by git URL
  or package, with versions, bringing their own scripts. For people modelling their own real systems.
- **External event logs** (open): systems that keep their own event log (Kafka, a ticket history, an incident
  log): copy in (works today through collectors), read in place, or mirror with a cursor that cites the
  original. Remote systems are the first case of reading in place.
- **Identifying existing controllers** (open; `docs/proposals/external-systems.md`): an autoscaler or alert
  rule modelled from its record.

## Modelling

- **Built-in join** (done, de204df and 966a07f, on `causes-join`; SPEC §5a, *Join*): `join: {children: REL, all:
  STATE, to: STATE}` (or `any:`) on the parent's kind, fired on each child's move from the item index, the parent's
  move recorded as `ergostat.item.joined` caused by the child's, folded only forward and counted like any other;
  `examples/roadmap` uses it in place of `bin/epics.py`. *Left*: the Blocks view does not draw a join (a rule on a
  kind, not a block); each child's move reads all its parent's children (O(children) per move: fine for an epic's
  tickets, not tuned for thousands).
- **Relations, what is left** (open; the first part merged as c4888bd from `relations`; the Process view draws them,
  done in 0f7f870 on `smallgaps`): the Graph and Timeline read relations as they stand now (time travel does
  not reach them) and are not in a snapshot; the projection does not level resources (a block's `pool`);
  `ticket-factory` does not record Jira's links: its collector does not read them (`bin/jira.py` asks Jira for
  summary, status, labels and description only), so `issuelinks` and `parent` must be asked for and folded as
  relations first.
- **Craft findings in `check`** (in progress, `selfimprove`; from `docs/MODELLING-WELL.md`): `check` is silent on a
  part with no `description`, a stock with no `unit`, a flow between stocks with no equation, a `process:` with no
  `identified:`, a sensor (a collector) with no description, and event types of one kind in mixed forms. Each is a
  review-checklist item an agent has to remember; a note-level finding would teach it.
- **A step whose goal never goes off** (in progress, `selfimprove`): a `takes:` block runs only while its goal is
  off, so a queue goal with a tolerance (or a setpoint above 0) lets items wait unseen; nothing says so. Found when
  the example's first goals had tolerances and nothing ran.
- **Proposals superseded by any edit** (open; owner, 2026-11-19): a model change made against a version since
  changed, even only in its numbers, is superseded and never written (SPEC section 12e). With an agent editing the
  YAML, or modelling accepting its own changes, nearly every open proposal goes stale before it is judged. Rebase
  instead: carry a change to the new version when the parts it touches are unchanged and its diff still applies,
  keeping its evidence; supersede only when its own neighbourhood changed.
- **The judge almost never decides on a slow model** (open; owner, 2026-11-19: on the work model nearly every
  change is inconclusive, a few refused, none accepted): a change must gain 2% in every window of at least twice
  its stock's time constant, on record after it was made; a model whose flows run per day rarely has that, and a
  change that cannot move the replay (structure, wiring, descriptions) can never prove itself. Say how much more
  record a verdict needs, judge such changes by structural measures (as redesign's scorecard does), and let a
  change carry over edits elsewhere (above).
- **A cause for a scheduled run's events** (done, e4800ea, on `causes-join`; SPEC §5b): the run is the cause its
  events cite (no `ergostat.schedule.fired` event per firing); the Process view draws each scheduled block in a
  **schedules** frame with its fan-out. *Left*: an event line still cannot name a cause of its own (`causedby`).
- **Triggers on an event type** (parked on `triggers`, failed its gate twice; `docs/roadmap/overnight/triggers.md`,
  *Where it stopped*): a block started by an event type alone, not only by a state change.
- **Closed-loop simulation** (done, `closedloop`; docs/roadmap/overnight/closedloop.md): projection held the blocks still; now it runs with the loops
  running by default (`numbers/closedloop.py`, SPEC §12b): goals and built-ins by the engine's own code, each machine
  block by its identified model (or a flagged assumption), on the causes strip, what-if (parameters,
  an input's rate, a setpoint, a pool), the fans, proposal effects and `ergostat project`; risk (Monte Carlo: each
  goal's chance of being off at the horizon and its expected time off). *Left*: a block's law written in the model
  (`law:`, 12-model gap 1) in place of a model identified from its record; loop dominance and leverage on the
  closed-loop run; a model for a machine block that commands another (held); stochastic arrivals within a run
  (the risk varies their mean over the horizon, not their timing).
- **Operating modes, regime-scheduled thresholds, interlocks, risk gating** (open; designed in
  `docs/proposals/coordinator/08-modes-and-protection.md`).
- **Observer staleness and estimated stocks** (done, `observer`; SPEC §9.6, `coordinator/06-observer.md`): a reading's
  age, `stale` goals, `on-stale: act | hold | off` per goal or block; a scalar Kalman estimate per stock with an adaptive
  gain (`stock.X.estimate`, `.uncertainty`), its innovations as `observer/X/innovation`, and `model-disagrees`. All
  opt-in (`observe: true`, `on-stale:`, or reading the estimate). Not yet: a
  covariance between stocks, item-level states (06's x̂1 to x̂10), sampling that rises after a surprise (06 §3.3).
- **Per-item and per-group goals** (done, 8fb7440 and e46dc45 on `smallgaps`; SPEC §8 `per:`): a goal on a stock counted from
  items, held by each item or each group of them by a field (a relation such as `parent`), naming those that break it.
- **Finding structure from residuals** (open; porting SD Lab's Kalman-LNA work; `parity/00-modeling-review.md`). It
  can now build on the observer's innovations (`observer/X/innovation`, `model-disagrees`).
- **Proposals drawn dashed in both diagrams; proposals that state the behaviour they predict** (the dashed drawing in
  progress, `redesign`; the stated behaviour done on `extremes`: each change's effect states the closed-loop projection
  of the stocks it touches in one sentence above the strip, accepting records it as `predicted`, and the judge's pass
  records `observed` beside it once the horizon has passed; `docs/roadmap/overnight/extremes.md`).

## Runtime, scale and latency

- **Warm workers instead of a process per item** (parked on branch `warm`, after failing its gate twice; its
  definition file, `docs/roadmap/overnight/leasekill.md`, says where it stopped and the fixes it needs).
- **ergostat's upkeep as a modelled system** (idea; owner, 2026-11-19): a built-in `use: upkeep` template, like
  `use: modelling`, drawing ergostat's own housekeeping as control loops: item-index files (created on each change to
  the kinds, tidied, healed), event-log compaction, measurement retention, the worktree pool, expired leases, the
  engine's stall watchdog. Stocks, goals (e.g. index files <= 6) and rule-tier controllers instead of constants in
  the code; whether a delete is safe stays an interlock in the code (`coordinator/08-modes-and-protection.md`), and
  no controller reads what it manages. If the engine stops, its loops stop: so correctness never depends on them, each fails
  safe (tidying stopped means files pile up, nothing breaks), and they are watched in layers (the engine's own
  watchdog, then the runner or launchd for a dead process, with a heartbeat goal an outside watcher reads).
- **From upkeep's fault injection** (`docs/proposals/upkeep.md` §4; `docs/roadmap/overnight/resilience-core.md`):
  - **Nothing restarts a dead engine; `status` shows a dead engine's last reading as alive** (done, 3e106ee:
    `ergostat run --service [--install]`, the outer watcher; "engine not running (last seen ...)").
  - **The watchdog restarts without finding the cause, every 6.5 minutes; a hang while starting is unseen; pool
    wedge found at 130 s** (done, 3e106ee: the index lock's holder dumped; back-off 60 s to 30 m; a startup deadline).
  - **An `alarm` block lights nothing** (done, 3e106ee).
  - **Block logs, `threads.txt`, `transcripts.json` and `run.log` grow without limit; old project folders pile up**
    (done, 3e106ee: `storage: logs:`; `ergostat compact --projects`).
  - **The CLI refuses to run while the YAML is broken**, so every `$ERGOSTAT_CMD` call fails while an agent edits
    (in progress, parked on branch `resilience`: its fallback to the engine's last good model settled includes
    against the live files, so it could load a model that never existed; it needs includes settled against the kept
    files, or the fallback refused when the live include set differs).
- **Extreme-conditions tests and calibration per part of the model** (done on `extremes`,
  `docs/roadmap/overnight/extremes.md`): the extreme conditions run the closed-loop projection (inputs at 0 and 10×, a
  pool at 0, each setpoint at its limits, each parameter at its range's ends), kept on disk per condition and per
  connected part of the model, run in the background by one low-priority process per project and bounded (the Check
  page's first status 4 s → 0.02 s on ticket-factory; `check` again 4.1 s → 0.3 s); each equation's own fit (R²,
  scaled error, skill against its mean) on its panel, and a finding where it fits worse than its mean. Left: a law's
  windup is only tested where a block writes `gain:`; the CLI waits at most 5 s, so a large model's first `check` says
  the rest are still to run; a project never run (no state directory, which `check` never makes) keeps them in memory
  only, so its every `check` runs them again.
- **An engine per system; line routing for large diagrams** (open; `docs/proposals/scale.md`).
- **The IR and a Rust runtime** (open; `docs/proposals/ir-and-runtime.md`, 12 questions for the owner).
- **A run whose lease expired is killed** (done, 5fa37de, `leasekill-only`; the owner decided 2026-11-18; SPEC §9.5
  *Fencing*): TERM to its process tree, KILL after a grace, `ergostat.run.killed`; its cost recorded, its item retried.

## Interface

- **Light theme: the repeats toward the paper are low in contrast** (open; for a design pass, no colour work until
  then; found fixing the dark theme's): the third round of correspondence colours (`--g-fade`, 55% of the hue) stands
  1.6:1 to 2.5:1 on white, and `--g9` (gold) 2.4:1 as it is; WCAG asks 3:1 for graphics. Tried on `smallgaps`
  (48b4254, reverted in 95e1a1f): six hues darkened and `--g-fade` 75% passed 3:1, but the gate review found the
  palette blurred: every hue at OKLCH L 0.50 to 0.56, gold and olive ΔE 4.9 apart, orange 3.0:1 and gold 3.8:1 against
  `--warn`, each repeat only about 12 from its hue. A repeat toward the paper that keeps 3:1 forces every hue to one
  lightness. To try next: mark the paper round by an ink outline or a dash instead of lightness, or alternate the
  hues' lightness (light hues repeated toward the ink only).

## The owner's work setup

- **A "report upstream" channel** (done, `reports`; SPEC §12m): a built-in item kind `ergostat.report` (drafted →
  reviewed → submitted / dismissed), drafted by the MCP tool `report_upstream`, `ergostat report --draft`, ergostat's
  own crashes (engine pass, runner, page server 500s, `check`; one a stack signature) and a block's
  `{"report": ...}` line (the modelling improver's prompt says when); scrubbed before anyone reads it (the model's
  names, the owner's denylist in the state or home folder, secrets, URLs, hosts, IPs, emails, paths, ticket keys,
  mentions; each removal logged with why); written as a Markdown issue to the state directory's `reports/`; `ergostat
  report`, the item page (Copy, a new-issue link with the title filled in, the scrub log) and one line in "needs
  attention". The owner submits by hand: ergostat makes no network call (decided by the owner, 2026-11-18).
  *Left*: the redesigner's guide (on `redesign`) should say the same report line the improver's does; people's names
  are caught only by the denylist, @mentions and the model's person agents; a crash's reproduction is checked only for
  `check`.
- **Remodel `the-job`** (open): equations, designed control laws, person steps marked, the coordinator's
  structure and behaviour tests.

## Done recently

- **The Blocks view crashed on a stock with no flows** (`IndexError` at the integrator's summing junction): drawn as an
  integrator with no inputs (8148f5f and e46dc45, `smallgaps`).

- **The reload wedge**: the item index read under its lock; a reload waits for edits to settle, never takes a broken
  model and swaps atomically; a watchdog recovers a stalled pool, loop or process (merged from `reloadfix`).
- **"file is not a database"**: item-index files deleted under other processes; cross-process locks, tidy only what
  nobody holds, a corrupt index rebuilt from the record (merged from `indexfix`).
- **A block reading a goal's error is drawn reinforcing**: a machine block's reading of a goal's error takes the sign
  of how it moves the goal's quantity (2df52cc, `gapsfix`).
- **A sensor's command is not given `ERGOSTAT_CMD`**: a sensor's run gets what a block's run gets to call ergostat
  back (ea0da0b, `gapsfix`).
- **A block's tier is not drawn**: written small at the top of each block in the Blocks view (47478b9, `gapsfix`).
- **Dark theme: the lighter correspondence colours are low in contrast**: 3:1 at least (0806abd, `gapsfix`).
- **One-line modelling loop**: `uses: {modelling: {use: modelling}}` (f8f9f7b, from `modelfix`).
- **YAML 1.1 readings** warned (`yaml-1.1`); **`where:` compares typed JSON**; **listing projects writes nothing into
  them**; **`try_use` trials stop what they started**; **the three load-sensitive tests** wait for conditions (all
  f8f9f7b, from `modelfix`).
- **Event-driven counts, a scheduler, evaluation of what changed**; **latency: push intake, notify-on-write, a local
  socket** (96f02d9, from `scale2` and `latency`).
- **What each run costs**, and **per-run cost and resources on the Agents page** (251df28, from `runcost`; network
  bytes per process left out).
- **Process view: drag, pin and re-route** (4aa1bc0, from `procdrag`).
