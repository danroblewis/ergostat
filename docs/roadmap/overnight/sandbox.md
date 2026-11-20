# sandbox: one allowlist sandbox for programs ergostat does not trust

Branch `sandbox`, from main at 4a4eda3. Two features are parked for sandbox weaknesses: `repair` (X1, git runs the
fixer's config unsandboxed; X2, the jail is a deny list with open network; M2, a fix can tell it is under test; M3,
processes outlive the jail) and `libraries` (a library's scripts run with the owner's reads and network once the trust
gate is laundered). Today's sandboxes are two deny lists: `actions/sandbox.py` (Claude Code's own) and repair's
`jail.py`. This branch builds the shared module both can adopt later, standalone, on main first. It changes neither
caller.

## Done when

`ergostat/sandbox/` runs a command (`run(argv, Policy)`) under the OS's sandbox with an **allowlist**, and never
without one: macOS `sandbox-exec` with `(deny default)` and explicit allows (no `allow default`; no Mach service, only
POSIX semaphores, which Python's `multiprocessing` needs), Linux `bwrap` with an empty root that binds only what is
allowed; neither, and it refuses (`Unavailable`). **Reads**: the work copy, the toolchain resolved explicitly (Python's
prefix, base prefix and venv; `/usr/lib`, `/System` on macOS, `/bin`, `/usr/bin`), and declared extra read paths;
nothing else, the whole home folder included. **Writes**: the work copy (never its `.git`) and a private temporary
folder. **Network**: none by default; with hosts listed, only through a filtering HTTP(S) CONNECT proxy ergostat
starts on 127.0.0.1 (a free system port), which admits only the listed host names (the CONNECT host, and the TLS SNI
must agree), resolves them itself (no DNS inside), logs each connection, and enforces per-host method limits for plain
HTTP (for HTTPS only whether the tunnel opens: a method-limited host is refused a tunnel unless the policy says the
limit may go unchecked inside TLS). **Lifetime**: everything started inside is killed when the run ends (macOS: its
process group, and every process of the user that carries this run's sandbox, found by `sandbox_check`; Linux:
`--die-with-parent`, a pid namespace and a new session). **Environment**: an allowlist plus what the caller passes; no
ergostat, test or dry-run marker and an ordinary `TMPDIR` name. **Git**: `ergostat.sandbox.git.Repo` runs git on a
work copy with `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, explicit `GIT_DIR`, `GIT_COMMON_DIR` and
`GIT_WORK_TREE`, `-c core.fsmonitor=false -c core.hooksPath=/dev/null -c commit.gpgsign=false`, `--no-ext-diff` and
`--no-textconv` where they apply, every filter driver blanked, after verifying that the `.git` pointer, `commondir` and
the worktree's back-pointer are what ergostat made. SPEC has a section on the sandbox, `docs/SECURITY.md` says for
people what it protects against and what it does not, and GAPS says repair and libraries are unblocked on the sandbox
side and what each still needs.

## Acceptance tests (`tests/test_sandbox_attacks.py`, the attack suite)

Each reproduces a finding from the repair and libraries reviews (the coordinator's `rp/`, `lib1/`, `lib2/`), with a
fake secret planted in a temporary HOME (never a real one), and each must be blocked:

- `test_a_program_runs_reading_its_copy_its_toolchain_and_declared_reads` (the control: the sandbox is usable)
- `test_secrets_in_home_are_unreadable` (t1: `~/jira_token`, `~/.claude.json`, `~/.ssh`, `~/.netrc`, `~/.config`,
  shell history, a browser profile)
- `test_writes_outside_the_copy_and_its_temporary_folder_are_denied` (`/tmp`, HOME, a read path; lib1's
  `echo PWNED1 > /tmp/pwned1`)
- `test_dns_is_denied_inside`
- `test_direct_network_is_denied_even_to_localhost` (a listener outside receives nothing)
- `test_the_proxy_admits_only_listed_hosts_and_logs_each` (an unlisted host and port refused, the listed one served)
- `test_the_proxy_refuses_a_tls_name_that_differs_from_the_connect_host`
- `test_the_proxy_enforces_methods_for_http_and_refuses_an_unchecked_tunnel`
- `test_library_exfiltration_commands_are_contained` (lib1's prompt and lib2's `curl ... | sh`)
- `test_a_background_process_does_not_outlive_the_run` (t5: `nohup sleep &`)
- `test_a_new_session_does_not_outlive_the_run` (`setsid`, a double fork)
- `test_a_timed_out_run_leaves_nothing_behind`
- `test_runs_cannot_tell_they_are_under_test` (t5: no `ERGOSTAT_*`, `DRY_RUN`, pytest or sandbox marker; an ordinary
  `TMPDIR`)
- `test_the_program_cannot_write_git_metadata` (rewrite or move `.git`, write `commondir`)
- `test_git_refuses_a_replaced_git_pointer` (rp `g`: `ws/.git` to a folder with `core.fsmonitor`)
- `test_git_refuses_a_moved_commondir` (rp `g2`)
- `test_git_runs_no_fsmonitor_hook_filter_or_external_diff` (planted in the repository's own config and hooks)
- `test_no_sandbox_means_refusal`
- `test_the_linux_command_binds_only_the_allowlist` (bwrap's argv: empty root, no home, `--unshare-all`,
  `--die-with-parent`, `.git` read-only)

## Suites

`scripts/suite_watch.py` with the unit suite (`-n 8 --dist worksteal`) and then the four Playwright files (`-n 4`),
one at a time, rc 0, no skips; `uv run ruff check ergostat tests scripts`.

## Size budget

**700 net lines outside `tests/` and `docs/`** (the owner's figure for this branch).
