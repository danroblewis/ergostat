#!/bin/sh
# Run a command in the dev container (Dockerfile, compose.yaml) with hard limits: 4096 processes and threads,
# 12 GB of memory, half the CPUs, no network but the loopback device, a tmpfs /tmp. docs/DEVELOPMENT.md.
#   scripts/in_container.sh [--net] [--print] CMD ...
#     --net     give the container a network (the default is none: only localhost)
#     --print   print the docker command instead of running it
# Settings: ERGOSTAT_MEM (12g), ERGOSTAT_CPUS (half the host's, at most the Docker VM's), ERGOSTAT_PIDS (4096),
# ERGOSTAT_TMP (4g), ERGOSTAT_WORK (the repository or worktree to mount at /work; this script's own by default).
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
run=
while [ $# -gt 0 ]; do
  case "$1" in
    --net) export ERGOSTAT_NET=bridge; shift ;;
    --print) run=echo; shift ;;
    --) shift; break ;;
    *) break ;;
  esac
done
[ $# -gt 0 ] || { echo "usage: scripts/in_container.sh [--net] [--print] CMD ..." >&2; exit 2; }
work=$(cd "${ERGOSTAT_WORK:-$here}" && pwd)
export ERGOSTAT_WORK="$work" ERGOSTAT_UID="${ERGOSTAT_UID:-$(id -u)}"
if [ -z "${ERGOSTAT_CPUS:-}" ]; then
  host=$(getconf _NPROCESSORS_ONLN)
  vm=$(docker info --format '{{.NCPU}}' 2>/dev/null) || vm=$host; [ "$vm" -gt 0 ] 2>/dev/null || vm=$host
  cpus=$((host / 2)); [ "$cpus" -le "$vm" ] || cpus=$vm; [ "$cpus" -ge 1 ] || cpus=1
  export ERGOSTAT_CPUS="$cpus"
fi
# A worktree's .git points at its repository's git directory by absolute path: mount that at the same path
common=$(git -C "$work" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
case "$common" in ""|"$work"/*) set -- dev "$@" ;; *) set -- -v "$common:$common" dev "$@" ;; esac
tty=-T; [ -t 0 ] && [ -t 1 ] && tty=
[ -z "$run" ] || env | grep '^ERGOSTAT_' | sort
exec $run docker compose -f "$here/compose.yaml" run --rm --build --quiet-build $tty "$@"
