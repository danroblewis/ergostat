#!/bin/sh
# read only: one measurement of this machine (disk, downloads or load); changes nothing
case "$1" in
  disk) df -P / | awk 'NR==2 { gsub("%", "", $5); print $5 }' ;;
  downloads) ls -1A "$HOME/Downloads" 2>/dev/null | wc -l | tr -d ' ' ;;
  load) load=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print $2}'); echo "${load:-0}" ;;
  *) echo "usage: meter.sh disk|downloads|load" >&2; exit 2 ;;
esac
