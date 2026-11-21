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
- **Shared libraries** (parked on `libraries`, `docs/roadmap/overnight/libraries.md`, *Where it stopped*): templates
  and reference models shared between projects and people, by git URL or package, with versions, bringing their own
  scripts. For people modelling their own real systems. **Unblocked on the sandbox side** (`sandbox`, SPEC §12q): an
  untrusted library's scripts can now run in the allowlist sandbox, with no reads of the owner's files and network
  only to hosts the owner lists. *Still needed:* the trust gate rebuilt on **provenance** (a value counts as the
  owner's only if it arrived by substitution of a `type: command` parameter, the marks kept through nested uses;
  equality to an owner's literal is not enough); the refusal not telling agents to copy commands into `with:`; a
  library's `example:` and `reading:` marked untrusted wherever an agent reads them; `ask:`, `query`/`source` gated and
  a minimum `every` for untrusted libraries; `fetch` refusing a lock entry without a tree, symlinks hashed explicitly;
  then running untrusted library scripts through `ergostat.sandbox` and the rebase onto main.
- **External event logs** (open): systems that keep their own event log (Kafka, a ticket history, an incident
  log): copy in (works today through collectors), read in place, or mirror with a cursor that cites the
  original. Remote systems are the first case of reading in place.
- **Identifying existing controllers** (done on `identify`; SPEC §12d, *Existing controllers*): an external block's
  `identify: {input, output}` fits on-off, proportional, PI and three-position step (floating) laws with a delay from the
  record, picks one by held-out error with a parsimony penalty, runs it in the closed-loop projection, draws it in the
  block, and says `external-unidentified` and `external-not-run`. Validated on a synthetic HPA-like stepper and an alert
  rule (`~/orchestra-kube-sim` is not on this machine). *Left*: **`external-law-changed`** (someone retuned the
  controller): comparing each half's numbers fired on unchanged controllers (alert 24/30 seeds, HPA 7/30), and a
  held-out test of two laws against one still did on a few, so it was dropped; it needs a test on counts of moves
  mistold, with a false-positive rate measured over seeds. Also the library of known laws (`law: kubernetes-hpa`,
  declared and tested against the record), the HPA's multiplicative rule as its own family, the risk sampling the law's
  numbers, a closed-loop identification free of the bias (an instrument, or the delay told apart), and a run against the
  kube sim.

## Running code ergostat does not trust

- **The Linux sandbox's attack suite asserted macOS behaviour in five places** (done; `linuxfix`, 2026-11-19). Each
  has a Linux form beside the macOS one, which is unchanged: DNS fails and nothing reaches a listener outside on both,
  and on Linux a send to 127.0.0.1 is allowed only because the run has a network namespace of its own (checked, with
  no route out); the process list and environment are read from the run's /proc, which shows only its own pid
  namespace (the environment test is a strict xfail on macOS only); listing the toolchain's parents shows only the
  folders bwrap made to mount what is allowed; the pid hopper's parent on Linux is bwrap's init, which a signal from
  inside never ends, so the run reports the program's own exit. 31 of 31 pass in the dev container (they run only
  under `scripts/in_container.sh --sandbox`).
- **An allowlist sandbox** (done on `sandbox`, SPEC §12q, `docs/SECURITY.md`): `ergostat/sandbox/`, reads only the
  copy, the toolchain and declared paths; writes only the copy (not `.git`) and a private temporary folder; network
  only through a filtering proxy (listed hosts, SNI checked, methods for plain HTTP, every connection logged), no DNS;
  every process killed at the end; no markers in the environment; git run by ergostat with its dangerous settings off
  and the copy's pointers verified. The attack suite (`tests/test_sandbox_attacks.py`) blocks every finding of the
  repair and libraries reviews, and the branch's own review (pid hopping, a ClientHello split across records, wide
  toolchain reads, the process table). *Left*: on macOS another process's argv and environment stay readable
  (`kern.procargs2` is not mediated by the sandbox for the same user; closing it needs a uid per run, an
  administrator's setup), recorded as a strict expected failure; the suite runs on macOS and, in the dev container,
  on Linux; no CPU, memory or disk limit beyond the time limit and `RLIMIT_NPROC`; repair uses it (`repair2`),
  libraries does not yet.
- **Repair** (SPEC §12r; `docs/roadmap/overnight/repair2.md`): **built on branch `repair2`** (not merged): triage into
  `ergostat.failure` (sealed: M1), the fix by an AI with no tools in a disposable clone with its own `.git` (X1), tested
  in `ergostat.sandbox` (X2, M2, M3; a read-only re-run's hosts GET-only, M6), proposed as `apply-fix` with its impact
  report, the ladder's first rung (a person; a denial final), a daily cap that fails closed
  (M7), and applying by `--ff-only` onto the commit it was made on (M8). M4 is designed away (a fix changes only the
  program). *Left*: verifying a fix by the runs after it and offering its revert; per-run logs and log events; the
  swallowed-errors check (M5); the ladder's lower rungs (narrow AI, program, rule) and promoting a class automatically;
  failures from tracebacks of other languages; a program with uncommitted changes is fixed from its committed text; two
  runs of one block at once share the block's log, so a failure's stderr may hold the other's lines.
- **AI approver for repairs: needs a positive allowlist of the AST changes a fix may make** (SPEC §12r). One was built
  on `repair2` (the AI shown only the diff and pass or fail, behind a guard that escalated new imports, processes,
  network, environment, writes and URL or path literals) and cut before merging: a guard that denies by list was
  bypassed many ways in review: `vars(os)['sys'+'tem']`, `sys.modules[...]`, `().__class__.__subclasses__()`, an
  existing `subprocess.run` given `['sh', '-c', x]`, calls it did not list (`os.chmod`, `Path.rename`, `marshal`), and
  relative path literals. A sound guard says what a fix may change (the shapes of expressions and names it may touch)
  and refuses the rest; until then `approver: ai` is refused by `check`.

## Modelling

- **System architecture review** (computed measures done on `architecture`; design in
  `docs/proposals/architecture.md`): `check` notes `system-splits`, `systems-merge`, `interface`, `time-scales` and
  `purpose`, and each system's size (and whether it is nearly decomposable) in `explain`, its size on its panel; a model-level `purpose:`. *Left*: the relative gain
  array (needs a square, non-singular gain matrix from approved step tests), eigenvalue elasticity and aggregation from loop dominance, interface
  stability over the model's history, the Viable System Model checklist and purpose coverage (the AI rung), and the
  per-system redesign and daily larger-model review (after `redesign`).
- **Built-in join** (done, de204df and 966a07f, on `causes-join`; SPEC §5a, *Join*): `join: {children: REL, all:
  STATE, to: STATE}` (or `any:`) on the parent's kind, fired on each child's move from the item index, the parent's
  move recorded as `ergostat.item.joined` caused by the child's, folded only forward and counted like any other;
  `examples/roadmap` uses it in place of `bin/epics.py`. *Left*: the Blocks view does not draw a join (a rule on a
  kind, not a block); each child's move reads all its parent's children (O(children) per move: fine for an epic's
  tickets, not tuned for thousands).
- **Relations, what is left** (open; the first part merged as c4888bd from `relations`; the Process view draws them,
  done in 0f7f870 on `smallgaps`; the Graph and Timeline at a moment travelled to, and in a snapshot, done on
  `relations-as-of`): `ticket-factory` does not record Jira's links: its collector does not read them (`bin/jira.py`
  asks Jira for summary, status, labels and description only), so `issuelinks` and `parent` must be asked for and
  folded as relations first.
- **A kind chosen in a snapshot** (open; found on `relations-as-of`): a snapshot holds the Items page's list with no
  kind chosen only (`items`, not `items?kind=K`), so choosing a kind in it says "not in this snapshot", and the
  Graph of one kind it holds (`items-graph?kinds=K`) is not reached from the page.
- **Resource levelling and completion estimates** (done, on `eta`; SPEC §5a, *Completion estimates*): the
  projection levels resources now: each open item's p50 and p90 finish from a Monte Carlo over every open item (a
  block's capacity, its recorded runs and rework, time in a state by Kaplan–Meier given the item's age, the
  record's paths, dependencies and arrivals); the Timeline's lanes, the list's *done by*, the item's why. Left: a
  goal's gate on a block is not simulated, and a capacity no block declares is not modelled (a block's `workspace:`
  pool is: held from the item's first take until it finishes).
- **Modelling improves the model** (landing, `modelling-core`; `docs/proposals/self-improvement.md`): what `check`
  finds is held as requests (`ergostat.modelling-request`); the rule tier (units, a queue's goal, a process nobody
  identified) and the AI tier (off unless `ai: true`), each a block of `use: modelling`, answer them with ordinary
  changes, checked in the tier's own process; the judge decides by class (description, unit, rename judged by check;
  values, equations and structure by the record). Every example uses it. Parked on `selfimprove` (its definition file
  says why): the rule tier's first-order equations, event-type renames that edit programs, the rule tier's copies of
  the chain fixes.
- **Redesign beside refinement** (landing, `modelling-core`; `docs/proposals/redesign.md`): one change set of many
  coordinated edits for a whole system, made over a few rounds on a scratch copy by the redesigner (an `ai` block,
  haiku by default, within a budget a run and a cap a day), judged as a whole by a scorecard, one
  `ergostat.model-change` of kind `redesign`, drawn dashed on both diagrams, never written without the owner unless
  `accept: {redesign: auto}` (and never one that removes, rewires or changes control). Runs on its own a system at a
  time when it is due (the owner's decision, 2026-11-19: `when: auto` by default), or when the owner asks. Open: removed parts are named, not drawn as ghosts; splitting a model into systems is
  in the guide but not scored; the judge scores a redesign on the record it has when it takes it up.
- **Craft notes in `check`** (done, `modelling-core`): a part with no description, a stock with no unit, a flow
  between stocks with no equation, an undescribed collector, event types in mixed forms, a takes queue's goal with a
  tolerance (a step whose goal never goes off), a `process:` with no `identified:` (`spec/craft.py`, notes, not
  counted as findings).
- **Proposals superseded by any edit** (done, `churn` and `proposals-superseded-by-any-edit`; owner, 2026-11-19): a model change made against a version
  since changed, even only in its numbers, was superseded and never written (SPEC section 12e); and every pass of a
  finder made a new change for the same thing, letting the last go ("let go: found again otherwise, or no longer
  found"), the estimator letting go of loops' processes too. **Done:** ergostat's own changes are what they are about,
  revised in place when found again with new numbers; carried to a new version when their subject is unchanged (a
  value's or an equation's edit made again on the files as they are); superseded only when their subject was edited or
  removed, their edit cannot be made again, or their finder no longer finds them, saying which. `modelling-core` makes it one
  mechanism: `rebase` moves the waiting edits' lines, and `supersede` carries ergostat's own (subject unchanged) and a
  description, unit or redesign whoever made it (its edit still applies). `proposals-superseded-by-any-edit` carries the
  rest: a block's values, equations and structure (it records a `subject`), and changes under test or passed (back to
  testing, their verdict cleared, judged again); a structural change whose lines moved takes the edit its finder finds
  again, on the same item. Every carry, the finders' writes, Dismiss and the judge are decided under the proposals' lock
  on the model as its files are now, and defer while the files do not compile or differ from the model read; a change
  made again on a superseded id keeps nothing of the old one. Still superseded: a block's equation or structural edit
  whose lines a hand edit moved (the block's to make again).
- **Poor identifications proposed, projections drawn as sure** (done, `churn`; owner, 2026-11-19: a loop's process that
  followed 2% held out was proposed, and the projections after a burst of 130 tickets were far off): a process is
  proposed only past a quality floor (what it follows held out, white errors in closed loop, independent of u), else
  the goal says `loop-not-identifiable` and what would identify it; the process is identified around a large outside
  step (a burst of arrivals), closer to the truth than from the loop working; the strip leads with "Low confidence"
  and widens the band where the parts it rests on fit badly. **Left:** a burst's window is chosen from y's own
  excursion (where it comes half way back), not from the process; several outside steps are not yet fitted together as
  experiments; the projections do not yet suggest the missing structure (capacity) themselves.
- **The judge almost never decides on a slow model** (owner, 2026-11-19: on the work model nearly every change is
  inconclusive, a few refused, none accepted; partly done on `slowjudge`, docs/roadmap/overnight/slowjudge.md; SPEC
  §12e): a change had to gain 2% in every window of at least twice its stock's time constant, above an absolute noise
  floor, so on a slow or noisy record each window was one noisy draw (measured: a change a fifth worse passed in 6 of
  20 records, one a fifth better failed in 11 of 20). *Done*: one replay of each over the whole record held out, the
  noise taken from the record about the better replay (AR(1), or a walk for a stock with no time constant), and a
  plug-in confidence sequence (a normal mixture, valid under that noise model) with its error
  rate stated (a change no better passes at most 5% of the time, however often looked at); an undecided change says
  about how much more record it needs and stays under test up to seven times the record it needs (a day at least); a
  change whose replay is the same as the model's waits for record in which it moves, rather than three hold-outs.
  Measured after (20 records each, a week of record): no worse change passed (0 of 60), 3 better changes failed in
  80, a drain twice off decided within a week, most changes a fifth off still undecided after one. *Left*: on a
  record as slow as the information allows (a fifth off a day-long drain) most changes still need more
  than a week; a change that cannot move the replay (structure, wiring, descriptions) should be judged by structural
  measures (as redesign's scorecard does); and a change should carry over edits elsewhere (above).
- **A cause for a scheduled run's events** (done, e4800ea, on `causes-join`; SPEC §5b): the run is the cause its
  events cite (no `ergostat.schedule.fired` event per firing); the Process view draws each scheduled block in a
  **schedules** frame with its fan-out. *Left*: an event line still cannot name a cause of its own (`causedby`).
- **Triggers on an event type** (done on `triggers2`, after `triggers` was parked; SPEC §9.3, *Started by an event*):
  `on: {event: TYPE, where:, emits:, max-age:, most:}`, a run per event; loops refused when the model is read
  (`trigger-loop`, any length) and stopped at run time by the depth every run carries, whatever started it (8 at
  most, `trigger.stopped`); a breaker per block (`most:` a minute, reset by the owner); advise asks per event, answers
  naming their ask; lookups by id and prefix types indexed. *Left*: a relay outside ergostat that drops `causedby`
  is caught only by the breaker; `max-age` reads the event's own clock.
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

- **Linux: two bugs the dev container found** (done; `linuxfix`, 2026-11-19). (1) The segmented event log
  (`ergostat/segments.py`, `_sync`) noticed new sealed segments by the directory's mtime alone, and Linux timestamps
  are coarse (one jiffy: 50 file creates on tmpfs gave one mtime), so a seal within the same tick was missed and its
  events vanished from queries. Now every seal, roll-up and prune replaces a `layout` token atomically under the lock,
  and a reader that sees it change lists the segments again and reads the head from its start (the head's inode is
  not trusted either: a file system reuses it). The mtime is still compared, for a writer that keeps no token.
  Tested with seals forced into one mtime with `os.utime`. (2) `shell=True` runs `/bin/sh`, which on Debian is dash,
  and dash forks for `sh -c CMD` where macOS's bash execs: the pid recorded for a daemon was the shell's. Now a
  daemon's command that is one simple command is run with `exec` (`daemons/proc.py`, `execd`); anything else keeps
  its shell, and either way the pid leads the daemon's session, so kills reach the program through its group.
- **Warm workers instead of a process per item**: superseded by daemons (branch `daemons`, SPEC §9.7,
  `docs/RUNTIME.md`): long-lived processes for blocks and sensors, many items at once, every line tagged with its run
  or request, env per item in its line, supervised (crash, silence, stdin backpressure, restart storms, cancel on a
  lease's expiry, drained on a swap). The `warm` branch stays parked as reference (its definition file,
  `docs/roadmap/overnight/leasekill.md`, says where it stopped); its review's findings were taken as lessons: B4 (a
  `done` for another item) by tagging, B1 (env leaking between items) by env in the line, B3 (a child's CPU never
  charged) by charging no item CPU at all (the daemon's own CPU and memory are sampled and shown); a `warm: true`
  daemon now charges it per item (*Done recently*).
- **A renewing run killed because the engine was busy recording its renewal** (parked on `leaserenew`,
  `docs/roadmap/overnight/leaserenew.md`, *Where it stopped*). A renewal through the engine's socket is recorded only
  when the engine gets the GIL; the watchdog could expire the lease first and kill a run that asked in time (16 of 32
  killed with a GIL-holding thread in the engine, 0 of 48 on the branch). The branch adds a grace and a second look,
  a re-read before the write, and a fold refusal that the raw readers honour; parked because its
  `refused_expiries` folds each expired item uncached, transcripts included, on every measure sample and estimate
  read. Still needed: read `refused` from the item index, and a performance test with many expired items and long
  transcripts.
- **Daemons, left over:** a daemon's lines are taken one at a time (a run's process batches the lines that arrive
  together into one write); a sensor daemon's observations (event lines about items, as a `run:` sensor may print) are
  not taken; a daemon's CPU is sampled every 30 s, so a daemon that lives less than that is measured only when it
  ends.
- **Daemons across the engine's own restarts** (follow-up, found in `tf-daemons`' review): the paths that start the
  engine's process again in place (`_restart` and `_restart_hard` in `ergostat/cli/running.py`: an exec for a new
  model's name or store, and the watchdog's last resort after `runner.kill_all()`) do not stop the daemons first. A
  daemon reading its standard input sees it end when the old process goes and exits, but nothing waits for that,
  drains its runs or ends its process group, so a daemon that ignores the end of its input, or a child it started,
  can outlive the engine.
- **Daemon YAML schema review** (open; owner, 2026-11-19): the functionality landed (`daemons`, `daemons2`; how to
  use and write daemons: `docs/DAEMONS.md`, the skill's `daemons.md`), but the owner is not sure the YAML is the
  best yet, and it may change. Alternatives worth considering:
  - *a modifier instead of a kind*: `run: python3 probe.py` plus `keep: true` (or `mode: daemon`), so moving a
    sensor over is one word and the command stays where it was, rather than `daemon: {run: ...}` as a seventh
    sensor kind;
  - *per-sensor arguments*: today a shared daemon works out what to read from the sensor's name (`orders.main` is
    the `orders` queue), so names carry configuration; a sensor's own `with: {queue: orders}`, sent in its read
    line, would free the names;
  - *where shared daemons are declared*: a top-level `daemons:` beside `agents:` (SPEC §10, the machine several
    blocks share), or a daemon as an agent's process (`agents: {svc: {kind: program, daemon: {...}}}`), which
    would show it on its rung like every other agent;
  - *the names of inline daemons* (`sensor.STOCK.SENSOR`, `block.NAME`), derived and dotted, used by
    `ergostat block NAME --restart` and in logs;
  - *push*: `push: true` beside `daemon:` on the sensor, or said once by the daemon (it pushes for every sensor
    that names it);
  - *the knobs*: `concurrency` beside the block's `pool` (two limits on one thing); `restart.backoff` as a
    two-item list against `backoff:` and `max-backoff:`; `stdin-timeout`'s name; a heartbeat on by default for
    block daemons;
  - *the word*: "daemon" is Unix jargon; `runner`, `server` or `keep-alive` may read better to the owner's users.
  Whatever changes, the protocol (SPEC §9.7) need not: these are only how the YAML says which process and how it
  is supervised. The docs' examples are run by `tests/test_daemon_docs.py`, so a schema change shows every place
  to rewrite.
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
    (done on branch `cli-fallback`, `docs/roadmap/overnight/cli-fallback.md`: the engine keeps the model it takes as
    one content-addressed snapshot of every file its loading read; commands that read load that snapshot alone,
    never running anything; commands that act, `event --add` among them, refuse naming the YAML's error).
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

## The factory (ergostat on ergostat)

- **The factory's AI sessions in the dev container** (open; from `factory`, `docs/roadmap/overnight/factory.md`): the
  implementor and the reviewer run `claude -p` on the host, held by their pool caps, the daily dollar cap and the load
  interlock, with Claude Code's allowed and disallowed tools (no OS sandbox). Inside the container they would get the
  kernel's limits, but a session there needs three things it lacks: Claude Code itself (the image has no Node and no
  Linux build of it), a sign-in (the host's is in the macOS keychain; a container would need a token,
  `CLAUDE_CODE_OAUTH_TOKEN`, as a secret mounted in), and a way out to the API alone (the container has no network,
  and `--net` opens all of it). ergostat's filtering CONNECT proxy (`ergostat/sandbox/proxy.py`, which can listen on a
  Unix socket) is the right filter, but Docker Desktop on macOS does not carry a host Unix socket into its VM, so the
  proxy would have to run inside Docker: a second service on an `internal: true` network, the only one with a route
  out, allowing `api.anthropic.com:443` (CONNECT, its TLS server name checked). Left: that service, the token's
  handling, Claude Code in the image, and a measured run of one session inside.
- **A block's pool set by the model's state** (open; found by `factory`): `pool:` is a number written in the YAML, so
  the factory's pools, ramped up on good results, are stocks (`implementor-pool`) its gates and runs enforce below the
  block's `pool:` (the most). The completion estimates and the Blocks view read the most, not the pool now. Either
  `pool: stock.NAME` (read at each dispatch, drained when lowered, as a lowered `pool:` is), or a block's pool as a
  setting a controller steps.
- **`mode: advise` on a block that takes items does nothing** (open; found by `factory`): the dispatcher
  (`ergostat/leases/dispatch.py`) leases items to a block whatever its `mode`, and `check` does not say so; only
  commanded and event-started blocks ask. The factory pauses its implementor with a gate instead (the auxiliary
  `intake-open`, read by hand, in an `expr` that commands it). Either ask once per item before it is leased
  (`block.advised` naming the item), or refuse `mode: advise` with `takes:` in `check`.
- **A gap continues an existing branch, with main merged in by the factory** (awaiting its gate; branch
  `factory/continue-branch3`, the salvage of `continue-branch`; its definition is
  `docs/roadmap/overnight/continue-branch.md`, and `continue-branch2.md` and `continue-branch3.md` hold where the later
  rounds stopped). A request may name `continues: <branch>`;
  implement.py merges origin/main before each session (a clean merge committed by the program, a conflicted one handed
  to the session with its conflict list), and gate 1 reads the continued branch's own definition and holds it to the
  main merged at its build. Main (1f013ba) is merged into the branch. Left: the factory's fast suites on the merged
  tree, and gate 1 for this salvage, which the coordinator judges by hand (its first commit is continue-branch.md).

## Done recently

- **Warm processes for blocks** (done on `factory/warm3`, finishing `warm2` and `warm3`, each parked after two failed
  gates; SPEC §9.7, `docs/roadmap/overnight/warm2.md`): `warm: true` on a daemon, a declared promise that the program
  keeps no state between runs: `concurrency` processes, one run each at a time, each run charged its process group's
  CPU (its reaped children's included); a process that misbehaves is restarted, one cancelled or past `recycle:`
  replaced; `ergostat block NAME --check-warm FILE` tests the promise on one input. `main` (f158e00) was merged in on
  2026-11-20 (2ca24c7), and the factory's gates ran the four suites on the merged tree (f2f1891) and passed them, as
  review/warm3-3 reports. Measured: 100 items through five steps at `pool: 10`, end to end p50 0.57-0.81 s warm
  against 1.31-1.34 s a process per item (89-116 against 49-56 items a second).

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
