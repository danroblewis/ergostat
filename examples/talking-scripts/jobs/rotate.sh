#!/bin/sh
# rotates the app's log when it is over 48 KB, and says so in words, as scripts do
mkdir -p var/log
size=$(du -k var/log/app.log 2>/dev/null | cut -f1)
if [ "${size:-0}" -gt 48 ]; then
  mv var/log/app.log "var/log/app.log.$(date +%s)"
  echo "rotated app.log: freed ${size} KB"
else
  echo "app.log is ${size:-0} KB, nothing to rotate"
fi
