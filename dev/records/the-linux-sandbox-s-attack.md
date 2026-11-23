## Entry

section: Running code ergostat does not trust

- **The Linux sandbox's attack suite asserted macOS behaviour in five places** (done; `linuxfix`, 2026-11-19). Each
  has a Linux form beside the macOS one, which is unchanged: DNS fails and nothing reaches a listener outside on both,
  and on Linux a send to 127.0.0.1 is allowed only because the run has a network namespace of its own (checked, with
  no route out); the process list and environment are read from the run's /proc, which shows only its own pid
  namespace (the environment test is a strict xfail on macOS only); listing the toolchain's parents shows only the
  folders bwrap made to mount what is allowed; the pid hopper's parent on Linux is bwrap's init, which a signal from
  inside never ends, so the run reports the program's own exit. 31 of 31 pass in the dev container (they run only
  under `scripts/in_container.sh --sandbox`).
