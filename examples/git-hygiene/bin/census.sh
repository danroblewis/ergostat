#!/bin/sh
bin/setup.sh
cd work
merged=$(git branch --merged main | grep -v -E '^\*|^  main$' | wc -l | tr -d ' ')
all=$(git branch | grep -v -E '^\*|^  main$' | wc -l | tr -d ' ')
printf '{"sensor": "branch-count", "value": %s}\n' "$((all - merged))"
printf '{"sensor": "merged-count", "value": %s}\n' "$merged"
