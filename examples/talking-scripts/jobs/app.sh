#!/bin/sh
# stands in for the app: leaves uploads behind and writes its log. It moves two flows, so it says
# which with JSON lines (what the log grew by is measured the way the sensor measures it: du)
mkdir -p var/uploads var/log
for i in 1 2; do mktemp var/uploads/up.XXXXXX >/dev/null; done
before=$(du -k var/log/app.log 2>/dev/null | cut -f1)
head -c 2000 /dev/urandom | base64 >> var/log/app.log
after=$(du -k var/log/app.log | cut -f1)
printf '{"out": "flow.uploads-left", "moved": 2}\n'
printf '{"out": "flow.logging", "moved": %s}\n' "$((after - ${before:-0}))"
