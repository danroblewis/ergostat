#!/bin/sh
# An AI agent filling a controller: ergostat gives it the state on stdin; Claude decides; this
# script turns the answer into ergostat's lines. Fill a controller (and a valve) with an agent:
#
#   [[agent]]
#   name = "triage"
#   kind = "ai"
#   command = "examples/ai-controller.sh triage-prompt.md"
#   every = "15m"
#
# The prompt file says what the loop is for and how to decide. Claude must answer with exactly one
# JSON object: {"decision": "...", "act": true|false, "amount": N, "why": "..."}.
# Needs Claude Code (claude) on PATH; it runs with your own login.
set -eu
prompt="$1"
context=$(cat)                                   # what ergostat gave this run
controller=$(printf '%s' "$context" | python3 -c 'import json,sys; c=json.load(sys.stdin); print(next(iter(c["controllers"])))')
valve=$(printf '%s' "$context" | python3 -c 'import json,sys; c=json.load(sys.stdin); print(next((r["name"] for r in c["roles"] if r["kind"]=="valve"), ""))')
answer=$(printf '%s\n\n## The state, from ergostat\n\n%s\n\nAnswer with one JSON object only.\n' "$(cat "$prompt")" "$context" \
         | claude -p --output-format text 2>/dev/null)
printf '%s' "$answer" | CONTROLLER="$controller" VALVE="$valve" python3 -c '
import json, os, re, sys
text = sys.stdin.read()
m = re.search(r"\{.*\}", text, re.S)
if not m:
    print("no JSON in the answer:", text[:300], file=sys.stderr); sys.exit(1)
a = json.loads(m.group(0))
print(json.dumps({"controller": os.environ["CONTROLLER"], "decision": a.get("decision") or "(no words)",
                  **({"why": a["why"]} if a.get("why") else {})}))
if a.get("act") and os.environ.get("VALVE"):
    # the acting itself stays a program you write and trust; here it is only reported
    print(json.dumps({"valve": os.environ["VALVE"], "amount": float(a.get("amount") or 1)}))
'
