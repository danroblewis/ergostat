"""The backup job: dumps the database. Its age goes back to 0, and there is one more backup to
copy off site: the backup itself, an item (backup/7) that offsite.py later says it sent."""
import random
import time

from sim import HOUR, now, say, world

time.sleep(1.0)                               # the backup takes a while
with world() as w:
    age = (now() - w["last_backup"]) / HOUR
    w["last_backup"] = now()
    w["taken"] += 1
    bid = f"backup/{w['taken']}"
    w["unsynced"].append(bid)
say(out="flow.backed-up", moved=round(age, 1), note="database dumped")
say(out="flow.new-backups", moved=1)
say(event="backup.taken", item=bid, data={"database": "orders", "size_mb": round(random.uniform(380, 420)),
                                          "age_replaced_h": round(age, 1)})
