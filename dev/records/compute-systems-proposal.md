# compute-systems-proposal: a reviewed proposal for compute systems, machines ergostat delegates runs to

depends-on: []

The owner, 2026-11-22: remote systems scale ergostat upward (another ergostat's model, read here). Nothing scales it downward: machines that run this model's work. Today every block runs on the engine's machine (`ergostat/runner.py`, `ergostat/spec/engine.py` `run_block`, `ergostat/leases/dispatch.py`); the factory's own Docker sessions are in `dev/bin/agents.py`, outside the core.

## Definition of done
1. `docs/proposals/compute-systems.md`, written for the owner, in the style of `docs/proposals/remote-systems.md`. It covers:
   - what a compute system is: it runs what the engine decided and holds no model, goals or record (the mirror of a remote system);
   - the worker: registration and heartbeat (CPUs, memory, disk, architecture, images, labels), run with limits through a backend (process, Docker; Kubernetes as a later backend), stdin/stdout/stderr kept as a log a reconnect resumes from, runs that outlive the connection and are reattached, the work in (an exact commit) and out (a bundle, artifacts, transcripts), secrets given at start and never written, kill and timeouts, a lost lease stopping its run, per-run CPU and memory as readings, cleanup by name;
   - the transport: one standard-library Python worker speaking JSON lines over an SSH session (`ergostat worker --stdio`), no open port;
   - the model: a block's `runs-on: <pool>` (default local), compute capacity as a stock, lost nodes handled by the existing lease expiry and fences;
   - what it is not, and the invariants it keeps;
   - a milestone: an ordered list of gaps, each with a one-paragraph definition, starting with a runner interface in the core whose first backend is today's local behaviour.
2. Every claim about today's code cites file:line on main.
3. No code changes.

## Files to touch
`docs/proposals/compute-systems.md` only.

## Risks
- The word "agent" already means an AI agent in ergostat: call these workers or nodes.
- Nothing work-specific and no machine names, addresses or user names.

## Size budget
0 lines of code; the proposal under 600 lines.

## Where it stopped

Written in full: `docs/proposals/compute-systems.md` (about 407 lines), no code changed. Nobody could be asked, so on
each open question the proposal takes the choice that is easiest to undo and lists them for the owner in its section 6
(*Decisions for the owner*): a lost node's runs cost the item an attempt, as any expired lease does today; the worker,
not the engine, counts a node's slots; secrets come from named files; a node's run environment is an allowlist;
sensors, daemons and AI blocks stay on the engine's machine in this milestone. "Worker" names the node's program
only, never an agent or a role (CLAUDE.md, *Words*, keeps "worker" away from the NOTES.md terms; the proposal says so
in its opening).

Round 2 (about 465 lines, still no code), answering every finding of review 1:
- The interlock (§2.2, §2.7): `start` and `renew` carry `left` seconds and the engine's monotonic `sent`, never a
  time of day. The worker times the deadline on its own suspend-counting clock as `sent + base + left`, where `base`
  is the least `heard − sent` over ten minutes, so the deadline is late by at most the fastest one-way transit and a
  delayed renewal cannot move it later. It sends SIGTERM at that deadline and SIGKILL `grace(ttl)/4` later. The
  engine sends a node a `start` only while its least ping round trip is at most `grace(ttl)/4`, so SIGKILL is sent
  by expiry + `grace(ttl)/2`, inside `terms.grace` and before the watchdog's second look. The wider claim is gone,
  and what the proposal does not claim (a suspended node, descendants that left the group) is said.
- Unknown is not gone (§2.4, §5): gone only on a reading from an allowlist. An unreadable record or a failed `ps`
  is `unknown`: the lease kept, a stop by group file or container name tried, and the lease left to expire.
- A `start` refused after the lease is given back uncounted, as `engine.py:1149-1150` does (§2.2).
- Engine-wide bounds (§3): at most 64 nodes and 256 runs on nodes over all pools, checked at `check` and counted at
  run time with the draining runs included.
The most reversible choices taken here: ten minutes for the window, 2 s for the ping, a quarter of the grace for
each bound, and 256 for the engine-wide ceiling. Each can change without changing the protocol.

Round 3 (about 500 lines, still no code), answering the one finding of review 2 (the deadline holder):
- A per-run **keeper** (§2.4) holds the deadlines and outlives the session: `worker.py --keep RUN`, detached by
  `setsid`, SIGHUP ignored, started before `started` is answered (`refused`, `no keeper`, uncounted, if it cannot
  start). It holds the wall deadline, fixed at start, and the lease deadline, which the worker moves forward through
  `runs/RUN/deadline` (written by replace; an unreadable file keeps the last deadline read), both on the node's own
  `CLOCK_BOOTTIME`. The process backend's run is its child (it writes the exit, in place of the wrapper, which only
  writes the exit, `runrecord.py:28`); for docker it waits with `docker wait`. At either deadline, or on the
  worker's `stop` file, it sends SIGTERM then SIGKILL (or `docker stop`, `docker rm -f`); after the run's end it
  removes the run's container and folder on `done` or a day later.
- §2.4, §2.7 (kill, wall timeout, the interlock's kill), §2.9 and gaps 3, 5 and 9 now agree: the kill and the
  cleanup are the keeper's; the worker only computes the deadline. Gap 5's test is a session cut *and* its worker
  ended, with the keeper's SIGKILL by expiry + `grace(ttl)/2`; gap 3 tests a closed stdin and a killed keeper.
- What is not claimed, said in §2.4: a keeper itself killed holds no deadline (the run's first process gets
  SIGKILL by `PR_SET_PDEATHSIG` on Linux; descendants and a container wait for the next worker, which reads the
  run as unknown and stops it by name); a login manager that ends a user's processes at logout ends the runs.
The most reversible choice taken here: a detached keeper per run rather than a resident per-node service (which
the owner would have to install and supervise), listed in §6. A keeper can become such a service later without
changing the protocol.
