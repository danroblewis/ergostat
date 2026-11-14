#!/bin/sh
# Start, stop or list every example in examples/ (or the ones named).
#   scripts/demos.sh start [demo ...]     each in the background, with its web page
#   scripts/demos.sh stop [demo ...]
#   scripts/demos.sh list                 every project ergostat knows, and its page
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
ergostat="$here/.venv/bin/ergostat"
[ -x "$ergostat" ] || ergostat=ergostat
demos="${DEMOS:-$here/examples}"
cmd="${1:-list}"; [ $# -gt 0 ] && shift
names="$*"
[ -n "$names" ] || names=$(for d in "$demos"/*/ergostat.toml; do basename "$(dirname "$d")"; done)
case "$cmd" in
  start) for n in $names; do printf '%-12s ' "$n"; "$ergostat" -C "$demos/$n" run | sed -n 's/^web: //p; s/^already running.*· //p'; done ;;
  stop)  for n in $names; do printf '%-12s ' "$n"; "$ergostat" -C "$demos/$n" run --stop; done ;;
  list)  "$ergostat" projects ;;
  *) echo "usage: scripts/demos.sh start|stop|list [demo ...]" >&2; exit 2 ;;
esac
