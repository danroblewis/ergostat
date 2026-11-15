#!/bin/sh
# move the five oldest files in outbox/ to archive/; print how many were moved
mkdir -p outbox archive
n=0
for f in $(ls -tr outbox | head -5); do
  mv "outbox/$f" archive/ && n=$((n + 1))
done
echo "$n"
