#!/bin/sh
# process up to three files: uppercase each into outbox/, and say each move as it is made
mkdir -p inbox outbox
for f in $(ls inbox | head -3); do
  tr '[:lower:]' '[:upper:]' < "inbox/$f" > "outbox/$f" && rm "inbox/$f" \
    && printf '{"moved": 1}\n{"event": "file.processed", "item": "%s"}\n' "$f"
done
exit 0
