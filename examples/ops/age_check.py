from sim import now, say, world

with world({"last_backup": now() - 40}) as w:
    hours = (now() - w["last_backup"]) / 2.0
say(sensor="backup-age", value=round(hours, 1))
