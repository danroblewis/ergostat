# Security: running programs you have not vouched for

Ergostat sometimes has to run a program nobody has checked yet: a fix an AI agent just wrote, run to see whether it
works before you approve it, or a script that came with a library someone shared. For those it has a sandbox
(`ergostat/sandbox/`, SPEC §12q). This page says, plainly, what that sandbox stops and what it does not. It is not
used yet by repair or libraries; both are waiting on other work (`docs/GAPS.md`).

## What it stops

The sandbox works by **allowlist**: the program may touch only what is listed, and everything else is refused by the
operating system (macOS: `sandbox-exec`; Linux: `bwrap`). If neither is there, ergostat refuses to run the program at
all. It never falls back to running it unprotected.

- **Reading your secrets.** Your whole home folder is closed: SSH keys, `~/.netrc`, `~/.config`, cloud and API
  tokens, `~/.claude*`, shell history, browser profiles and cookies. So are other temporary files. On macOS the
  keychain cannot be asked either. The program can read only its own work copy, the language it runs in (Python and
  the system's libraries and tools), and folders the caller names.
- **Writing outside its folder.** It can write only in its work copy and a private temporary folder that is deleted
  afterwards. Not `/tmp`, not your home folder, not your other projects.
- **Changing git behind ergostat's back.** The program cannot write the work copy's git metadata at all, so it cannot
  plant a git setting (an `fsmonitor`, a filter, a hook, a signing program) that would run later outside the sandbox.
  Ergostat makes every commit itself, with git's dangerous settings switched off, and checks before each git command
  that the copy's git pointers are still the ones it made.
- **Sending your data out.** There is no network unless the caller lists hosts. Then the only way out is a proxy
  ergostat starts, which lets through only the listed host names, does the name lookups itself (the program can do
  none, so it cannot leak data through DNS), and logs every connection, allowed or not. It cannot reach other
  programs on your machine through local ports either.
- **Leaving something running.** Everything the program starts is killed when the run ends or times out, including
  processes that tried to detach (`nohup … &`, a new session, a double fork).
- **Knowing it is being tested.** The program gets a short list of ordinary environment variables and what the caller
  passes on purpose: no `ERGOSTAT_…`, dry-run or test markers, and a temporary folder with an ordinary name.

Each of these is tested by an attack (`tests/test_sandbox_attacks.py`), with fake secrets in a fake home folder.

## What it does not stop

- **Doing harm to a listed host.** If you list `api.example.com`, the program may send it anything that host accepts.
  Method limits (for example "GET only") are enforced for plain HTTP. For HTTPS the proxy cannot see inside the
  encryption, so a host limited to some methods gets no HTTPS connection at all, unless the caller says the limit may
  go unchecked there. List as few hosts as you can.
- **Damaging its own work copy.** It may change or delete anything in its copy (except `.git`). The copy should be a
  throwaway, which is how repair uses it.
- **Using what it can read.** It can read the toolchain and the folders named for it. Do not name a folder that holds
  secrets. Ergostat refuses to name `/` or the whole home folder.
- **Noticing the sandbox.** A program can still tell something is unusual: reading the home folder fails, there is no
  DNS, and its folder's path is whatever the caller chose. What it cannot find is a marker that says "test". A fix
  that behaves only when watched is still possible in principle; tests run against real inputs make that harder,
  not impossible.
- **Using all the CPU, memory or disk** while it runs. Only the time limit bounds it.
- **Other programs on your machine using the proxy.** While a run lasts, another local program of yours could connect
  to its port and reach the listed hosts. It cannot reach anything else through it.
- **Bugs in the operating system's sandbox**, or a process that escapes it through one. macOS's `sandbox-exec` is
  marked deprecated by Apple, though still shipped and used (Chrome and Claude Code use the same mechanism).
- **Linux**: built and its command line tested, but the attack suite has been run on macOS only so far.
- **Claude Code sessions** (AI blocks with `tools:` or `actions:`) use Claude Code's own sandbox, not this one: they can
  still read most of the machine (SPEC §12k, *Not enforced*).
- **What happens after you approve.** Once a fix is approved and merged, it runs as your code always does, with your
  permissions. The sandbox protects the time before anyone has looked.
