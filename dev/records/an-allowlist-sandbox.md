## Entry

section: Running code ergostat does not trust

- **An allowlist sandbox** (done on `sandbox`, SPEC §12q, `docs/SECURITY.md`): `ergostat/sandbox/`, reads only the
  copy, the toolchain and declared paths; writes only the copy (not `.git`) and a private temporary folder; network
  only through a filtering proxy (listed hosts, SNI checked, methods for plain HTTP, every connection logged), no DNS;
  every process killed at the end; no markers in the environment; git run by ergostat with its dangerous settings off
  and the copy's pointers verified. The attack suite (`tests/test_sandbox_attacks.py`) blocks every finding of the
  repair and libraries reviews, and the branch's own review (pid hopping, a ClientHello split across records, wide
  toolchain reads, the process table). *Left*: on macOS another process's argv and environment stay readable
  (`kern.procargs2` is not mediated by the sandbox for the same user; closing it needs a uid per run, an
  administrator's setup), recorded as a strict expected failure; the suite runs on macOS and, in the dev container,
  on Linux; no CPU, memory or disk limit beyond the time limit and `RLIMIT_NPROC`; repair uses it (`repair2`),
  libraries does not yet.
