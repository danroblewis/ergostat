#!/bin/sh
# people drop zero to three files at a time
mkdir -p inbox
k=$(( $(od -An -N1 -tu1 /dev/urandom) % 4 ))
i=0
while [ $i -lt $k ]; do
  echo "a note dropped at $(date +%H:%M:%S)" > "inbox/note-$(date +%s)-$$-$i.txt"
  i=$((i + 1))
done
