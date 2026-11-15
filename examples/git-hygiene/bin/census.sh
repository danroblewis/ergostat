#!/bin/sh
# one reading: the number of open (unmerged) or merged branches in work/
bin/setup.sh
cd work && [ -d .git ] || exit 1          # never run git anywhere but work/
merged=$(git branch --merged main | grep -v -E '^\*|^  main$' | wc -l | tr -d ' ')
all=$(git branch | grep -v -E '^\*|^  main$' | wc -l | tr -d ' ')
case "$1" in
  open) echo $((all - merged)) ;;
  merged) echo "$merged" ;;
  *) echo "usage: census.sh open|merged" >&2; exit 2 ;;
esac
