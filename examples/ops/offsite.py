"""The off-site sync: copies the oldest backup not yet off site, one per run; says which it sent
(backup.sent-offsite) and that it moved one."""
from sim import say, world

with world() as w:
    bid = w["unsynced"].pop(0) if w["unsynced"] else None
if bid:
    say(out="flow.sent-offsite", moved=1)
    say(event="backup.sent-offsite", item=bid, data={"to": "offsite-bucket"})
else:
    print(0)
