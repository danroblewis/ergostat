#!/bin/sh
# make work/, a repository with a main branch, once
[ -d work/.git ] && exit 0
mkdir -p work && cd work && git init -q -b main && git config user.email dev@example.invalid && git config user.name dev
echo "# work" > README.md && git add README.md && git commit -qm "start"
