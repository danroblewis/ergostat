"""The demo's own test issues: the harness, not the factory. Everything it creates is written down in
SCRATCH/created.json, and cleanup touches only that.

    demo_issues.py create [N] [--title T] [--body B]   create N issues (at most 3 at once) in JIRA_PROJECT, labelled
    demo_issues.py list                                 the issues it created, as Jira has them now
    demo_issues.py cleanup [--delete]                   for each: close its pull request and delete the branch if
                                                        still open; move the issue to Done (or delete it)

Never run this at work: there, the issues are real.
"""

from __future__ import annotations

import argparse
import sys
import time

import github
import jira
from tf import SCRATCH, conf, items, read_json, write_json

CREATED = SCRATCH / "created.json"
BODIES = [
    "Add a file `work/{key}.txt` with a two-line greeting to the team, in Portuguese and in English.",
    "Add a file `work/{key}.txt` that describes, in one sentence, what a stock and a flow are.",
    "Add a file `work/{key}.txt` listing three prime numbers above 100, one per line.",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=["create", "list", "cleanup"])
    ap.add_argument("n", nargs="?", type=int, default=1)
    ap.add_argument("--title")
    ap.add_argument("--body")
    ap.add_argument("--delete", action="store_true")
    a = ap.parse_args()
    made = read_json(CREATED, [])
    if a.what == "create":
        if a.n > 3:
            sys.exit("at most 3 test issues at once")
        for i in range(a.n):
            title = a.title or f"[ergostat demo] {time.strftime('%H:%M')} test ticket {len(made) + 1}"
            body = (a.body or BODIES[(len(made)) % len(BODIES)]) + f"\n\nrepo: {conf('GITHUB_REPO')}"
            key = jira.create(title, body.replace("{key}", "<this issue's key>"))
            made.append({"key": key, "created": time.time()})
            write_json(CREATED, made)
            print(f"created {key}: {title}")
        return 0
    if a.what == "list":
        for m in made:
            try:
                i = jira.get(m["key"])
                print(f"{m['key']:10} {i['status']:12} {i['summary']}")
            except jira.JiraError as e:
                print(f"{m['key']:10} {'(gone)':12} {e}")
        return 0
    tickets = {t["id"].split("/", 1)[1]: t for t in items("ticket")}
    for m in made:
        if m.get("cleaned"):
            continue
        f = (tickets.get(m["key"]) or {}).get("fields", {})
        if f.get("pr"):
            p = github.pr(f["repo"], f["pr"])
            if p["state"] == "OPEN":
                print(f"{m['key']}: closing #{f['pr']}", github.close(f["repo"], f["pr"], delete_branch=True))
            else:
                print(f"{m['key']}: #{f['pr']} is {p['state'].lower()}")
        if f.get("branch") and f.get("repo"):
            print(f"{m['key']}: branch {f['branch']}:", github.delete_branch(f["repo"], f["branch"]))
        try:
            if a.delete:
                jira.delete(m["key"])
                print(f"{m['key']}: deleted")
            else:
                print(jira.transition(m["key"], conf("JIRA_DONE")))
            m["cleaned"] = time.time()
        except jira.JiraError as e:
            print(f"{m['key']}: {e}")
        write_json(CREATED, made)
    return 0


if __name__ == "__main__":
    sys.exit(main())
