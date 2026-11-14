#!/bin/sh
# read only: three measurements of this machine
used=$(df -P / | awk 'NR==2 { gsub("%", "", $5); print $5 }')
dl=$(ls -1A "$HOME/Downloads" 2>/dev/null | wc -l | tr -d ' ')
load=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print $2}')
printf '{"sensor": "df", "value": %s}\n' "$used"
printf '{"sensor": "downloads-count", "value": %s}\n' "$dl"
printf '{"sensor": "uptime", "value": %s}\n' "${load:-0}"
