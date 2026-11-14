#!/bin/sh
# deletes upload leftovers older than a minute; at most 25 a run, to go easy on the disk
mkdir -p var/uploads
files=$(find var/uploads -type f -mmin +1 | head -25)
n=$(printf '%s' "$files" | grep -c . || true)
[ -n "$files" ] && printf '%s\n' "$files" | xargs rm -f
echo "cleanup done: removed $n stale uploads"
