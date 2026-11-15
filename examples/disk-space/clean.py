"""The cleaner: deletes a batch of the oldest files and prints how many % it freed.
ergostat runs it while the goal disk-under-80 is off, once per fresh reading."""
from sim import save, used

now = used()
freed = round(min(5.0, now), 1)          # one batch of old files
save(now - freed)
print(freed)
