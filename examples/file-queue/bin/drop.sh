#!/bin/sh
# people drop zero to three files at a time; say each (file.dropped) and how many
mkdir -p inbox
k=$(( $(od -An -N1 -tu1 /dev/urandom) % 4 ))
i=0
while [ $i -lt $k ]; do
  f="note-$(date +%s)-$$-$i.txt"
  echo "a note dropped at $(date +%H:%M:%S)" > "inbox/$f" \
    && printf '{"event": "file.dropped", "item": "file/%s", "data": {"file": "file:inbox/%s"}}\n' "$f" "$f"
  i=$((i + 1))
done
printf '{"moved": %s}\n' "$k"
