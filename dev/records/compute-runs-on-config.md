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

## Where it stopped

Built (implementor, 2026-11-23, gap/compute-runs-on-config-continued-continued round 1). Nothing is left of the
definition. Choices made with no one to ask, each the more reversible one:

- One file outside the Files list: ergostat/numbers/version.py (1 line). `Block.runs_on` is a new dataclass field, and
  `_plain` hashes every field, so with no change every model's `whole`, `control` and each block's `part` hash would
  move on upgrade (reopening dismissed findings about blocks) even with no `runs-on:` written. The field is marked
  `metadata={"unset": None}` and `_plain` leaves out a field at its unset value, so a model with no `runs-on` (or
  `runs-on: local`) hashes as it did on main; naming a pool is still a control change
  (test_runs_on_local_or_none_compiles_to_an_identical_ir).
- `runs-on` on a person block is refused too (`runs-on-person`): the definition names daemon, sensor and ai; a person
  is run by no machine. `local` is refused as a pool's name (`bad-name`), since `runs-on: local` means here.
- Calls are found in the `run:` text and in the model-folder file its first word names (read whole; unreadable or
  over 8 MiB counts as calling, never as clean). A program that reaches the socket by other means is not seen; SPEC
  says so.
- `pool-across-shards` is worked out from `shards.plan(spec)` (the default ceiling of 16 shards, the most split an
  engine makes), only for a model with no other error, since such a model is refused already. Said at the second
  block's `runs-on`.

## Where it stopped

Built (implementor, 2026-11-23, gap/compute-runs-on-config-continued-continued round 2). Main (ead497d1) merged; the
conflict in ergostat/spec/ir.py kept both main's `Block.law` and the branch's `Block.runs_on` (unset at None, so
hashes are as on main). Round 1's finding is answered: `calls()` resolves the first word (following links) and reads
it only when it is under the model's folder. An absolute path, a `..` out of the folder or a link out is not read,
and only the command text is checked (SPEC §12k says so). Test:
test_a_file_outside_the_model_folder_is_not_read_for_calls, which failed when I removed the folder check.
Overrun reason: 95 net lines against 90; the five over are the folder check on the script read that round 1's review asked for.

## Where it stopped

Built (implementor, 2026-11-23, gap/compute-runs-on-config-continued-continued round 3). The queue's finding is
answered. tests/test_library_trust.py::test_every_compile_key_classified failed because the new `runs-on` key was in
no trust table (sensor, program, ai, person). ergostat/library/trust.py now refuses it by name to a library template,
in MACHINE_NO and SENSOR: only the owner names the machine a block runs on. That is one file outside the Files list,
2 lines. Refusing is the more reversible choice, because allowing it later loosens nothing already written. SPEC §2a
says so. The test failed before the change and passes after it (48 passed in the file).
Overrun reason: 97 net lines against 90; five are round 2's folder check on the script read, and two are the trust-table lines that classify `runs-on` for library templates.
