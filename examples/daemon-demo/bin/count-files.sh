#!/bin/sh
# count-files.sh DIR: a sensor's daemon. It answers each reading asked of it with how many files are in DIR,
# and starts no process to do it: the count is a shell glob, the line is taken apart by the shell itself.
dir=${1:?usage: count-files.sh DIR}
mkdir -p "$dir" || exit 1
while IFS= read -r line; do
  case $line in
    *'"op": "read"'*)
      req=${line##*'"request": "'}; req=${req%%'"'*}
      set -- "$dir"/*
      [ -e "$1" ] || shift $#            # an empty folder: the glob matched nothing
      printf '{"reading": %d, "request": "%s"}\n' $# "$req" ;;
    *'"op": "stop"'*) exit 0 ;;
  esac
done
