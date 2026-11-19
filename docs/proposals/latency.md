# Latency: a workflow's steps as fast as they can go

Status: measured and built 2026-11-18 on the `latency` branch (on `scale2`). The numbers are in
`docs/proposals/latency-results.jsonl` (one line per run, with the load average when it was taken), made by
`scripts/latency_bench.py`. "Before" is `scale2` as it stands (commit 9e087c5 of this branch: the benchmark and
nothing else), run from a worktree of its own; "after" is this branch.

## The question

The owner's alert-triage bots at work take 2 to 3 minutes; a person often gets there first. The Process view's Times
show hops of about 52 seconds in ticket-factory. The target: 100 to 500 items at once, and a workflow's time of 1 to
10 seconds apart from the time outside it that nobody here can shorten (an AI thinking, CI, GitHub, a person).

## The answer, short

- **ergostat's own part of a hop was a quarter of a second, and is now about 10 ms.** A 5-step workflow whose steps
  do nothing took 1.3 s for one item, 1.25 s of it the dispatcher's quarter-second look at the record, five times.
  Woken by the write instead, the same item takes 0.07 s end to end.
- **At 100 to 500 items at once, the bound is now starting a process per step**: about 280 step runs a second (3.5 ms
  of the engine's time each, most of it `fork` and the run's own events). 100 items through 5 steps take 1.4 s (p50)
  and 1.7 s (p95); 500 take 6.1 s and 9.4 s, at 52 items (260 hops) a second, where they took 7.3 s and 11.7 s. The
  next step, a step that stays running (below, designed and not built), removes the process per item.
- **Arrivals no longer wait for a poll.** `POST /api/events` (or a webhook mapped per sender) records and folds them
  at once: 500 events in 9 ms, and the first step takes them within milliseconds. A collector polling every 3 s
  added a second and a half on average before.
- **A step's calls no longer load the model or poll.** `ergostat act` took 0.6 s, mostly two half-second polls (the
  engine looking for approvals, the call looking for the result); over the engine's socket it takes the CLI's own
  start (0.07 s), and 0.6 ms from a step's own code.
- **ticket-factory's 52 seconds are people, pools and fixed waits, not ergostat.** Offline, a ticket's time is
  34 to 42% the owner's stand-in approving gated actions (every 5 s, one at a time: `open-pr` waits for four), 30 to
  39% steps that gave the ticket back and waited (mostly `work` finding no free workspace, then the reviewer, then
  CI), 14 to 18% waiting to be taken (mostly `work` again: three workspaces, each held for its ticket through review
  and CI, and the AI's one seat), and 2 to 4% the steps' own work. With the timings it has at work (`POLL_EVERY`
  15 s, a reviewer who takes 2 minutes) the mean hop is 23 s with three tickets and the review step alone 127 s; the
  queue for workspaces grows with every ticket more (the slowest hop here, 3.5 minutes in `located`). The owner's
  52 s was not reproduced exactly; it is of this make. ergostat's own part (dispatch, the
  engine running an approved action, the call seeing it ran) was 1 to 2% and is under 0.5% now. **With every gate
  promoted to `auto`, a ticket took 43 to 53 s before and takes 28 s now, 18 s of it the reviewer and 4.5 s CI: the
  other ten steps take 0.1 to 0.5 s each.** What this branch changed there: a step that waits is woken by the news it
  waits for (a webhook), or looks again after 1 s, 2 s, 4 s instead of a fixed 15 s; its calls go over the socket;
  the first step sees its ticket at once. What it cannot change: the people (the approvals, the review) and the
  pools the factory is given.

## How it was measured

`scripts/latency_bench.py synth N`: a model with one item kind (`job`, states s0 to s5) and five program blocks, each
taking the jobs in one state (`takes:`) with a `pool:` of min(N, 100), and printing the event that moves them on; each
step is a zsh one-liner that notes its own start (`$EPOCHREALTIME`) and does nothing else. N jobs arrive at once, by
one of three intakes: written into the record from outside (`record`: what `event --add` does, without its model
load), a collector sensor polling a spool file every 3 s (`collector`), or one `POST /api/events` (`push`). Each hop
of each job is read back from the record:

| part | from | to |
|---|---|---|
| intake | the arrival (the benchmark's clock) | the event recorded |
| dispatch | the item in its state, and free (the last lease ended) | `ergostat.lease.taken` |
| spawn | the lease taken | the step's process running (its own clock) |
| run | the process running | its event recorded (the item moved) |
| release | its event recorded | the lease ended (the next step may take it only then) |
| hop | the item free in its state | free in the next |

`factory`: examples/ticket-factory copied and run offline (fakes for Jira and GitHub, the stand-in AI, the scripted
teammate as reviewer and, offline only, as the owner approving every gated action), until N tickets are closed.
Per step: the wait to be taken, each run's length, and inside the run the gated actions (the approval, the engine
running it, the asker seeing it ran) and the rest (the step's own work: Python, `ergostat item`, git, the fakes); the
runs that gave the ticket back (`Wait`) and for how long. `--set POLL_EVERY=15s --set REPING_AFTER=90s --set
TEAMMATE_AFTER=120s` runs it with the timings it has at work. `calls`: what one `ergostat item`, `event --add`,
`act` and `lease --renew` cost from inside a run.

Every run sampled the engine's threads and memory every 2 s and would have killed it above 1,500 threads or 6 GB;
none came near (the most seen, 137 threads). Nothing ran while an earlier run's engine was alive. The machine: a
28-core Mac, load 3 to 15 while these ran.

## Before and after: the 5-step workflow, steps doing nothing

| run | N | pool | intake | end to end p50 / p95 | intake | dispatch p50 / p95 | spawn | run | release | hop p50 / p95 | items/s |
|---|---:|---:|---|---|---|---|---|---|---|---|---:|
| before | 1 | 1 | record | 1.30 / 1.30 s | 0.1 ms | 252 / 254 ms | 7.5 ms | 1.9 ms | 0.5 ms | 262 / 263 ms | 0.8 |
| before | 50 | 50 | record | 0.96 / 1.86 s | 0.2 ms | 130 / 524 ms | 10.8 ms | 4.5 ms | 4.0 ms | 150 / 542 ms | 27 |
| before | 100 | 100 | record | 1.63 / 2.63 s | 0.3 ms | 269 / 579 ms | 11.1 ms | 4.7 ms | 4.5 ms | 290 / 598 ms | 38 |
| before | 500 | 50 | record | 7.30 / 11.70 s | 0.9 ms | 234 / 7,796 ms | 11.9 ms | 5.0 ms | 5.1 ms | 257 / 7,821 ms | 40 |
| before | 50 | 50 | collector (3 s) | 1.98 / 2.89 s | **1,006 ms** | 128 / 552 ms | 10.9 ms | 4.3 ms | 4.2 ms | 149 / 568 ms | 17 |
| after | 1 | 1 | record | **0.07 / 0.07 s** | 0.1 ms | **2 / 8 ms** | 6.7 ms | 1.7 ms | 0.6 ms | **10 / 21 ms** | 15 |
| after | 50 | 50 | record | 0.71 / 0.90 s | 0.2 ms | 135 / 280 ms | 11.1 ms | 4.4 ms | 3.8 ms | 154 / 298 ms | 55 |
| after | 100 | 100 | record | 1.42 / 1.73 s | 0.4 ms | 285 / 312 ms | 10.8 ms | 4.3 ms | 3.9 ms | 305 / 333 ms | 57 |
| after | 500 | 50 | record | 6.44 / 9.68 s | 1.0 ms | 654 / 5,652 ms | 11.7 ms | 4.7 ms | 4.3 ms | 674 / 5,672 ms | 51 |
| after | 500 | 100 | record | 6.31 / 9.69 s | 1.8 ms | 419 / 4,649 ms | 11.7 ms | 4.7 ms | 4.3 ms | 442 / 4,670 ms | 51 |
| after | 1 | 1 | push | 0.09 / 0.09 s | 25 ms | 2 / 8 ms | 6.7 ms | 1.7 ms | 0.6 ms | 10 / 21 ms | 11 |
| after | 50 | 50 | push | 0.70 / 0.85 s | 1.4 ms | 110 / 320 ms | 10.3 ms | 4.0 ms | 3.6 ms | 131 / 340 ms | 58 |
| after | 100 | 100 | push | 1.43 / 1.66 s | 6.0 ms | 279 / 333 ms | 10.1 ms | 4.0 ms | 3.5 ms | 297 / 352 ms | 60 |
| after | 500 | 100 | push | 6.14 / 9.36 s | 8.7 ms | 422 / 4,569 ms | 11.3 ms | 4.5 ms | 4.2 ms | 445 / 4,587 ms | 52 |

Reading it:

- **One item: the dispatcher's look was the whole hop.** 252 ms of each 262 ms hop was waiting for the dispatcher's
  next look at the record (every 0.25 s, `LOOK`, and the look began just after the write it was waiting for). Woken by
  the write, the dispatch is 2 ms, and the hop 10 ms: 7 ms to start the step's process (`/bin/sh`, then zsh), 2 ms
  for it to print and for its line to be recorded, under 1 ms to end the lease.
- **Many items: the dispatch is a queue.** At N = 50 and 100 a hop's dispatch is the time to take the items ahead of
  it: the dispatcher takes one item at a time (0.4 ms each alone), and in the engine each take starts a run whose
  `fork` and first events compete for the same interpreter, so a burst of 100 takes 0.3 s. That is why the p50 at
  N = 100 hardly moved (1.63 → 1.42 s) while the p95 did (2.63 → 1.73 s) and the spread closed: before, an item
  could also miss a look and wait a whole quarter second more.
- **500 items: throughput.** The engine does about 280 hops a second (52 items through 5 steps), about 3.5 ms of
  its single interpreter's time per hop: the `fork` of a ~100 MB process, the run's thread, and six events (taken,
  started, the step's event, ran, ended, the valve). 2,500 hops is about 9 s of it; items pipeline, so the median
  item takes 6.1 s and the last 9.4 s. The pool hardly matters (50 or 100: the same), the engine does. Before, the
  same burst ran at 40 items a second: each idle look cost a quarter second of nothing.
- **Arrivals.** Pushed, 500 events are recorded in 9 ms (one request, one write) and folded when the dispatcher
  wakes. A collector adds half its period on average (1.0 s here, `every: 3s`; ticket-factory's watcher is every
  10 s) plus its own run; collectors stay, for what nobody pushes.
- **Threads.** A run used three threads (its own, one writing its input, one reading its output: 100 runs at once
  were 305 threads, 500 would have been 1,500). It now uses one (100 runs: 125 threads, the engine's own 25 included):
  the run's thread writes its input and reads its output with a selector.

## Before and after: ticket-factory, offline

Three tickets, then eight, through the twelve steps; the factory's offline timings (`POLL_EVERY` 2 s, the reviewer
after 9 s, the owner's stand-in approving every 5 s, CI 3 s), and then with the timings it has at work.

Seconds per ticket seen (eight arrive in each run; "tickets" is how many were closed when the run stopped), by what
the time went to. "The reviewer" and "CI" are the time steps spent given back waiting for them; "capacity" is `work`
put off because no workspace was free, and runs waiting for the AI's one seat; "waiting to be taken" the rest of the
time between a ticket reaching a step and its run starting.

| run | tickets | end to end p50 / p95 | hop p50 / mean | approvals (a person) | the reviewer | CI | capacity (workspaces, the AI's seat) | waiting to be taken | the steps' own work | ergostat (running an action, the call seeing it ran) |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| before, offline | 3 | 117 / 126 s | 5.4 / 9.3 s | 27.4 | 4.5 | 3.0 | 26.6 | 14.4 | 3.0 | 1.1 |
| after, offline | 3 | 106 / 117 s | 3.3 / 6.8 s | 27.3 | 5.5 | 2.2 | 22.9 | 12.2 | 1.4 | 0.3 |
| before, offline, 8 tickets | 8 | 178 / 304 s | 5.6 / 12.4 s | 64.3 | 12.0 | 7.8 | 57.2 | 23.7 | 6.4 | 2.7 |
| after, offline, 8 tickets | 8 | 157 / 258 s | 5.2 / 11.0 s | 64.6 | 13.8 | 6.0 | 46.9 | 19.5 | 1.9 | 0.6 |
| before, work's timings | 3 | 253 / 263 s | 6.3 / 22.7 s | 26.1 | 50.6 | 11.2 | 106.6 | 22.4 | 3.2 | 1.2 |
| after, work's timings | 3 | 218 / 227 s | 3.3 / 19.1 s | 26.2 | 48.3 | 2.2 | 81.1 | 25.3 | 1.9 | 0.3 |
| before, every gate auto | 3 | 43 / 53 s | 2.2 / 3.5 s | 0.0 | 10.4 | 4.4 | 6.1 | 6.9 | 4.6 | 5.4 |
| after, every gate auto | 3 | 28 / 28 s | 0.3 / 2.1 s | 0.0 | 13.5 | 4.5 | 2.6 | 0.8 | 1.6 | 0.5 |

And each step's hop (median), with the timings it has at work, and with every gate promoted to `auto`:

| step | work's timings: before | after | every gate auto: before | after | what is left |
|---|---:|---:|---:|---:|---|
| pick-up | 5.8 s | 0.6 s | 3.5 s | 0.1 s | one approval; before, 2.9 s for the queue's next reading |
| locate | 0.4 s | 0.1 s | 0.5 s | 0.2 s | a `git fetch` |
| work | 0.4 s | 0.3 s | 0.8 s | 0.4 s | the stand-in (an AI session at work); tickets wait for a workspace before it |
| open-pr | 19.5 s | 20.0 s | 2.3 s | 0.3 s | four approvals, one after another |
| ask-review | 5.1 s | 4.8 s | 1.2 s | 0.1 s | one approval |
| review | 126.6 s | 125.7 s | 12.1 s | 14.2 s | the reviewer (2 minutes at work's timings, 9 s offline, then the teammate's 5 s round) |
| address | 19.5 s | 20.4 s | 1.6 s | 0.5 s | two approvals, the AI's seat |
| sail | 4.5 s | 5.4 s | 0.6 s | 0.1 s | one approval |
| ci | 15.6 s | 3.3 s | 5.1 s | 3.2 s | CI (3 s offline) |
| fix-ci | 9.4 s | 16.8 s | 1.6 s | 0.5 s | two approvals, the AI's seat |
| merge | 4.8 s | 1.8 s | 0.6 s | 0.1 s | one approval |
| close | 10.2 s | 10.2 s | 1.4 s | 0.2 s | two approvals |

With people approving, a ticket's time hardly moves (117 → 106 s offline; 253 → 218 s with work's timings): it is
the approvals (27 s a ticket), the reviewer (50 s a ticket at work's timings), the workspaces and the AI's seat. What
moved is what was ergostat's and the factory's own: the steps' own work (3.0 → 1.4 s a ticket), ergostat's part of
the actions (1.1 → 0.3 s), CI seen within a second or two of finishing (15.6 → 3.3 s), the first step taken at once
(5.8 → 0.6 s). With every gate promoted (`--auto-gates`), what is left is outside time: a ticket takes 28 s, 18 s of
it the reviewer and 4.5 s CI, and the other ten steps 0.1 to 0.5 s each (before: 43 to 53 s, and 0.6 to 3.5 s a step).

### Where the 52 seconds go

The Process view's Times average the time between moves. In ticket-factory, what fills them, in order:

1. **People and their stand-ins (outside time).** Every outward act is a gated action at `approve`; offline the owner
   is played by the teammate, which approves what waits every 5 s, one at a time. A step that asks for four actions
   (`open-pr`: push, open the pull request, move the issue, comment) waits for four approvals in turn: 19 s.
   `close` two (10 s), `address` and `fix-ci` two each. At work a person approves, in minutes or hours. The review
   itself is the reviewer's: 9 s offline, 2 minutes (`TEAMMATE_AFTER`) or hours at work. **ergostat cannot shorten
   these; promoting a class of action to `auto` once it has proved itself is how the factory removes them**, and the
   `--auto-gates` runs above show what is left when every class is promoted.
2. **Fixed re-check intervals (ergostat's and the factory's).** A step that finds nothing yet (no review, CI still
   running, an action still held) gave its ticket back for `POLL_EVERY` (15 s at work, 2 s offline) and asked again.
   With work's timings a ticket spent 74% of its time given back: 62% of that `work` finding no free workspace (3,
   below), 31% the reviewer, 7% CI, each looked at again only every 15 s (10 s for a workspace). Now it is woken by the news it waits for (a webhook about the ticket,
   SPEC 5c and 9.5), and without news looks again after 1 s, 2 s, 4 s, ... up to `POLL_EVERY`; the review step looks
   again no later than its re-ping falls due.
3. **Capacity.** `work` waits for a workspace (3, each held for its ticket through review and CI until it is done)
   and for the AI's one seat (`at-once: 1`); a ticket that finds none is put off 10 s and asks again. With 8 tickets
   that was the longest hop (up to 3.5 minutes in `located`). The pools are the factory's to size, not latency.
4. **Waiting to be taken.** `pick-up` waited 2.9 s for every ticket: its block takes only when its goal ("nothing
   waits in new") is off, and that was seen at the queue sensor's next reading (`every: 3s`). The engine now reads
   every count of items when the record is written, so the goal is off as the ticket arrives: 0.03 s.
5. **The steps' own work**: 0.16 to 0.7 s a run, most of it starting Python and `ergostat item` loading the model (50
   ms for this model) and the `act` calls' polling; now 0.04 to 0.18 s, the calls over the socket.

## What each change bought

| change | where | what it bought (measured) |
|---|---|---|
| Woken by the write (`notify.py`): every write to a record tells its waiters in this process; other processes' writes come through the kernel (kqueue); the old periodic check is the fallback | the dispatcher, the approvals the engine follows, an `act` waiting for its answer | a hop's dispatch 252 → 2 ms; one item through 5 steps 1.30 → 0.07 s; the engine running an approved action at once instead of within 0.5 s |
| Counts of items read when the record is written (only those that changed are recorded) | a goal on a queue, so a block that takes items under a goal | ticket-factory's `pick-up` waited 2.9 s for its goal to see the ticket; now 0.03 s |
| An item put off is looked at again when it falls due | the dispatcher | a re-check of 1 s is 1 s, not up to 2 |
| One thread per run (`spec/stream.py`: a selector) | every block's run | 3 → 1 thread a run: 500 runs at once fit under the safety limit with room |
| Push intake: `POST /api/events`, webhooks by `intake: hooks:`, a token, localhost unless `intake: allow:` | arrivals and outside news | intake 1.0 s (a 3 s collector) → 1.4 to 9 ms; webhooks for Jira, GitHub and PagerDuty mapped in YAML |
| The engine's socket: `event --add`, `act`, `lease`, `item --json` answered without the model | a step's calls | `act` 0.60 → 0.075 s from the command line (its polling gone), 0.6 ms from a step's own code; `item`, `event --add`, `lease --renew` cost the command line's start (60 to 75 ms) instead of that plus loading the model (50 ms for ticket-factory, seconds for large models) |
| A nack can wait for news (`"news": true`): the first event about the item from outside its own runs makes it ready at once | a step that waits on someone outside | the review step taken again 7 to 17 ms after the news of the review (offline, the teammate records it as GitHub's webhook would), not up to `POLL_EVERY` later; the reviewer's own pace remains |
| ticket-factory: calls over the socket, adaptive re-checks (1 s doubling to `POLL_EVERY`), news on review, webhooks mapped | the example | see the factory tables |

## What remains

### 1. A process per item: a step that stays running (designed, not built)

Starting a process for each item is now the floor: about 7 ms to start even a shell one-liner, tens to hundreds of
milliseconds for a Python step that imports its libraries (ticket-factory's `step.py`: 40 ms before its own work),
seconds for an AI session, and about 3.5 ms of the engine's single interpreter for each run (the `fork`, a thread,
six events). At 500 items through 5 steps that is the 6 to 9 s above.

**The design.** A block that takes items may say its program stays running and asks for its items, over the engine's
socket, instead of being started for each one:

```yaml
blocks:
  triage:
    type: program
    run: python3 bin/triage.py
    takes: {kind: alert, at: new, to: [triaged]}
    pool: 20
    warm: 4                  # four processes kept running; each takes items one at a time (pool: the most at once)
```

- **The protocol** (the socket's, `calls/`): a warm process connects and asks `{"op": "next", "block": "triage"}`.
  The engine answers when there is an item for it: `{"item", "lease", "run", "env"}` (the same input and the same
  `ERGOSTAT_*` values a run is given today, `env` for the ones that differ per item). The process answers with the
  same lines a run prints (`{"op": "lines", "run": RUN, "lines": [...]}`, taken as they come, fenced the same way) and
  ends the item with `{"op": "done", "run": RUN, "exit": 0}` (or a nack line before it). Nothing else changes:
  every item is still a run in the record (`agent.started`, `agent.ran`, its lease, its attempts, its fencing); only
  the process is reused.
- **The change to how a step is written** is small: the loop around it. A Python step becomes

  ```python
  from ergostat.calls.serve import items        # or 20 lines of the standard library, as bin/tf.py speaks the socket
  for it in items():                            # one item at a time: its input, its environment set for it
      it.say({"event": "alert.triaged", "data": triage(it.item)})
  ```

  and must not keep state from one item to the next that it would not have kept across runs. A shell step stays a
  process per item. A step that does not declare `warm:` is run as today.
- **What the engine guarantees.** A warm process that crashes, or exits, ends the item it held as a run that exited
  non-zero (its attempt counted) and is started again; one silent past the lease's TTL is killed and replaced (its
  item expires, as today); each is replaced after `recycle:` items (default 1,000) or when the model changes, so a
  leak or a stale model cannot last. The owner sees warm processes on the block's page, like runs.
- **Why pull, over the socket**: no pipes per process, no thread per item in the engine (a process waiting for its
  next item is parked like an `act` waiting for its answer), and the same protocol serves warm processes ergostat did
  not start (another host's pool, later), held to the same leases.
- **What it should buy**: the spawn (7 ms to seconds) and the fork in the engine (about 2 of the 3.5 ms a hop) go;
  the six events of a hop can be written in two batches (taken with started; the step's lines with ran and ended).
  Estimate: 1,000+ hops a second on one engine, so 500 items through 5 steps in 2 to 3 s, and a Python step's hop
  in milliseconds instead of a tenth of a second.

### 2. The engine's own cost per hop

After the process: the events of a hop (six writes, each a lock, an append and a fold), the dispatcher taking one
item at a time and folding it again to check its lease, and one interpreter for all of it (the GIL). Batching a
look's takes into one write, and checking them against the fold once, is the next 2x; a second engine process for
the runs' own bookkeeping is a design change, and only needed past about a thousand hops a second.

### 3. AI latency: the outside time ergostat can still shape

An alert-triage bot that takes 2 to 3 minutes spends almost all of it in the model and in tools. What would cut it:

- **Parallel facets.** Split the triage into independent questions (what changed: deploys, config; what is failing:
  logs, metrics; who else sees it: other alerts, the status page), each a small fast session (haiku) or a plain
  query, run at once as separate blocks taking the same alert (each its own state or its own `where:`), and a short
  final step that reads their answers. The slowest facet, not their sum, is the time; ergostat's hops between them are
  now milliseconds.
- **Short, cached prompts.** Keep what every run shares (the instructions, the tools, the team's runbook) first and
  unchanging, so the provider's prompt cache serves it, and render the item's own context (a recipe, SPEC 12j) last
  and short. A session that starts by reading 50 files to orient itself pays that every time; a recipe that hands it
  the 5 that matter does not.
- **Streaming and early answers.** ergostat takes a run's lines as it prints them (SPEC 9.1): a step that prints its
  verdict as soon as the model gives it (`{"event": "alert.triaged", ...}` first, the explanation after) moves the
  item on while the session is still writing. The next step can start on the verdict.
- **Warm sessions.** Starting `claude -p` costs seconds before the first token; a warm process (above) holding a
  session open per step, fed one item at a time, does not pay it per item.
- **Fetch before it is its turn.** When an alert is pushed, a cheap step can gather its context (the dashboards, the
  recent deploys) at once, in parallel with whatever is ahead of it, so the AI step starts with it in hand.
- **Fewer, smaller models.** A narrow decision (is this a known flake?) is a rule or a narrow AI agent, in
  milliseconds; the ladder in `docs/AGENT-GUIDE.md` is also the latency ladder.

### 4. The factory's own waits

Approvals (promote the classes that have proved themselves: `ergostat actions` says which), the reviewer (people),
the pools (`size: 3` workspaces held through review and CI; `at-once: 1` for the AI), and the collectors that remain
(the watcher every 10 s: a Jira webhook makes it the fallback).

## A plan to reach 1 to 10 s at 100 to 500 items

| step | what | expected, 5 steps of no work | status |
|---|---|---|---|
| 1 | woken by the write; counts read on write; a thread a run; push intake; the socket; waiting for news | 1 item 0.07 s; 100 items 1.4 s; 500 items 6 to 9 s | **done** (measured above) |
| 2 | warm step processes over the socket (`warm:`), Python helper | 500 items 2 to 3 s; a Python step's hop ~5 ms | designed (above) |
| 3 | a look's takes in one write; a hop's events in two | 500 items ~1.5 s | next, small |
| 4 | ticket-factory and the work bots: webhooks configured at work (Jira, GitHub, the alert source), gates promoted as they prove themselves, AI steps split into parallel facets with short cached prompts and early answers | a triage of 2 to 3 min → the slowest facet's model time plus seconds | the example shows the way; the work setup is the Supervisor's |
| 5 | past ~1,000 hops a second: the runs' bookkeeping in a second process | | only if measured to be needed |

The target, 1 to 10 s at 100 to 500 items apart from outside time, is met now for steps that are processes doing
little work (6 to 9 s at 500, 1.4 s at 100), and step 2 gives it a wide margin. For the triage bots the time is the
model's: steps 2 and 4 are what move it.
