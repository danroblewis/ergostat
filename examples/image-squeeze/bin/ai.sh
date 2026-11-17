#!/bin/sh
# The researcher's, the developer's and the improver's machine. ergostat gives it the prompt, then the block's
# JSON input, on standard input.
#
#   FACTORY_AI=claude   a Claude Code session does the work (claude -p, reading and editing files,
#                       running bin/py, bin/lab.py and git in this folder); real tokens, minutes
#   (unset)             a stand-in program: free, seconds, works from a fixed notebook of ideas
#
# Models, per role (any name `claude --model` takes): the researcher has to read every result so
# far and think of something new, the developer only to build one idea, so by default
#   FACTORY_RESEARCHER_MODEL=sonnet  FACTORY_DEVELOPER_MODEL=haiku  FACTORY_IMPROVER_MODEL=sonnet
# (FACTORY_MODEL sets all three.) The improver reviews the model with ergostat's tools (MCP), reads the
# files, and changes none: it only proposes.
role="$1"
cd "$(dirname "$0")/.." || exit 1
if [ "${FACTORY_AI:-}" = "claude" ]; then
    case "$role" in
        researcher) model="${FACTORY_RESEARCHER_MODEL:-${FACTORY_MODEL:-sonnet}}" ;;
        improver) model="${FACTORY_IMPROVER_MODEL:-${FACTORY_MODEL:-sonnet}}" ;;
        *) model="${FACTORY_DEVELOPER_MODEL:-${FACTORY_MODEL:-haiku}}" ;;
    esac
    exec bin/py bin/session.py run "$role" "$model"     # a session item, its transcript kept as it grows (Items: session)
fi
exec bin/py "bin/standin_$role.py"
