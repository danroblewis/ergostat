## Entry

section: Runtime, scale and latency

- **Linux: two bugs the dev container found** (done; `linuxfix`, 2026-11-19). (1) The segmented event log
  (`ergostat/segments.py`, `_sync`) noticed new sealed segments by the directory's mtime alone, and Linux timestamps
  are coarse (one jiffy: 50 file creates on tmpfs gave one mtime), so a seal within the same tick was missed and its
  events vanished from queries. Now every seal, roll-up and prune replaces a `layout` token atomically under the lock,
  and a reader that sees it change lists the segments again and reads the head from its start (the head's inode is
  not trusted either: a file system reuses it). The mtime is still compared, for a writer that keeps no token.
  Tested with seals forced into one mtime with `os.utime`. (2) `shell=True` runs `/bin/sh`, which on Debian is dash,
  and dash forks for `sh -c CMD` where macOS's bash execs: the pid recorded for a daemon was the shell's. Now a
  daemon's command that is one simple command is run with `exec` (`daemons/proc.py`, `execd`); anything else keeps
  its shell, and either way the pid leads the daemon's session, so kills reach the program through its group.
