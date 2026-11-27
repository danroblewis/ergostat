"""The planner, a stand-in for a person planning a roadmap: while fewer than two epics are unfinished, it plans the
next one, after the last, as a fan-out of tickets: design, then three in parallel, then integrate, then release.
Each line it prints is an event (SPEC 9.1): an item and its relations."""
import json
import os
import subprocess

ME = os.environ.get("ERGOSTAT_CMD", "ergostat").split()


def items(kind):
    out = subprocess.run([*ME, "item", "--projection", kind, "--json", "-n", "500"], capture_output=True, text=True).stdout
    return [i for i in json.loads(out or "{}").get("items", []) if i.get("projection") == kind]


def say(event, item, **data):
    print(json.dumps({"event": event, "item": item, "data": data}), flush=True)


epics = items("epic")
if sum(1 for e in epics if e["state"] != "shipped") < 2:
    n = max([int(e["id"].split("/e")[-1]) for e in epics] or [0]) + 1
    epic = f"epic/e{n}"
    say("epic.planned", epic, title=f"release {n}", **({"after": f"epic/e{n - 1}"} if n > 1 else {}))
    t = lambda name: f"ticket/e{n}-{name}"                      # noqa: E731
    plan = [("design", []), ("build-api", ["design"]), ("build-ui", ["design"]), ("docs", ["design"]),
            ("integrate", ["build-api", "build-ui"]), ("release", ["integrate", "docs"])]
    for name, after in plan:
        say("ticket.planned", t(name), title=f"{name} for release {n}", parent=epic, blocked_by=[t(a) for a in after])
