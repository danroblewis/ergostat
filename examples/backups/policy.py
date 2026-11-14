import json
import sys

ctx = json.load(sys.stdin)
trig = ctx.get("trigger") or {}
if trig.get("item") == "backup-fresh":
    say = lambda **x: print(json.dumps(x))  # noqa: E731
    say(controller="backup-fresh", decision="too old: request a backup")
    say(event="backup.requested", item="database", data={"age": ctx["state"].get("hours-since-backup")})
