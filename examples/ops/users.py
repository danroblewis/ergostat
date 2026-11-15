"""Stands in for the users (a simulation, not part of the platform): a few jobs every run, and a
burst of 30 every 30 seconds. Prints how many arrived."""
import random

from sim import now, world

with world() as w:
    arrived = max(0, round(random.gauss(5, 2)))
    if now() - w["last_burst"] >= 30:
        w["last_burst"] = now()
        arrived += 30
    w["waiting"] += arrived
print(arrived)
