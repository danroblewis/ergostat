#!/bin/sh
# The remote pair, run on this machine: incidents (the remote) on 8796, support (the local model) on 8797.
#   sh examples/remote-pair/run.sh        start both (in a scratch copy), and say where they are
#   sh examples/remote-pair/run.sh stop   stop both
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${REMOTE_PAIR_DIR:-${TMPDIR:-/tmp}/ergostat-remote-pair}
ERGOSTAT=${ERGOSTAT:-ergostat}
if [ "$1" = stop ]; then
  $ERGOSTAT -C "$WORK/support" run --stop || true
  $ERGOSTAT -C "$WORK/incidents" run --stop || true
  exit 0
fi
for port in 8796 8797; do
  if lsof -nP -iTCP:$port -sTCP:LISTEN > /dev/null 2>&1; then echo "port $port is taken; stop what holds it first" >&2; exit 1; fi
done
mkdir -p "$WORK"
cp -R "$HERE/incidents" "$HERE/support" "$WORK/"
$ERGOSTAT -C "$WORK/incidents" run --port 8796
$ERGOSTAT -C "$WORK/incidents" remote token support > "$WORK/support/incidents.token"
$ERGOSTAT -C "$WORK/support" run --port 8797
echo "incidents (the remote): http://127.0.0.1:8796    support (reads it): http://127.0.0.1:8797"
echo "scratch copy: $WORK    stop both: sh $0 stop"
