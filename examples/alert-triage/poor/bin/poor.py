"""The poor model's stand-ins: the same work as ../bin/step.py, with inconsistent event names, and the facets
opened and finished by a scheduled sweep, whose runs no item caused."""
import json
import os
import random
import shlex
import subprocess
import sys
import time


def say(event, item, data=None):
    print(json.dumps({"event": event, "item": item, "data": data or {}}), flush=True)


def items(kind):
    cmd = shlex.split(os.environ.get("ERGOSTAT_CMD") or "ergostat -C .")
    got = subprocess.run([*cmd, "item", "--projection", kind, "-n", "10000", "--json"], capture_output=True, text=True)
    try:
        return json.loads(got.stdout or "{}").get("items") or []
    except ValueError:
        return []


if sys.argv[1] == "handle":
    item = os.environ["ERGOSTAT_ITEM"]
    time.sleep(random.uniform(0.5, 2))
    state = next((i.get("state") for i in items("alert") if i["id"] == item), "new")
    if state in ("new", "leased") and random.random() < 0.2:
        say("alerts.noise", item)
    elif state in ("new", "leased"):
        say("triage.finished", item)
    else:
        say("alert.escalate" if random.random() < 0.3 else "summary.written", item)
else:                                                      # the sweep: on a schedule, caused by nothing
    facets = items("facet")
    for a in items("alert"):
        mine = [f for f in facets if (f.get("fields") or {}).get("alert") == a["id"]]
        if a.get("state") == "triaged" and not mine:
            for f in ("logs", "deploys", "metrics"):
                say("facet.opened", f"facet/{a['id'].split('/')[1]}-{f}", {"alert": a["id"]})
            say("alert.investigate", a["id"])
        elif a.get("state") == "investigating" and mine:
            for f in mine:
                if f.get("state") == "open":
                    say("facet.complete", f["id"])
            if all(f.get("state") == "done" for f in mine):
                say("investigation.complete", a["id"])
