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
    item=$(bin/py bin/session.py start "$role" "$model")        # an item from the moment it starts (Items: session)
    claude -p --model "$model" --output-format json --permission-mode acceptEdits \
        --allowedTools "Bash(bin/py:*)" "Bash(python3:*)" "Bash(git:*)" "Bash(ls:*)" "Bash(cat:*)" Read Edit Write Glob Grep \
        | bin/py bin/session.py finish "$item"
    exit $?
fi
exec bin/py "bin/standin_$role.py"
