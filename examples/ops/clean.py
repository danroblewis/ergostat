from sim import say, world

with world({"used": 60.0, "written": 0.0}) as w:
    w["used"] += w.pop("written", 0.0) + 0.4
    say(sensor="disk-usage", value=round(w["used"], 1))
    if w["used"] > 80:
        freed = round(w["used"] - 65, 1)
        w["used"] -= freed
        say(controller="disk-under-80", decision=f"over 80: free {freed}%")
        say(valve="delete-old-files", amount=freed)
    else:
        say(controller="disk-under-80", decision="under 80: nothing to do")
    w["written"] = 0.0
