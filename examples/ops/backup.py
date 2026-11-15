"""The backup job: dumps the database. Its age goes back to 0, and there is one more backup to
copy off site."""
import time

from sim import HOUR, now, say, world

time.sleep(1.0)                               # the backup takes a while
with world() as w:
    age = (now() - w["last_backup"]) / HOUR
    w["last_backup"] = now()
    w["unsynced"] += 1
say(out="flow.backed-up", moved=round(age, 1), note="database dumped")
say(out="flow.new-backups", moved=1)
