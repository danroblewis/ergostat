"""Every agent here measures its stock, and drains it when it is over: a made-up platform."""
import json
import random
import sys

from sim import say, world

ctx = json.load(sys.stdin)
roles = {r["kind"]: r["name"] for r in ctx["roles"]}
stock = roles["sensor"].removesuffix("-count")
with world({}) as w:
    v = w.get(stock, 0)
    if stock.endswith("q0"):                      # work arrives only at the head of each chain
        v += random.choice([0, 1, 1, 2, 3])
    say(sensor=roles["sensor"], value=v)
    c = ctx["controllers"][roles["controller"]]
    limit = float(c["setpoint"].split()[-1])
    if v > limit:
        n = int(v - limit // 2)
        v -= n
        nxt = stock[:-1] + str(int(stock[-1]) + 1) if stock[-1] in "012" else None
        if nxt:
            w[nxt] = w.get(nxt, 0) + n
        say(controller=roles["controller"], decision=f"{v + n} over {limit:g}: drain {n}")
        say(valve=roles["valve"], amount=n)
    else:
        say(controller=roles["controller"], decision="within: wait")
    w[stock] = v
