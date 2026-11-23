# sessions-know-the-shell-rule: build and review sessions use the shell in the form it allows

In six hours, 283 sessions had 680 commands refused, mostly because they chained commands with `&&`, `;` or pipes under the allowlist. One session concluded the shell was broken and parked top-priority work three times.

Change. The implementor and reviewer prompts state that each Bash call is one allowed command, name what to use instead, and say a refusal is never a reason to stop. Add a measure of refused commands per session so a rise is visible. Do not widen the allowlist.

Definition of done.
1. A test proves both rendered briefs contain the rule and every command the implementor prompt tells a session to run is allowed for that role.
2. Refused commands per session is a measure on the model.
3. Do not measure or change the live instance in the session.

## Where it stopped

Built, round 1: every point of the definition, about 50 net lines (dev/bin/agents.py +22, dev/bin/measure.py +17,
dev/bin/brief.py +3, dev/model/measures.yaml +7, the two prompts), within the 600 budget.

- `agents.shell_rule(role)` writes the briefs' `# How the shell works here` from the role's own allowlist (`TOOLS`):
  each Bash call is one allowed command, beginning with one of the role's Bash commands (listed); `&&`, `;`, `|`,
  `cd`, `cat`, `head`, `timeout`, `python3`, `git -C`, a multi-line command or any other program are refused; use
  Read, Grep and Glob (and Edit and Write for the implementor) and one call per command; the rules' commands for the
  owner's own runs are not the session's; a refusal is never a reason to stop, park or report the environment broken.
  brief.assemble fills `{shell}` with it; implementor.md and reviewer.md place it. The allowlist is unchanged.
- reviewer.md told the reviewer to run `uv run python -m pytest -q tests/test_x.py`, which its allowlist refuses
  (read-only: git diff, log, show). It now says the reviewer runs no tests or programs. This is the narrowest fix that
  keeps every command the brief gives allowed without widening the allowlist; reverting it is one line.
- `measure.py refused-commands-per-session` (an auxiliary in dev/model/measures.yaml, no goal; the existing
  `no-tool-denials` goal already holds the total at 0): the mean of each session's `denied` entries that are Bash
  calls, over the sessions in the window whose `denied` is a list. The others (a timeout, a crash, a result silent on
  them) are left out and counted on stderr; with none that said, no value (exit 1), never 0 (lesson-3).

Acceptance tests, in `tests/test_shell_rule.py`, each passing:
- `test_both_briefs_state_the_shell_rule_and_tell_only_allowed_commands`: both briefs rendered by brief.assemble from
  the real templates (the implementor's with agents.LOOK, as agents.session adds it), the rule in each, and every
  backticked command in them allowed to that role, or named as refused or as never to run. Seen to fail with `{shell}`
  removed from implementor.md, and with reviewer.md's old pytest line put back (`may('uv run python -m pytest -q
  tests/test_x.py', 'reviewer')` false).
- `test_the_allowlist_is_not_widened`.
- `test_refused_commands_per_session_is_a_measure_on_the_model`: no value with only unknown sessions, 1.0 for two
  Bash refusals over two sessions that said (an Edit refusal not counted). Seen to fail counting every refusal (1.5).

Not covered, said so a review need not find it: the brief's knowledge block (dev/knowledge, the house rules) still
names commands for the owner's runs, such as the `ps -A ... | grep` wait. The test checks the templates, the rule and
the page paragraph, and stands the knowledge block in; the rule tells a session those commands are not its own. The
check of "allowed" is the prefix match of tests/test_agents.py's `permits`, which does not model how Claude Code
splits a chained command. Nothing was measured or changed on the live instance (item 3). No `## Entry` written: the
definition allows only this section to be added, and the gap is not in GAPS.md.

Run here: tests/test_shell_rule.py, tests/test_agents.py (28), and test_factory.py's
`test_the_factory_model_loads`, `test_refused_tool_calls_are_recorded_on_the_session` and
`test_the_implementor_may_remove_files_and_run_the_watched_suite`, each passing. Ruff is clean on ergostat, tests and
scripts and on the three changed dev/bin files. Local `main` has nothing the branch lacks. Not run: the whole unit
suite, the four browser files (no page changed), demo_check (no example touched).
