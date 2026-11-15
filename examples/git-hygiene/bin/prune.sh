#!/bin/sh
# delete merged branches, keeping the newest one; print how many were deleted
cd work && [ -d .git ] || exit 0          # never run git anywhere but work/
old=$(git for-each-ref --merged main --sort=committerdate --format='%(refname:short)' refs/heads | grep -v '^main$')
n=$(printf '%s\n' "$old" | grep -c . )
k=$((n - 1))
if [ "$k" -gt 0 ]; then
  printf '%s\n' "$old" | head -"$k" | xargs git branch -q -d    # -d: only branches already merged
  echo "$k"
else
  echo 0
fi
