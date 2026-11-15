#!/bin/sh
# make work/, a repository with a main branch, once (mkdir is the lock: two sensors may start together)
[ -d work/.git ] && exit 0
mkdir work 2>/dev/null || { sleep 1; exit 0; }
cd work && git init -q -b main && git config user.email dev@example.invalid && git config user.name dev
echo "# work" > README.md && git add README.md && git commit -qm "start"
