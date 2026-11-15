"""The sensor: how old the newest backup is, in simulated hours. It only reads."""
from sim import HOUR, now, world

with world() as w:
    print(round((now() - w["last_backup"]) / HOUR, 1))
