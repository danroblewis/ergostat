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

- **Built-in join** (open; relations make it a rule over `parent`/`children`): move a parent item once all its
  children reach a state (fork-join). Relations (merged, c4888bd) now say which items are a parent's
  children, both ways, from the item index, so the join is a rule on the kind (`join: {children: parent, all: done,
  to: shipped}`, say) rather than a block that lists and matches items itself (`examples/roadmap/bin/epics.py`
  does it today; elsewhere it takes a join block or an auxiliary). Left: the rule's shape, when it fires (on each
  child's move, from the index), and the parent's `entering` counted like any other move.
- **Relations, what is left** (open; the first part merged as c4888bd from `relations`): the Graph and Timeline read
  relations as they stand now (time travel does not reach them) and are not in a snapshot; the projection does not
  level resources (a block's `pool`); `ticket-factory` does not record Jira's links yet; the Process view does not
  draw relations.
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
- **A cause for a scheduled run's events** (open): a block on `every:` runs caused by nothing, so a sweep that opens
  sub-items draws no fan-out in the Process view; an event line cannot name its own cause (`causedby`).
- **Triggers on an event type** (open): a block started by an event type alone, not only by a state change.
- **Closed-loop simulation** (open): projection holds blocks still; simulating with the controllers running.
- **Operating modes, regime-scheduled thresholds, interlocks, risk gating** (open; designed in
  `docs/proposals/coordinator/08-modes-and-protection.md`).
- **Observer staleness and estimated stocks** (open; `coordinator/06-observer.md`).
- **Per-item and per-kind goals** (open).
- **Finding structure from residuals** (open; porting SD Lab's Kalman-LNA work; `parity/00-modeling-review.md`).
- **Proposals drawn dashed in both diagrams; proposals that state the behaviour they predict** (the dashed drawing in
  progress, `redesign`; the stated behaviour open).

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
- **Extreme-conditions tests and calibration per part of the model** (open; the Check page's first status
  takes 13 s even on small models).
- **An engine per system; line routing for large diagrams** (open; `docs/proposals/scale.md`).
- **The IR and a Rust runtime** (open; `docs/proposals/ir-and-runtime.md`, 12 questions for the owner).
- **A run whose lease expired is killed** (done, 5fa37de, `leasekill-only`; the owner decided 2026-11-18; SPEC §9.5
  *Fencing*): TERM to its process tree, KILL after a grace, `ergostat.run.killed`; its cost recorded, its item retried.

## Interface

- **Light theme: the repeats toward the paper are low in contrast** (open; found fixing the dark theme's): the third
  round of correspondence colours (`--g-fade`, 55% of the hue) stands 1.6:1 to 2.5:1 on white, and `--g9` (gold) 2.4:1
  as it is; WCAG asks 3:1 for graphics.

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
