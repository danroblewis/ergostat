#!/bin/sh
# delete merged branches, keeping the newest one
cd work || exit 0
old=$(git for-each-ref --merged main --sort=committerdate --format='%(refname:short)' refs/heads | grep -v '^main$')
n=$(printf '%s\n' "$old" | grep -c . )
k=$((n - 1))
if [ "$k" -gt 0 ]; then
  printf '%s\n' "$old" | head -"$k" | xargs git branch -q -d
  printf '{"controller": "few-merged-branches", "decision": "%s merged: delete %s"}\n' "$n" "$k"
  printf '{"valve": "delete-merged", "amount": %s}\n' "$k"
else
  printf '{"controller": "few-merged-branches", "decision": "%s merged: keep"}\n' "$n"
fi
