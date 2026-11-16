#!/bin/sh
# move the five oldest files in outbox/ to archive/; say each (file.archived) and how many were moved
mkdir -p outbox archive
n=0
for f in $(ls -tr outbox | head -5); do
  mv "outbox/$f" archive/ && n=$((n + 1)) && printf '{"event": "file.archived", "item": "file/%s", "data": {"file": "file:archive/%s"}}\n' "$f" "$f"
done
printf '{"moved": %s}\n' "$n"
