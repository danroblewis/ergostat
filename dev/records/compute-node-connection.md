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
