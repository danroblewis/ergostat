#!/bin/sh
# measure the inbox, decide, and process up to three files, saying each move as it is made
# (a run stopped midway then leaves an honest record)
mkdir -p inbox outbox
n=$(ls inbox | wc -l | tr -d ' ')
printf '{"sensor": "inbox-count", "value": %s}\n' "$n"
if [ "$n" -le 5 ]; then
  printf '{"controller": "inbox-empty", "decision": "%s waiting: within the setpoint, process anyway"}\n' "$n"
else
  printf '{"controller": "inbox-empty", "decision": "%s waiting: process three"}\n' "$n"
fi
for f in $(ls inbox | head -3); do
  tr '[:lower:]' '[:upper:]' < "inbox/$f" > "outbox/$f" && rm "inbox/$f" \
    && printf '{"valve": "process-files", "amount": 1}\n{"event": "file.processed", "item": "%s"}\n' "$f"
done
exit 0
