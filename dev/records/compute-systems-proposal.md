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
