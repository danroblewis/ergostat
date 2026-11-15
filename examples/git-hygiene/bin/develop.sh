#!/bin/sh
# a developer: usually starts a branch with a commit, sometimes merges the oldest open one
bin/setup.sh
cd work && [ -d .git ] || exit 1          # never run git anywhere but work/
r=$(( $(od -An -N1 -tu1 /dev/urandom) % 3 ))
if [ "$r" -lt 2 ]; then
  b="feature-$(date +%s)-$$"
  git switch -q -c "$b" && echo "$b" > "$b.txt" && git add "$b.txt" && git commit -qm "$b" && git switch -q main \
    && printf '{"out": "flow.branched", "moved": 1}\n{"event": "branch.started", "item": "%s"}\n' "$b"
else
  b=$(git for-each-ref --no-merged main --sort=committerdate --format='%(refname:short)' refs/heads | head -1)
  [ -n "$b" ] && git merge -q --no-edit "$b" >/dev/null \
    && printf '{"out": "flow.merged", "moved": 1}\n{"event": "branch.merged", "item": "%s"}\n' "$b"
fi
exit 0
