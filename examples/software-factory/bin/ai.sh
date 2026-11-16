#!/bin/sh
# The developer's and the reviewer's machine. ergostat gives it the prompt, then the block's JSON
# input, on standard input.
#
#   FACTORY_AI=claude   a Claude Code session does the work (claude -p, editing files, running
#                       python3 and git in this folder); costs real tokens, minutes per ticket
#   (unset)             a stand-in program does it: free, seconds per ticket, makes mistakes on purpose
role="$1"
cd "$(dirname "$0")/.." || exit 1
if [ "${FACTORY_AI:-}" = "claude" ]; then
    exec claude -p --permission-mode acceptEdits \
        --allowedTools "Bash(python3:*)" "Bash(git:*)" "Bash(ls:*)" "Bash(cat:*)" "Bash(diff:*)" Read Edit Write Glob Grep \
        ${FACTORY_MODEL:+--model "$FACTORY_MODEL"}
fi
exec python3 "bin/standin_$role.py"
