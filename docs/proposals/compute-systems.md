# Compute systems: machines that run what this engine decides

Status: proposed 2026-11-22, for the owner's review; nothing of it is built. The owner's framing: remote systems
(`docs/proposals/remote-systems.md`, SPEC §4c) scale ergostat **upward**: another ergostat's model, read here.
Nothing scales it **downward**: machines that run this model's work. Today every machine block runs on the
engine's own machine, and the one place ergostat's work is run elsewhere (the factory's Docker sessions,
`dev/bin/agents.py`) is outside the core.

A **compute system** is a pool of **nodes** that run what this engine decided. It holds no model, no goals, no
record: the engine leases the item, starts the run, reads its lines and records what happened, exactly as it does
for a local run; the node only executes, keeps the run's output until the engine has read it, and stops the run
when told to or when it can no longer hear the engine. On each node a **worker** (`ergostat worker --stdio`) does
this, reached over an SSH session, with no port of its own.

Words. "Agent" means whatever fills a role (NOTES.md, *Agents*), so a node and its worker are never called agents:
a worker fills no role, shows no rung and decides nothing. The block's agent is still the block's agent, wherever
its run executes. "Worker" here names one program (the node's process), never a role or a run.

## The mirror of a remote system

| | Remote system (SPEC §4c) | Compute system (this proposal) |
|---|---|---|
| Who holds the model | the remote ergostat | this engine; the node holds none |
| Who decides | the remote | this engine (its dispatcher, its controllers) |
| Who executes | the remote's machines | the node, for this engine |
| Where the record is | the remote's record, read here | this engine's record only; the node keeps run files until read |
| What crosses | readings and events, read-only | runs in; lines, exits, readings and results out |
| Direction | we read it; we never act through it (remote-systems.md:22-26) | we act through it; it never reads or changes our model |
| Transport | HTTP behind a token, over an SSH tunnel or https (remote-systems.md:61-76) | JSON lines over an SSH session (section 3) |

In the disciplines' terms:

- **Queueing**: a compute pool is a multi-server station. Its servers are the node slots (`c`, the sum over the
  nodes in service); the block's items are the customers; the dispatcher is the admission rule. Utilisation is
  `ρ = λ / (c·μ)`, and a pool whose `c` drops (a node lost) shows as a queue growing at a fixed arrival rate, which
  the model can already see as a stock of items in a state.
- **System dynamics**: capacity is a **stock** (slots in service), with an inflow (nodes joining, slots freed) and
  an outflow (nodes lost, slots taken). It is read like any stock (section 4), so a controller can hold a queue
  against it, and a valve can add nodes when the owner grants one that does.
- **Control**: the pool is an **actuator** with limited authority: it saturates at `c`. The engine is still the one
  controller of its runs; the node has a local safety interlock only (a run stops when its lease cannot be renewed,
  section 2.7), never a decision of its own about what to run.

## 1. Where runs execute today

- **Machine blocks** run as a child process of the engine, in `Engine._ran` (`ergostat/spec/engine.py:975-1184`): the
  run's input is written to a file (`engine.py:1064`), the process is started in a session of its own through
  `Measured` (`engine.py:1066-1067`), its record written (`engine.py:1068`), its output file followed by
  `stream.follow` with the block's timeout (`engine.py:1085-1086`), and its CPU and memory sampled
  (`engine.py:1082`, `engine.py:1089`). The working directory is the block's workdir or the model's root
  (`engine.py:1029`).
- **The environment is the engine's whole environment** plus the run's variables (`engine.py:995-997`), so whatever
  secret the engine was started with is in every run's environment. `ERGOSTAT_CMD` names this machine's Python and
  model root (`engine.py:997`), and `ERGOSTAT_SOCKET` the engine's local call socket (`engine.py:998-1001`,
  `engine.py:1791-1800`).
- **A run outlives its engine, but nothing takes it up again.** Its four files (`runs/RUN.json|in|out|exit`), its
  wrapper that writes the exit code, and its record of pid and start time are in `ergostat/spec/runrecord.py:1-8`,
  `runrecord.py:41-47`, `runrecord.py:70-83`. SPEC says plainly that taking up a run left behind by a stopped engine
  is not built (`docs/SPEC.md:2201`).
- **Leased runs.** The dispatcher leases each item to a run (`ergostat/leases/dispatch.py:253-315`), the fencing
  number one more than the last (`dispatch.py:257`), and starts one thread per run (`dispatch.py:314`) that calls
  `run_block` (`dispatch.py:331`). A block's room is its pool less its runs in flight (`dispatch.py:193-203`); a
  pool may be read from a stock (`dispatch.py:205-218`, `ergostat/spec/ir.py:711-712`); a daemon's free room caps it
  too (`dispatch.py:197-198`).
- **Lost runs.** A lease past its expiry, with no activity from its holder, expires on a second look
  (`dispatch.py:468-480`, `dispatch.py:482-504`); its run is killed only when this engine started it
  (`ergostat/leases/kill.py:30-46`: it looks the run up in `eng.live`); and whatever a run says about its item after
  its lease ended is refused by the fence (`engine.py:2061-2085`). A program's TTL is at least its timeout
  (`ergostat/leases/terms.py:33-34`).
- **Kills and timeouts.** A timeout kills the run's process group (`ergostat/spec/stream.py:36-38`,
  `ergostat/runner.py:44-53`); a lease kill sends SIGTERM to the group and every descendant, then SIGKILL after the
  grace (`kill.py:1-6`, `kill.py:49-63`).
- **The older runner.** `ergostat/runner.py:280-357` runs an agent's command with `shell=True` in the repository
  (`runner.py:302-303`), still used by `ergostat agent NAME --now` (`ergostat/cli/agents.py:122-139`).
- **The factory's containers** (`dev/bin/agents.py:1-17`) already do much of what a node must: hard limits with
  `--init` (`agents.py:53-54`), one secret given by name at `docker run` and never on a command line
  (`agents.py:12-14`, `agents.py:145-155`), containers named by a prefix and a random id (`agents.py:172-175`),
  killed and removed by name (`agents.py:161-164`), a sweep of those past their time (`agents.py:178-192`), and the
  work coming out as a git bundle made in a container with no network (`agents.py:309-335`). None of it is reachable
  from a model.

## 2. The worker

One program, `ergostat worker --stdio`, standard library only (as all of ergostat at runtime, CLAUDE.md:63), in one
module that also runs on its own (`python3 -I worker.py --stdio`), so a node needs Python 3.12 and git, not an
install of ergostat. It reads requests on standard input and answers on standard output, one JSON object a line;
its own diagnostics go to standard error, which the engine keeps in the pool's log. It has a folder of its own
(`~/.local/state/ergostat-worker/` by default, `--root` to change it) and writes nowhere else but the run folders
it makes there and the containers it names.

### 2.1 Registration and heartbeat

The first line the worker says is `hello`:

```json
{"v": 1, "seq": 1, "type": "hello", "worker": "1.0", "node": "3f9c...", "cpus": 16, "memory": 68719476736,
 "disk": {"root": 412316860416}, "arch": "x86_64", "os": "linux", "backends": ["process", "docker"],
 "images": ["ergostat-run:1@sha256:..."], "labels": {"gpu": "none"}, "slots": 4, "runs": ["9b1e..."]}
```

- `node` is a random id the worker makes once and keeps in its root (never a host name, an address or a user
  name: the engine names a node by its pool and its place in the list, section 4);
- `cpus`, `memory`, `disk` and `arch` are read from the system (`os.cpu_count`, `/proc/meminfo` or `sysctl`,
  `shutil.disk_usage` of the root, `platform.machine`); `images` from `docker image ls` when the Docker backend is
  there; `labels` from the worker's own `labels.json` (what the owner says the node has);
- `slots` is the most runs it takes at once (its config, at most its CPUs, at most 64); the worker, not the engine,
  is the authority on it, so two engines connected to one node can never both fill it (a `start` beyond it is
  refused, `full`);
- `runs` lists the runs it still holds (section 2.4).

Every 10 seconds, and at once after a run starts or ends, it says `beat`: the slots free, the disk free, and per run
its state (`running`, `ended`, `unknown`: section 2.4), its byte offsets so far and its latest CPU and memory reading. The engine counts a
node **lost** after three beats missed (30 s) or the session's end, whichever comes first.

### 2.2 A run, with limits, through a backend

The engine sends `start`:

```json
{"type": "start", "run": "9b1e...", "block": "build", "backend": "docker", "image": "ergostat-run:1",
 "command": "make test", "input": "<the run's stdin, as today's runs/RUN.in>",
 "env": {"ERGOSTAT_RUN": "9b1e...", "ERGOSTAT_ITEM": "change/42", "ERGOSTAT_LEASE": "7"},
 "secrets": {"API_TOKEN": "..."}, "limits": {"cpus": 2, "memory": 4294967296, "pids": 512, "disk": 10737418240,
 "wall": 1800, "network": "none"}, "work": {"repo": "main-repo", "commit": "1a2b3c..."},
 "out": {"bundle": true, "artifacts": ["dist/*.tar.gz"], "transcripts": [".claude/projects/*.jsonl"]},
 "lease": {"fence": 7, "ttl": 60, "left": 60.0, "sent": 81234.5}}
```

The lease carries no time of day: `left` is the seconds until the engine's expiry and `sent` the engine's
monotonic clock when it said so, both read by the engine at one moment; section 2.7 says how the worker times them.

and the worker answers `started` (with the backend's own handle: a pid and its start time, or a container name) or
`refused` with why (`full`, `no such image`, `limits over the node`, `bad name`). A `start` refused after its
item was leased is not the run's fault: the engine gives the item back uncounted and puts it off, as it does today
for a run that found its workspace pool full (`engine.py:1149-1150`, `POOL_FULL_AFTER`, `engine.py:59`), and a
refusal for any other reason (`no such image`, `limits over the node`) is said in the pool's status and gives the
item back the same way, so a misconfigured node costs no item an attempt. A **backend** is how a run is made
to execute under its limits; each says the same four things: start, is it still going, stop, and what it used.

- **process**: a session of its own and the same `sh` wrapper that writes the exit code (`runrecord.py:21-29`), so
  the run never depends on the worker; memory and processes by `setrlimit` (`RLIMIT_AS`, `RLIMIT_NPROC`) before
  `exec`; CPU, where the node lets a user write a cgroup v2 (`systemd-run --user --scope -p CPUQuota=`), as a share,
  else only as a ceiling on CPU **time** (`RLIMIT_CPU` at `cpus × wall`), and `hello` says which. No network limit:
  `network: none` is refused on this backend rather than pretended.
- **docker**: `docker run -d --init --name ergostat-run-RUN --cpus --memory --memory-swap --pids-limit
  --network none --cap-drop ALL --security-opt no-new-privileges`, the same limits the factory's containers carry
  (`agents.py:53-54`); the work folder mounted at `/work`, the run's output to files in the run folder, never to
  `docker logs` alone. Docker is a resource limit, not a security boundary (CLAUDE.md:98): the proposal claims no
  more.
- **kubernetes** (a later gap): a Job per run named `ergostat-run-RUN`, the limits as its requests and limits,
  the worker running wherever `kubectl` reaches the cluster. The protocol does not change.

### 2.3 The log a reconnect resumes from

The run's standard output and standard error go to two files in its folder (`runs/RUN/out`, `runs/RUN/err`), as a
local run's output does today (`runrecord.py:1-8`). The worker follows them and sends what is new as `out` lines,
each with the stream, the byte **offset** of its first byte and its text (at most 64 KiB a line; longer output is
split at line ends where it can be, else at the limit). The engine records the lines exactly as it records a local
run's: the worker never reads or interprets them, so the refusals, the fence and the bare number all stay in the
engine (`engine.py:1042-1048`, `engine.py:2061-2085`).

The engine keeps, per run, the offset it has taken up to (in the run's record, written after the lines are
recorded). On a reconnect it sends `attach {"run", "out": OFFSET, "err": OFFSET}` and the worker sends from there.
Ordering is by offset, never by time (the review lessons' lesson-2): a line whose offset is below what was taken is
dropped, so a line is recorded once even when the worker resends it. Each file is capped (`limits.log`, 64 MiB by
default, at most 1 GiB); past the cap the run is stopped, `log over its cap`, rather than its output silently
dropped.

### 2.4 Runs that outlive the connection

The worker that SSH started dies with its session; the runs do not. Each run is its own session under the wrapper,
or a detached container, and its folder holds its record (`run.json`: run id, block, lease, backend handle, the
pid's start time or the container's id, its offsets, its limits, its deadline). A new `ergostat worker --stdio`
reads the run folders at start and lists their runs in `hello`. The engine, on reconnecting, attaches every run it
still holds a lease for, and sends `kill` for every one it does not (a run the engine no longer knows is never left
running on a node). Each run the worker lists is in one of three states, and **gone** needs evidence read:

- **running**: its pid alive with the start time recorded (as `runrecord.py:79-83`), or its container running with
  the id recorded;
- **gone**: only on one of an allowlist of readings: the wrapper's exit file written; the container read as exited
  with the id recorded; or the pid absent (or now another process, by its start time) *and* the run's process group
  read as empty. Then the run ended, and its exit (or its want of one) is reported as `ended`;
- **unknown**: anything else: the record unreadable, the start time not read (a failed or timed-out `ps`, the
  case lesson-3 records), `docker inspect` failing, the group not read. Unknown is never gone and never fine. The
  worker tries a stop by name at once (SIGTERM then SIGKILL to the group in `runs/RUN/pgid`, a file of its own
  written before the run starts; `docker rm -f ergostat-run-RUN`), and keeps listing the run as unknown until a
  reading puts it in one of the other two states. The engine keeps the lease, records no end, and sends no
  renewal: the lease expires at its TTL through the watchdog as a silent run's does (`dispatch.py:468-504`), the
  run ends `agent.failed` with the note `unknown on its node`, and whatever the run still says is refused by the
  fence (`engine.py:2061-2085`). The lease is never released early on a reading that was not made (lesson-6).

The engine's own side is the half SPEC says is not built for local runs (`docs/SPEC.md:2201`): an engine that
restarts must take up the runs its record says it started. That is one mechanism for both (milestone gap 6).

### 2.5 The work in and out

- **In: an exact commit.** A run names a repository (a name in the pool's config) and a commit id, never a branch.
  The worker keeps one bare repository per name in its root and answers `need {"repo", "commit"}` when it lacks the
  commit; the engine sends a git bundle of what is missing (`have` lists the worker's newest commits), in chunks of
  at most 1 MiB, at most 2 GiB in all. The run's folder is a detached worktree at that commit (as the workspace
  pools make worktrees, `ergostat/workspaces/git.py:50-58`), or for a run with no repository an empty folder.
- **Out: a bundle, artifacts, transcripts.** When the run ends the worker makes, in the run's backend (a container
  with no network for docker, as `agents.py:309-335` does), a git bundle of the commits on top of the given commit,
  the files matching the run's `artifacts` globs (inside the run folder only; symlinks out of it refused), and the
  transcripts named. Each goes back as chunks with its size and SHA-256, each capped (bundle 256 MiB, artifacts
  1 GiB, transcripts 64 MiB by default). The engine fetches the bundle into a side ref named for the run and the
  fence, never into a branch, and keeps the rest under `runs/RUN/` in the state folder; what a later block does
  with them is the model's business. A result whose lease has ended is refused like a line (the fence), and said.

### 2.6 Secrets given at start, never written

The pool's config names each secret and the file it is read from (section 4), as a remote's `token-file:`
(remote-systems.md:66-67); the model never holds one. The engine reads them at each start and sends them in
`start.secrets`. The worker keeps them in memory only: the process backend puts them in the run's environment, the
docker backend passes `-e NAME` with the value in the `docker` client's own environment, never on its command line
(as `agents.py:12-14`). They are never written by the worker or the engine: not to the run's record, its folder, its
log, a `beat`, the event record or an error; the record and the events carry their **names** only. The run's
environment is an allowlist (the run's `ERGOSTAT_*` variables, `PATH`, `HOME`, `LANG`, the secrets named), not
the engine's whole environment as a local run's is today (`engine.py:995`). What the run itself does with a secret
it was given is outside this guarantee: a run can print it, and a process can read its own environment. The worker
also replaces a secret's exact value in forwarded lines with `[secret NAME]`, as a second layer only (a denylist,
it misses an encoded copy); the claim is "never written by ergostat", not "never seen".

### 2.7 Kill, timeouts and a lost lease

- **Kill.** `kill {"run", "why", "grace"}`: SIGTERM to the run's group and its descendants, SIGKILL after the grace
  (as `kill.py:1-6`); for docker, `docker stop -t GRACE` then `docker rm -f`. The worker answers `ended` with how
  (`TERM`, `KILL`) as `ergostat.run.killed` records it today (`kill.py:56-63`).
- **The wall timeout is the worker's.** The worker holds the run's deadline (`limits.wall`, the block's `timeout:`,
  `ir.py:703`) and kills it there whether or not the engine is connected.
- **A lost lease stops its run.** The engine gives a silent run's item to another no earlier than its expiry plus
  `grace(ttl) = max(1, min(0.1 × ttl, 30))` seconds (`terms.py:38-41`): the watchdog expires a lease only on a
  second look, `grace(ttl)` after the pass that first found it overdue (`dispatch.py:468-480`), and no pass finds it
  overdue before its expiry (`dispatch.py:458`). The node's interlock is built to have **finished** its kill inside
  that window, and never compares a time of the engine's with a time of its own (lesson-2):
  - *What the engine says.* With `start`, and with `renew {"run", "fence", "left", "sent"}` at once after each
    renewal it records and every 2 seconds besides, the engine says how many seconds its lease has `left`
    (its expiry less its own clock, read together) and `sent`, its monotonic clock at that moment.
  - *How the worker times it.* Only on its own clock, one that counts a suspend (`CLOCK_BOOTTIME` on Linux). It
    keeps `base`, the least `heard − sent` of the session's messages over the last ten minutes (heard on its clock,
    sent on the engine's: the difference is never read as a time, only compared with other such differences; the
    window keeps two clocks' drift, tens of parts per million, to a few milliseconds). A run's deadline is
    `sent + base + left` from the latest renewal heard: the engine's expiry on the worker's clock, late by at most
    the fastest one-way transit of the window (`d_min`), however late *this* renewal came. A renewal that arrives
    slow therefore cannot move the deadline later than a fast one would.
  - *The kill.* At its deadline the worker sends SIGTERM to the run's group (or `docker stop -t K`), and SIGKILL (or
    `docker rm -f`) `K = grace(ttl) / 4` seconds later: SIGTERM by `expiry + d_min`, SIGKILL by
    `expiry + d_min + grace(ttl) / 4`.
  - *What the engine checks.* It sends `ping` every 2 seconds and times each `pong` on its own monotonic clock;
    `d_min` is below every round trip (a round trip contains a one-way transit). The engine starts a run on a node only while the least round trip of the last minute is at
    most `grace(ttl) / 4` for the block's TTL (else `start` is not sent and the item goes back uncounted, as a
    `full`; with a 60 s TTL that is 1.5 s), and kills a running one by `kill` if its node's round trips grow past it.
    The SIGKILL is then sent by `expiry + grace(ttl) / 2`, leaving half the grace for the kernel or Docker to end
    the processes and for the worker's own timer (a quarter second), before the watchdog's second look can give the
    item away. With a 60 s TTL: grace 6 s, the kill asked by expiry + 3 s.
  - *What is not claimed.* A node that is suspended stops its runs with it; on waking, a run may go on for one tick
    of the worker's timer before the kill, and what it says then is refused by the fence. A run's descendants that
    left its group are reached by `reap` only as the local kill reaches them (`kill.py:53-57`). Docker's own stop
    time past `rm -f` is Docker's.

  On the engine's side,
  `kill()` reaches a node's run through its handle as it reaches a local one through `eng.live` today
  (`kill.py:39-46`). The fence still refuses whatever a run says after its lease ended (`engine.py:2061-2085`), so
  the interlock on the node is a second stop, not the only one.
- **Every number has a ceiling**: slots at most 64 a node, nodes at most 64 and runs on nodes at most
  256 over all pools (section 3), `wall` at most a day, a `kill`'s `grace` at most 10 minutes, retries of a lost session backed off up to ten minutes; each refused at `check` above its
  ceiling and again by the worker at `start` (the review lessons' lesson-4).

### 2.8 Per-run CPU and memory, as readings

The worker samples each run once a second for the first ten, then every ten seconds: for the process backend its
tree from `/proc` (or `ps`), as the local sampler does (`ergostat/costs/sampler.py:1-24`); for docker the
container's cgroup (`cpu.stat`, `memory.current`, `memory.peak`). The latest is in each `beat`; the whole is in
`ended` as `resources`, which the engine writes on `agent.ran` or `agent.failed` as it does for a local run
(`engine.py:1089`, `engine.py:1136`). They are **measurements**, not events (invariant 10): the engine records each
pool's `ergostat.compute.*` series (section 4) and each run's totals; no `beat` becomes an event.

### 2.9 Cleanup by name

Every name the worker makes is made from the run id, which must match `^[0-9a-f]{32}$` (refused otherwise): the
folder `runs/RUN/`, the worktree under it, the container `ergostat-run-RUN`. It removes a run's folder and container
only after the engine has said `done {"run"}` (it has recorded the end and fetched what it wanted), or past the
run's deadline plus a day with no engine to say so. A sweep at start and every hour removes only names of that form
under its own root and its own container prefix, resolved and checked to be under the root before anything is
deleted; it never deletes all-but-a-list (lesson-11). The bare repositories are pruned by age and size (`--keep`,
a disk cap).

## 3. The transport: JSON lines over an SSH session

The engine starts `ssh -T -o BatchMode=yes HOST ergostat worker --stdio` (`HOST` is a name in the owner's
`~/.ssh/config`, so no address or user name is in the model) and speaks to the worker on that process's standard
input and output. There is **no open port**: no listener on the node, none on the engine; who may connect, the
keys and the encryption are SSH's, which the owner already runs (the same choice as a remote's tunnel,
remote-systems.md:70-74). A pool may name another command in place of `ssh` (`connect:`), which is how the tests and
the demo run a worker on the same machine (`connect: [ergostat, worker, --stdio]`), and how a later backend reaches
a node through something else.

Every line is one JSON object with `v` (the protocol, 1), `seq` (per direction, from 1, so either side sees a gap)
and `type`, at most 1 MiB. Requests carry an `id` that their answer repeats.

| From the engine | From the worker |
|---|---|
| `start`, `renew`, `kill`, `attach`, `done` | `hello`, `beat`, `started`, `refused` |
| `bundle` (chunks in), `ping` | `need`, `out` (lines, by offset), `ended` (exit, how, resources) |
| | `result` (chunks of the bundle, artifacts, transcripts), `pong`, `error` |

The worker sends at most 4 MiB ahead of the engine's acknowledgement (`attach` and `beat` carry the offsets
taken), so a slow engine slows the node's output, never fills its memory. One connection per node per engine
process, one reader thread per connection, and the lines of every run on that node come through it. Each run on a
node still costs the engine its dispatch thread (`dispatch.py:314`), as a local run does, but no follower thread of
its own. Both are bounded **engine-wide**, not only per pool: at most 64 nodes over all pools (64 reader threads),
and at most 256 runs on nodes at once over all pools. `check` refuses a model whose pools' `nodes × slots` sum past
256; at run time the dispatcher counts every node run still held or draining (killed, not yet `ended`) against
that 256 before it sends a `start`, whatever the pools and nodes say. A
worker that meets a version it does not know answers `error` and ends; the engine says so in the pool's status and
starts nothing there.

## 4. The model

```yaml
compute:
  farm:                               # the pool's local name
    nodes: [{ssh: node-1}, {ssh: node-2}]   # Host names in the owner's ~/.ssh/config
    backend: docker                   # process (default) or docker
    image: ergostat-run:1
    slots: 4                          # runs at once per node (at most its CPUs, at most 64)
    limits: {cpus: 2, memory: 4g, wall: 30m}
    repos: {main-repo: .}             # the repositories a run may name, and where they are here
    secrets: {API_TOKEN: ~/.config/ergostat/api.token}
    labels: {arch: x86_64}            # a node is used only when its hello says these

blocks:
  build:
    type: program
    run: make test
    takes: {kind: change, at: [ready], to: [built]}
    pool: 8
    runs-on: farm                     # default: local, today's behaviour
```

- **`runs-on: <pool>`**, on a machine block (`ir.py:723-725`). Unset, or `local`, the block runs as it does today:
  nothing in a model that does not say `runs-on` changes. `check` refuses an unknown pool, a pool whose limits are
  over its ceilings, `network: none` on the process backend, and a block whose command needs this machine
  (`ERGOSTAT_CMD`, the call socket) until those reach nodes (milestone gap 10).
- **Compute capacity as a stock.** Each pool has built-in measures, as the workspace pools do (`ir.py:206-212`):
  `ergostat.compute.slots@POOL` (slots of nodes in service), `.free@POOL`, `.busy@POOL`, `.nodes@POOL`,
  `.lost@POOL`. A block's room is its own pool less its runs (`dispatch.py:193-203`), and also at most the pool's
  free slots, as a daemon's room is capped (`dispatch.py:197-198`); `pool: {now: stock.S}` (`ir.py:712`) may read
  any of them. A model may draw the pool as a stock with its flows (nodes joining, nodes lost) and a goal on it, and
  the diagrams show it as any stock; nothing is drawn that the model does not declare (invariant 12).
- **Lost nodes need no new mechanism.** A lost node's runs keep their leases until those expire as any silent run's
  do (`dispatch.py:468-504`): the item goes back to its queue, its attempt counted as today (`dispatch.py:492`), and
  anything the node later says about it is refused by the fence. The node's slots leave the capacity stock at once,
  so the dispatcher stops sending there before the leases expire. If the node comes back, its worker's `hello`
  lists those runs, the engine holds no lease for them, and it kills them (section 2.4). Whether a lost node's runs
  should count against the item's attempts is the owner's choice (section 6); this proposal keeps today's counting.
- **Shards.** A pool belongs to the shard of the blocks that use it, as a kind does (SPEC §9.8, `dispatch.py:96-100`); `check` refuses a
  pool used by blocks of two shards. The worker's own slot count still stops two engines from overfilling a node.

## 5. What it is not, and the invariants it keeps

**It is not:**

- **a scheduler.** The node never chooses what to run; the engine's dispatcher does, with its leases, pools and
  budget, as today (`dispatch.py:170-203`). The worker answers `start` or `refused`, nothing more.
- **an agent.** A node fills no role and shows no rung. A block keeps its agent and its rung wherever it runs.
- **a remote system.** It holds no model, no goals and no record, serves no API and is never drawn as a subsystem.
- **a record.** The node keeps a run's files until the engine has read them, then deletes them. There is one
  record, the engine's; a node's beats are measurements.
- **a security boundary** beyond its backend: a process run is the node's user; a Docker run is Docker's limits.
  Secrets are kept from ergostat's files and logs, not from the run.
- **for sensors and daemons, yet.** Sensors' readings and daemons (SPEC §9.7) stay on the engine's machine in this
  milestone. AI blocks come after program blocks (they need the transcripts and the session token as a secret).
- **a cluster manager.** It does not provision or scale nodes. A valve that does is the owner's to grant, like any.

**It keeps:**

- **Three roles (invariant 2).** A run on a node acts on the world only as the block's valve, through lines the
  engine reads and records. The worker itself changes nothing but its own folder and containers.
- **Every agent held to the same discipline (invariant 6).** Each run has its limits, its timeout, its lease and its
  readings, and a node cannot run a block the engine did not lease.
- **Events and metrics apart (invariant 10).** Every event is written by the engine to its own record; beats and
  resources are measurements.
- **Nothing of its own accord (invariant 12).** No pool, node or worker exists until the owner declares one; an
  empty `compute:` runs nothing.
- **Leases and fences.** A run's lease, fence, attempts and dead letters are today's (SPEC §9.5); a node adds a
  second stop (its interlock), never a second judgement of whether a lease is held.
- **Fail closed.** A missing beat counts as a lost node, a hello of an unknown version as refused, a node too slow
  for a block's grace as refused for it. A run counts as gone only on a reading from an allowlist (section 2.4);
  an unreadable record, a start time not read or a container not inspected is **unknown**: its lease kept, a stop
  by name tried, the lease left to expire, never gone and never fine.

## 6. Decisions for the owner

These are open; each is the most reversible choice, and each can change without changing the protocol.

| Question | Proposed |
|---|---|
| How a node is reached | SSH to a Host name in the owner's SSH config; `connect:` for anything else |
| Who counts a node's slots | the worker (refuses `full`); the engine's capacity stock follows its beats |
| What a lost node's runs cost the item | an attempt, as any expired lease today; `count: false` is a one-line change later |
| Secrets | named files, read at each start, sent in `start`, never written by ergostat |
| The run's environment on a node | an allowlist, not the engine's environment |
| When a node's interlock kills | at the engine's expiry, timed on the node's own clock from the renewals heard; SIGKILL `grace(ttl) / 4` later |
| What a node keeps | run folders until `done`, bare repositories by age and size |
| Sensors, daemons, AI blocks | engine-local in this milestone; AI blocks in a later gap |
| Kubernetes | a later backend, the same protocol |

## 7. The milestone: gaps, in order

1. **`compute-runner-interface`**: a runner interface in the core (`ergostat/compute/runner.py`): `start(spec) →
   handle`, `lines(handle, offset)`, `alive(handle)`, `kill(handle, why, grace)`, `resources(handle)`,
   `cleanup(handle)`. Its first backend, `local`, is today's code moved behind it unchanged: the run files and
   wrapper (`runrecord.py`), `Measured`, `stream.follow` and the sampler, as `engine.py:1060-1105` uses them, and the
   lease kill (`kill.py:30-63`) through the handle in place of `eng.live`. No behaviour changes: the unit suite and
   the four browser files pass unchanged, and a new test shows `_ran` reaches processes only through the interface
   (a monkeypatched backend sees every start, kill and cleanup). Net code near zero.
2. **`compute-run-spec`**: the run as data: one JSON-able run spec built by `_ran` (command, input, cwd, the
   `ERGOSTAT_*` environment, secrets by name, limits, the work's repository and commit, the outputs wanted), passed
   to the backend. The local backend still gives the engine's environment (today's behaviour); the spec's allowlist
   is what other backends use. Tests: the spec of each block type, round-tripped through JSON.
3. **`compute-worker-stdio`**: `ergostat worker --stdio`, standard library only, protocol v1 (section 3), with the
   process backend: hello and beats, start with `setrlimit` limits, output by offset, the wall timeout, kill with a
   grace, the run folders and cleanup by name. Tested over a pipe to a worker on the same machine (no SSH): a run's
   lines, its exit, a kill, a timeout, a line resent below the taken offset dropped, a bad run id refused, a sweep
   that deletes only its own names.
4. **`compute-pools`**: `compute:` and `runs-on:` in the YAML, their `check` findings and ceilings; the engine's
   connection per node (`ssh`, or `connect:`), a `remote` backend of the runner interface over it; the
   `ergostat.compute.*` measures and the dispatcher's room capped by a pool's free slots; a pool's status in the
   engine's heartbeat and `/api/status`. Acceptance: a block with `runs-on` over a same-machine worker runs and
   records as a local block does; a block without it is unchanged.
5. **`compute-lease-on-node`**: the lease's expiry in `start`, `renew` on each renewal, the worker's interlock
   killing a run whose lease it has not heard renewed, the engine's lease kill reaching node runs, a node lost after
   three beats missed, its slots out of the stock at once, `ping` round trips and the `grace(ttl) / 4` bound, the
   engine-wide ceilings of section 3. Tests: a worker whose session is cut has SIGKILLed its run by the expiry plus
   `grace(ttl) / 2`, before the watchdog expires the lease; a worker whose clock of day is set an hour off kills at
   the same moment; a renewal delayed in the pipe does not move the deadline later; a node whose round trip is past
   the bound is sent no `start`; the item goes back once; a line the cut-off run sends after reconnecting is refused
   by the fence.
6. **`compute-reattach`**: runs that outlive the connection, and the engine's taking up of the runs it started
   (local and remote alike, the half `docs/SPEC.md:2201` says is not built; it takes up what the parked
   `rs-adopt` review found, such as recording the end before releasing the record). A reconnect attaches every run
   it holds a lease for, from its offsets, and kills every one it does not; a run is gone only on a reading of section 2.4's allowlist (a reused
   pid with its group empty), and a failed `ps` or an unreadable record gives `unknown`: the lease kept until it
   expires, never released early.
7. **`compute-work-in-out`**: the exact commit in (bare repositories, `need`, bundles in chunks) and the bundle,
   artifacts and transcripts out (sizes and hashes, caps, a side ref per run and fence, a result after the lease
   ended refused).
8. **`compute-secrets`**: `secrets:` from files, sent at start, held in memory; the allowlisted environment.
   Acceptance: after a run, the secret's value is in no file of the worker's root, the engine's state folder, the
   record or any log (a test that searches them all), and its name is on the run.
9. **`compute-docker-backend`**: the Docker backend on the worker: the limits and `--init`, the container named
   for the run, the images in `hello`, per-run readings from the container's cgroup, `docker stop` then `rm -f`,
   `network: none` by default.
10. **`compute-calls-from-node`**: a run on a node may call `ergostat act`, `event --add`, `lease` and `item` as a
    local run does: the worker serves a socket in the run's folder and forwards each call to the engine, which
    answers it as its own socket does (`engine.py:1791-1800`), at most 20 calls a second a run. Until then `check`
    refuses a `runs-on` block that uses them.
11. **`compute-demo`**: `examples/compute-pair/`: a model whose items are worked by a pool of two same-machine
    workers; one worker is killed mid-run, its node is lost, its item's lease expires and the item is worked again on
    the other; `demo_check` covers it.

**Left for later**: the Kubernetes backend; sensors and daemons on nodes; AI blocks on nodes (the session token as
a secret, their transcripts); a valve that adds or removes nodes; moving the factory's own sessions
(`dev/bin/agents.py`) onto a compute pool, so that the factory runs its gaps the way any model would.
