import time

from sim import now, say, world

time.sleep(1.0)                               # the backup takes a while
with world({"last_backup": now(), "unsynced": 0}) as w:
    age = (now() - w["last_backup"]) / 2.0
    w["last_backup"] = now()
    w["unsynced"] = w.get("unsynced", 0) + 1
say(valve="run-backup", amount=round(age, 1), note="database dumped")
say(valve="record-backup", amount=1)
