"""The off-site sync: copies one backup off site per run, and prints 1 (what it moved)."""
from sim import world

with world() as w:
    w["unsynced"] -= 1
print(1)
