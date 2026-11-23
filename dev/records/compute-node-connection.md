# compute-node-connection: The engine's connection to each node of a pool: session, hello, beats, loss and reconnect

depends-on: [compute-pools-config, compute-worker-protocol]

Problem: the engine has no way to reach a worker (compute-systems.md sections 2.1, 3). This gap is the session; round trips and the status shown are compute-node-status. Change: ergostat/compute/connection.py, one Node per entry of each declared pool, named POOL/N by its place in the list and never by host, started with the engine and closed on close or swap: a subprocess (`ssh -T -o BatchMode=yes HOST ergostat worker --stdio`, or the pool's connect: argv) with pipes, one reader thread, stderr kept in the pool's log. It parses hello (version 1 only; labels must include the pool's), marks the node lost after three missed beats (30 s) or EOF, reconnects with backoff from 1 s doubling to ten minutes, and exposes request(msg) with ids and a timeout, and on(type, fn). Done: a connect: pool comes up; killing the worker loses the node at EOF, SIGSTOP after three beats; it returns with backoff; another v leaves the node out of service with the error kept; closing the engine ends every session and leaves no ssh or worker child; no host name, address or user appears in logs or events. Files: ergostat/compute/connection.py, ergostat/spec/engine.py, tests/test_compute_connection.py (six tests), docs/SPEC.md. Full text: wave2-compute.md (compute-node-connection, the session half). Budget: 200 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:15).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:15).

Its runs failed past their attempts (a dead letter):
- attempt 3: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 4: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 5: nack exited 1
- attempt 6: nack the run ended with gap/compute-node-connection still parked

## Where it stopped

Built (implementor, 2026-11-23, continued round 1). ergostat/compute/connection.py (Node, Pools), the engine's
start/swap/close wiring in ergostat/spec/engine.py, the six tests of tests/test_compute_connection.py, SPEC §12s.4
*The engine's connection* (and the two "nothing connects yet" sentences of §12k and §12s corrected). Nothing left
within the definition; round trips, `least_rtt`, the status in the heartbeat and `/api/status` are compute-node-status's.

Choices taken alone (each the more reversible one):
- A refused node (another `v`, labels lacking, a bad `slots`, the worker's `error`) is tried again with the same
  backoff as a lost one, staying refused with its error kept until a hello is taken: a worker upgraded in place comes
  back without an engine restart. Never retrying is one line (`break` after a refusal) if the owner wants it.
- A session's stderr is kept in an unnamed temporary file and written into the pool's log (its last MiB, the ssh host
  replaced by POOL/N) when the session ends, not line by line: the one reader thread stays the only thread per node,
  and a host ssh prints is never on disk as printed. A `connect:` argv's words are the owner's and are not rewritten.
- Under shards only the lead engine connects (one session per node per engine process).
- Events: `compute.node.up`, `compute.node.lost`, `compute.node.refused`, each said once per new reason.

Overrun reason: connection.py is 302 lines (about 267 not blank) plus 14 in engine.py against a budget of 200, because the session half carries the fail-closed hello checks (version, seq, labels, slots), the process-group kill and reap held under the node's lock so close never races a spawn or signals a reaped group (lessons 1, 6), the redaction of ssh's stderr that the no-host done item needs, the run-time 64-node ceiling counting sessions still closing (lesson 4), and the swap sync that closes only pools changed or removed; the plan's own budget for this gap with status and pings was 280.

## Where it stopped

Built (implementor, 2026-11-23, continued round 2). The review's one finding answered: rewriting the `ssh:` alias in
ssh's stderr was a denylist (once ssh reads its config it prints the real HostName, address and user). An `ssh:`
session's stderr now goes to /dev/null and the pool's log gets only `POOL/N ssh exited N; its standard error is not
kept`, so nothing ssh writes is kept (an allowlist of one line ergostat writes itself). The fake ssh of
test_engine_starts_and_closes_every_session_and_never_names_a_host now prints `connect to host 10.1.2.3`,
`Could not resolve hostname real.example.com`, `alice@real.example.com: Permission denied` and its alias, and the
test asserts none of them is in the log, the record or what the engine says. Broken on purpose (ssh's stderr kept),
that assertion failed on all four. The two SPEC §12s.4 sentences are narrowed: a `connect:` command's own stderr is
kept as written, and the no-host promise covers the record, what the engine says and ergostat's own log lines.

Choice taken alone (the more reversible one): the worker's own diagnostics, which come back over ssh's stderr, are
dropped with ssh's because the two can't be told apart. Keeping a worker line would need an allowlist of its forms
(or the worker sending its diagnostics as frames), which can come later without changing anything here.

Overrun reason: connection.py is now 307 lines plus 14 in engine.py against a budget of 200, for the reasons given in round 1; this round adds 5 net lines (the ssh exit-status line in place of the alias regex).

## Where it stopped

Built (implementor, 2026-11-23, continued round 3). Main (bf6dbebf) merged in; the one SPEC §12s conflict kept both
sides (the keeper's run of 12s.3 and the engine's session of 12s.4 in one sentence). The review's one finding
answered: a reason kept for a node (its `error`, compute.node.refused/lost `why`, what the engine says, the log) is
now an allowlist of ergostat's own words. A worker's `error` hello reads `the worker refused; its reason is not kept`
(its text can hold its root under the remote user's home); a first frame of another type reads `its first line is
not hello` (the type is the worker's text); a bad frame's reason is kept only in the fixed forms frames.decode writes
with whole numbers (`protocol v2 is not v1`, `seq 3 where 2 was next`), else `its protocol is not v1` or `its seq is
out of order` (a `v` or `seq` string was echoed through repr). SPEC §12s.4's "or the worker's own `error`" is
replaced by the fixed reason and the rule. test_another_version_is_refused_with_its_error_kept now also runs three
fake workers (an `error` hello naming /home/alice, a hello with `v: "/home/alice"`, a first frame of type `alice`)
and asserts each fixed reason and that `alice` is in neither the record, what is said, status() nor the log. Broken
on purpose, it failed both ways: the worker's `why` kept verbatim, and `_bad` passing every reason through.

Choice taken alone (the more reversible one): the worker's refusal text is dropped rather than matched against an
allowlist of serve.py's Refused forms, since those forms are another gap's and change with it; an allowlist can be
added later in `_hello` without changing anything else.

Overrun reason: connection.py is now 316 lines plus 14 in engine.py against a budget of 200, for the reasons given in round 1; this round adds 9 net lines (the allowlist of bad-frame reasons and the fixed refusal).
