#!/bin/sh
# over 20 in outbox/: move the oldest to archive/ until 10 are left, saying each move as it is made
mkdir -p outbox archive
n=$(ls outbox | wc -l | tr -d ' ')
if [ "$n" -gt 20 ]; then
  k=$((n - 10))
  printf '{"controller": "outbox-small", "decision": "%s in outbox: archive %s"}\n' "$n" "$k"
  ls -tr outbox | head -"$k" | while read -r f; do
    mv "outbox/$f" archive/ && printf '{"valve": "archive-oldest", "amount": 1}\n'
  done
else
  printf '{"controller": "outbox-small", "decision": "%s in outbox: leave it"}\n' "$n"
fi
