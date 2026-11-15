"""One script for the whole made-up platform; the shared state is the simulation (.sim.json).

    python3 tick.py count web-q0            a sensor: prints how many items web-q0 holds
    python3 tick.py arrive web-q0           a load generator: adds 0-3 items to web-q0, prints how many
    python3 tick.py drain web-q0 web-q1     a worker: moves web-q0 down to half its goal, into web-q1
    python3 tick.py drain web-q3            (no second queue: the items leave the platform)
"""
import json
import random
import sys

from sim import world

what, queue, *rest = sys.argv[1:]
nxt = rest[0] if rest else None

with world({}) as w:
    v = w.get(queue, 0)
    if what == "count":
        print(v)
    elif what == "arrive":
        n = random.choice([0, 1, 1, 2, 3])
        w[queue] = v + n
        print(n)
    elif what == "drain":
        ctx = json.load(sys.stdin)                       # what ergostat gives a block: its goal among it
        goal = next(iter(ctx["goals"].values()))
        limit = float(goal["hold"].split()[-1])          # "<= 5"
        n = max(0, v - int(limit // 2))
        w[queue] = v - n
        if nxt:
            w[nxt] = w.get(nxt, 0) + n
        print(n)                                         # what it moved along its one flow
