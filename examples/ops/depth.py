"""The sensor: jobs waiting in the queue. It only reads."""
from sim import world

with world() as w:
    print(w["waiting"])
