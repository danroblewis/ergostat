#!/bin/sh
mkdir -p outbox
printf '{"sensor": "outbox-count", "value": %s}\n' "$(ls outbox | wc -l | tr -d ' ')"
