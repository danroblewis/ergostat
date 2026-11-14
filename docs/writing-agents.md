# Writing an agent

An agent is any program ergostat can run: a shell script, a Python file, a binary, a `claude -p`
call. It fills the roles the model gives it (sensors, controllers, valves), and it talks to
ergostat in JSON lines.

## The shape of a run

1. ergostat starts the command in the repository, when its schedule says: `every = "5m"`,
   `cron = "0 3 * * *"`, or `on = ["loop.off"]` (event types it listens for).
2. It writes one JSON object to the program's stdin, then closes it:

   ```json
   {"agent": "disk-cleaner", "kind": "program",
    "roles": [{"kind": "sensor", "name": "disk-usage"}, {"kind": "controller", "name": "disk-under-80"},
              {"kind": "valve", "name": "delete-old-files"}],
    "state": {"disk-used": 71.2},
    "controllers": {"disk-under-80": {"holds": "disk-used", "setpoint": "<= 80", "value": 71.2, "error": 0,
                                      "drives": ["delete-old-files"]}},
    "trigger": null}
   ```

   `trigger` is the event that started the run (for `on`), or null for a scheduled one. Reading
   stdin is optional.
3. The program prints what happened, one JSON object per line, each naming the part it is for.
   Anything else it prints goes to its log (`ergostat agent NAME` shows the end of it).
4. Its exit code: not 0 is a failed run, and shows in the status.

## What it can say

| Line | Means | Recorded as |
|---|---|---|
| `{"sensor": "disk-usage", "value": 71.2}` | a reading | a measurement, `sensor/disk-usage` |
| `{"controller": "disk-under-80", "decision": "over 80: free 15%"}` | a decision | `controller.decided` |
| `{"valve": "delete-old-files", "amount": 15}` | the valve moved this much | `valve.opened` |
| `{"valve": "process-jobs", "position": 4}` | how far the valve stands open | a measurement, `valve/process-jobs` |
| `{"event": "backup.requested", "item": "database", "data": {...}}` | anything else that happened | an event of that type |

An agent may only name parts it fills; anything else is refused, and the refusal is recorded. The
event types under `agent.`, `loop.`, `valve.`, `controller.`, `model.` and `ergostat.` are
ergostat's own. Give events an `item`: what the work is about (`database`, `docs/install.md`), so
`ergostat item` can fold them.

## Three small agents

A sensor, in shell (it fills one role):

```sh
#!/bin/sh
printf '{"sensor": "inbox-count", "value": %s}\n' "$(ls inbox | wc -l | tr -d ' ')"
```

A sensor, controller and valve in one program, in Python:

```python
import json, shutil, sys

ctx = json.load(sys.stdin)
used = 100 * (1 - shutil.disk_usage("/data").free / shutil.disk_usage("/data").total)
print(json.dumps({"sensor": "disk-usage", "value": round(used, 1)}))
if used > 80:
    freed = clean_oldest_until(65)          # yours
    print(json.dumps({"controller": "disk-under-80", "decision": f"over 80: freed {freed:.1f}%"}))
    print(json.dumps({"valve": "delete-old-files", "amount": freed}))
else:
    print(json.dumps({"controller": "disk-under-80", "decision": "under 80: nothing to do"}))
```

A rule that listens for a loop going off, and hands on to another agent with an event:

```python
import json, sys

ctx = json.load(sys.stdin)
if (ctx["trigger"] or {}).get("item") == "backup-fresh":
    print(json.dumps({"controller": "backup-fresh", "decision": "too old: request a backup"}))
    print(json.dumps({"event": "backup.requested", "item": "database"}))
```

```toml
[[agent]]
name = "backup-policy"
kind = "rule"
command = "python3 policy.py"
on = ["loop.off"]
```

## Trying it

- By hand, without ergostat: `echo '{"roles": [], "state": {}, "controllers": {}, "trigger": null}' | ./agent.sh`
- Once, through ergostat, recorded like any run: `ergostat agent NAME --now`. It prints what the
  agent said, what was refused, and the end of its log.
- `ergostat check` warns when a command is not found, a part has no agent, or a loop cannot close.

## Limits

- `timeout = "30s"` (default five minutes): a run past it is stopped, with everything it started
  (each run is its own process group), and the run is recorded as failed.
- One run at a time per agent. A scheduled run is skipped while the last one is still waiting.
- The environment has `ERGOSTAT_AGENT`, `ERGOSTAT_RUN` (the run's event id), `ERGOSTAT_PROJECT` and
  `ERGOSTAT_STATE_DIR`.

## Moving down the ladder

Start with whatever does the job, often an AI agent. When `ergostat` says a controller decided the
same thing most of the time, replace its agent with a cheaper one (a decision, a program, a rule)
that says the same lines. The model does not change; only the agent filling the role does.
