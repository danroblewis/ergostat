#!/bin/sh
# delete merged branches, keeping the newest one; say each (branch.deleted) and how many were deleted
cd work && [ -d .git ] || exit 0          # never run git anywhere but work/
old=$(git for-each-ref --merged main --sort=committerdate --format='%(refname:short)' refs/heads | grep -v '^main$')
n=$(printf '%s\n' "$old" | grep -c . )
k=$((n - 1))
if [ "$k" -gt 0 ]; then
  for b in $(printf '%s\n' "$old" | head -"$k"); do
    git branch -q -d "$b" \
      && printf '{"event": "branch.deleted", "item": "branch/%s"}\n' "$b"   # -d: only branches already merged
  done
  printf '{"moved": %s}\n' "$k"
else
  echo 0
fi
