#!/bin/sh
# The researcher's and the developer's machine. ergostat gives it the prompt, then the block's
# JSON input, on standard input.
#
#   FACTORY_AI=claude   a Claude Code session does the work (claude -p, reading and editing files,
#                       running bin/py, bin/lab.py and git in this folder); real tokens, minutes
#   (unset)             a stand-in program: free, seconds, works from a fixed notebook of ideas
#
# Models, per role (any name `claude --model` takes): the researcher has to read every result so
# far and think of something new, the developer only to build one idea, so by default
#   FACTORY_RESEARCHER_MODEL=sonnet  FACTORY_DEVELOPER_MODEL=haiku
# (FACTORY_MODEL sets both.)
role="$1"
cd "$(dirname "$0")/.." || exit 1
if [ "${FACTORY_AI:-}" = "claude" ]; then
    case "$role" in
        researcher) model="${FACTORY_RESEARCHER_MODEL:-${FACTORY_MODEL:-sonnet}}" ;;
        *) model="${FACTORY_DEVELOPER_MODEL:-${FACTORY_MODEL:-haiku}}" ;;
    esac
    mkdir -p run
    # its answer to ergostat, its cost and turns to run/costs.jsonl (claude's JSON output, read apart)
    claude -p --model "$model" --output-format json --permission-mode acceptEdits \
        --allowedTools "Bash(bin/py:*)" "Bash(python3:*)" "Bash(git:*)" "Bash(ls:*)" "Bash(cat:*)" Read Edit Write Glob Grep \
        | bin/py -c '
import json, sys, time
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except ValueError:
    print(raw); raise SystemExit(1)
with open("run/costs.jsonl", "a") as f:
    f.write(json.dumps({"at": time.time(), "role": sys.argv[1], "model": sys.argv[2], "cost_usd": d.get("total_cost_usd"),
                        "turns": d.get("num_turns"), "seconds": round((d.get("duration_ms") or 0) / 1000, 1),
                        "error": d.get("is_error")}) + "\n")
print(d.get("result") or "")
raise SystemExit(1 if d.get("is_error") else 0)' "$role" "$model"
    exit $?
fi
exec bin/py "bin/standin_$role.py"
