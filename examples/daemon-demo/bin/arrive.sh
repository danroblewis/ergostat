#!/bin/sh
# arrive.sh: a stand-in for the outside. Each run opens one job, which takes 1 to 4 seconds.
n=$(date +%s)
printf '{"event": "job.opened", "item": "job/%s", "data": {"seconds": %d}}\n' "$n" $((n % 4 + 1))
