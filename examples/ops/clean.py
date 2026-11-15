"""The cleaner: deletes a batch of the oldest files and prints how many % it freed."""
from sim import world

with world() as w:
    freed = round(min(5.0, w["used"]), 1)
    w["used"] -= freed
print(freed)
