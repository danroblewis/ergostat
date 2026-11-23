# compute-runs-on-config: runs-on: on a block names its pool, with the refusals for blocks that cannot run on a node

depends-on: [compute-pools-config]

Problem: with pools declared, a block still cannot say it runs on one: there is no `runs-on:` key. Change in ergostat/compute/compile.py and the block compiler: `runs-on: POOL|local` becomes Block.runs_on in the IR. Errors with their place: an unknown pool; runs-on on a daemon, sensor or ai block; runs-on on a command that uses calls (ERGOSTAT_CMD, ERGOSTAT_SOCKET, `ergostat `), until compute-calls-from-node lifts it; a pool used by blocks of two shards. Nothing runs differently yet: runner() still returns local. Done: each refusal has its code; a block with `runs-on: local` or none compiles to an identical IR; the schema (schema/ergostat.schema.json) and SPEC's block keys list runs-on. Files: ergostat/compute/compile.py, ergostat/spec/compile.py, ergostat/spec/ir.py, schema, tests/test_compute_compile.py, docs/SPEC.md. Full text: wave2-compute.md (the runs-on half of compute-pools-config). Budget: 90 net lines.

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
- attempt 6: nack the run ended with gap/compute-runs-on-config still parked

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:06).

Stopped on its last attempt by RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 678, in session
    out = agents.session(cfg, role, brief, work, keep=kept)
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 204, in session
    egress(cfg)
    ~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 117, in egress
    _egress(cfg)
    ~~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 124, in _egress
    docker("network", "create", "--internal", NET)
    ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 106, in docker
    raise RuntimeError(f"docker {args[0]}: {r.stderr.strip()[-300:]}")
RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:07).

Its runs failed past their attempts (a dead letter):
- attempt 2: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 3: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 4: nack exited 1
- attempt 5: nack the run ended with gap/compute-runs-on-config-continued still parked

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:21).

Its runs failed past their attempts (a dead letter):
- attempt 3: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 4: nack exited 1
- attempt 5: nack the run ended with gap/compute-runs-on-config-continued still parked
- attempt 6: nack the implementor pool is full (run/pools.json): waits its turn
