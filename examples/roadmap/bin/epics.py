"""Moves each epic along by its tickets, read through their relation to it (parent): underway once one has
started, shipped once every one is done. (A join, done by a block: docs/GAPS.md, built-in join.)"""
import json
import os
import subprocess

ME = os.environ.get("ERGOSTAT_CMD", "ergostat").split()


def items(kind):
    out = subprocess.run([*ME, "item", "--kind", kind, "--json", "-n", "500"], capture_output=True, text=True).stdout
    return [i for i in json.loads(out or "{}").get("items", []) if i.get("kind") == kind]


kids = {}
for t in items("ticket"):
    for p in t["fields"].get("parent") or []:
        kids.setdefault(p, []).append(t["state"])
for e in items("epic"):
    states = kids.get(e["id"], [])
    if not states:
        continue
    if e["state"] == "planned" and any(s != "todo" for s in states):
        print(json.dumps({"event": "epic.started", "item": e["id"]}), flush=True)
    elif e["state"] != "shipped" and all(s == "done" for s in states):
        print(json.dumps({"event": "epic.shipped", "item": e["id"]}), flush=True)
