"""The autoscaler, a rule: more workers when the queue is long, fewer when it is short."""
from sim import say, world

with world({"waiting": 0, "workers": 2}) as w:
    q, n = w["waiting"], w["workers"]
    if q > 20 and n < 8:
        w["workers"] = n + 1
        say(controller="queue-short", decision=f"{q} waiting: open to {n + 1} workers")
    elif q < 5 and n > 1:
        w["workers"] = n - 1
        say(controller="queue-short", decision=f"{q} waiting: close to {n - 1} workers")
    else:
        say(controller="queue-short", decision=f"{q} waiting: hold at {n} workers")
