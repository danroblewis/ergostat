#!/bin/sh
# stands in for the app: leaves uploads behind and writes its log
mkdir -p var/uploads var/log
for i in 1 2; do mktemp var/uploads/up.XXXXXX >/dev/null; done
head -c 2000 /dev/urandom | base64 >> var/log/app.log
