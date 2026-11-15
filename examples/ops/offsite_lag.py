"""The sensor: backups taken but not yet copied off site. It only reads."""
from sim import world

with world() as w:
    print(w["unsynced"])
