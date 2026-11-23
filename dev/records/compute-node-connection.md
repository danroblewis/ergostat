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

## Where it stopped

Built (implementor, 2026-11-23, continued round 4). The review's one finding answered (lessons 3 and 8). In `_line`,
any exception from frames.decode other than `Bad` (the RecursionError of JSON nested deep enough) is a bad frame with
the fixed reason `line N: not JSON`. Each pass of `_run` is now wrapped, so any other fault of a session (a
TemporaryFile that can't be made before the try, among others) marks the node lost with `the session failed: KIND`
(the exception's class name, never its text), records compute.node.lost and tries again with the backoff. SPEC §12s.4's
Lost sentence now names both. test_lost_on_eof (still six tests) also runs a fake worker that sends a good hello and
then 200,000 `[`, and asserts compute.node.lost `line 2: not JSON` is recorded on at least two tries with the thread
alive. A third node, with tempfile.TemporaryFile monkeypatched to raise ENOSPC, must go lost with `the session failed:
OSError` and be tried again. I broke each fix on purpose and the test failed: without the `_line` catch the reason
read `the session failed: RecursionError`, and without the `_run` catch the node stayed `connecting` with nothing said.

Choice taken alone (the more reversible one): a node whose good hello is followed by a bad line goes in service and is
said up and lost again on each try, as a session that keeps ending would be. The backoff bounds how often.

Overrun reason: connection.py is now 321 lines plus 14 in engine.py against a budget of 200, for the reasons given in round 1; this round adds 5 net lines (the two catches).

## Where it stopped

Built (implementor, 2026-11-23, continued round 5). Main (ead497d1) merged in. The one docs/SPEC.md conflict, the
opening of §12s, keeps both sides in one sentence: main's keeper run "with its output sent by offset (12s.3)" and the
branch's engine session (12s.4). Main's "Nothing in the engine speaks to it yet" is dropped because this branch makes
it false. Main's "a model is unchanged by any of this" now reads "a model without `compute:` is unchanged", because
§12k's `compute:` opens sessions. No code changed this round, and no review findings were open apart from the conflict.

Overrun reason: connection.py is 321 lines plus 14 in engine.py against a budget of 200, for the reasons given in round 1; this round adds no lines.

## Where it stopped

Built (implementor, 2026-11-23, continued round 6). The review's one finding answered (lessons 4, 8). A hello no
longer resets the backoff or what was said. Only a session that stayed in service for three beats (30 s; `_steady`,
checked in the read loop) sets `tries` back to 0 and lets any reason be said again. A worker that says a good hello
and then dies or sends a bad line is now tried at 1, 2, 4 s and so on up to ten minutes. The record holds one
`compute.node.up` and one `compute.node.lost` for the whole run of tries: once a session that was said up ends before
it held, a later try's up is said only when its session holds three beats, and a lost reason that matches the last one
said is not said again. The round-4 record's "The backoff bounds how often" was false then and is true now. SPEC
§12s.4's backoff and record sentences say this. test_lost_on_eof's flapping worker (still six tests) now asserts five
tries spaced by at least 0.2, 0.4, 0.8 and 1.6 s and the record exactly [up, lost]. When the fifth try holds, it
asserts a second up is said only after three beats, with `tries` back to 0. test_backoff_and_return asserts `tries`
goes back to 0 only once the session has held. I broke each fix on purpose and each test failed: with a hello resetting
`tries` and `said`, the waits stayed at 0.2 s; with `_steady` not saying the deferred up, the record stayed [up, lost].

Choice taken alone (the more reversible one): a node that flaps, is then refused, and then holds is said up only once
it has held three beats (up to 30 s late), not at its hello. Saying it at once would mean resetting `upsaid` in `_out`
for a session that had no hello.

Overrun reason: connection.py is now 341 lines plus 14 in engine.py against a budget of 200, for the reasons given in round 1; this round adds about 20 net lines (the steady span that alone resets the backoff, and the deferred up).

## Where it stopped

Built (implementor, 2026-11-23, continued round 7). Main (e43046dc) merged in. The two docs/SPEC.md conflicts keep
both sides. §12k *Compute pools* now says a pool is declared, checked and connected to (the branch), and that a block
may name its pool with `runs-on:` and still runs here (main). The opening of §12s names the engine's session (the
branch) and says `runs-on:` is declared and checked only (main). Main's "nothing connects to a node" and "Nothing in
the engine speaks to it yet" are dropped because this branch makes them false. §12s.4's "still to be filled" no
longer lists `runs-on:`, which main has now added. No code changed this round, and no review findings were open
apart from the conflict.

Overrun reason: connection.py is 341 lines plus 14 in engine.py against a budget of 200, for the reasons given in round 1; this round adds no lines.
