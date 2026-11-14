#!/bin/sh
# rebuilds the status report; says how old the one it replaced was
mkdir -p var
if [ -f var/report.html ]; then age=$(( $(date +%s) - $(stat -c %Y var/report.html 2>/dev/null || stat -f %m var/report.html) )); else age=0; fi
date > var/report.html
echo "report rebuilt (the old one was ${age}s old)"
