from sim import say, world

with world({"unsynced": 0}) as w:
    n = w.get("unsynced", 0)
    say(sensor="offsite-lag", value=n)
    if n > 1:
        w["unsynced"] = n - 1
        say(controller="offsite-current", decision=f"{n} waiting: copy one")
        say(valve="copy-offsite", amount=1)
    else:
        say(controller="offsite-current", decision="up to date")
