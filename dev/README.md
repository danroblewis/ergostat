# The factory: ergostat developing itself

`ergostat.yaml` at the repository's root is the factory that develops ergostat: gaps (from `docs/GAPS.md`, or asked
for) defined first, built by an AI implementor in their own worktrees, judged by a disagreeable AI reviewer, landed by a
merge queue behind the four suites (one batch of approved gaps a run, 1 gap to start), and the new main installed and switched to, with a revert. Its
programs, prompts and model files are here, in `dev/`. The plan it automates is
`docs/roadmap/overnight-2026-11-19.md`; what it is meant to do is `docs/roadmap/overnight/factory.md`.

It ships **off**: the implementor takes nothing until you open the intake.

## Where things are

| | |
|---|---|
| `~/ergostat` | the checkout the queue merges into, runs the suites in, and pushes from. Never the instance's code |
| `~/ergostat-live/drop.git` | the factory's own bare repository: each gap's work, on `factory/<branch>`, as the sessions bundled it back; the queue fetches the reviewed commit from it. Its main is fetched under `drop.git.lock` beside it, one session at a time |
| `~/ergostat-live/sessions/` | each session's clone (made from the drop, never the owner's repository) |
| `~/ergostat-live/<sha>` | each installed version: a detached worktree with its own `.venv` |
| `~/ergostat-live/current`, `previous` | the version running, and the one a revert goes back to |
| `~/ergostat-live/instance/` | the instance's folder, the same across versions (its record is keyed by it): copies of the version's `ergostat.yaml` and `dev/`, made at each switch (an edit made in them since, such as a model change you accepted, is kept as a patch in `run/model-edits/`: bring it to the repository as a gap), `run/` (briefs, logs, the cost ledger, definitions you write), `factory.local.toml`, and `ergostat.local.yaml`: the instance's own `web:` (its tunnel's public name) and `intake:` bind, never in the repository, kept across switches and never made a gap (SPEC §2) |
| `dev/factory.toml` | the settings (paths, models, per-session limits, the suites' commands); `factory.local.toml` in the instance's folder overrides any of them |
| `dev/model/budget.yaml` | **the daily dollar cap** (the goal `ai-budget`, $40 a day): change it there and nowhere else |

## Sessions in containers

Each implementor and reviewer session runs in a Docker container of its own (`dev/bin/agents.py`): on its own clone
(read-only for the reviewer), its result bundled back into `drop.git`; on an internal network whose only way out is
the egress proxy (`dev/agent/egress.py`, container `ergostat-egress`), which reaches `api.anthropic.com` alone; with
one secret, the session token, and nothing else of this machine. Claude Code inside still runs `--restricted` with the
role's narrow tools.

**The researcher reads the web.** A researcher session alone runs on a second internal network, `ergostat-research`,
whose only way out is a proxy of its own, `ergostat-egress-research` (the same `dev/agent/egress.py`, started like the
first and under the same lock), with `HTTPS_PROXY` pointing there. It allows `[agents] hosts` (the API) plus
`[agents] research_hosts`: by default `["*"]`, any host on 443 whose TLS server name matches its CONNECT (as for the
first proxy), and whose resolved addresses are all public (`ipaddress.is_global`): a name that resolves to a loopback,
private, link-local or other non-global address (127.0.0.1, 10.x, 172.16/12, 192.168/16, 169.254/16, ::1), or to
nothing, is refused, the reason in the proxy's log (`docker logs ergostat-egress-research`), and the tunnel goes to
the address checked. A list of names allows those alone (and the API); `[]` the API alone. A proxy running with other
hosts than the settings' is started again with them. The researcher's tools are the reviewer's plus WebSearch,
WebFetch and the walker (`uv run --with playwright==1.63.0 python scripts/walk.py`), with a `run/shots/<session>/`
folder at `/shots` as for the designer; WebFetch stays denied to every other role, and every other role stays on
`ergostat-agents` with the same hosts. Its prompt says that a URL it cites must be one it opened, and to prefer
primary sources.

**A session may see a page.** The implementor and the designer (a read-only role, like the reviewer: the reviewer's
tools and nothing that writes) may also run `uv run python scripts/demo_up.py` (start one demo of `examples/`, offline,
and stop it) and `uv run --with playwright==1.63.0 python scripts/walk.py` (walk its pages in Chromium). No other
role may, but the researcher may walk a page of the web (above). Each implementor or designer session gets a folder of its own on this machine, `run/shots/<session>/`
(named as its transcript, `<gap>-<role>-<n>`), mounted read-write at `/shots`, and its brief tells it to pass
`--shots /shots`: its pictures land there and outlive the container (its `/tmp` does not). A designer runs on
`[agents] designer_cpus` CPUs (default 3, above 0 and at most 4, else the session is refused with the reason), and so
does an implementor whose brief names `ergostat/web/` (an engine and Chromium at once); every other session keeps
`session_cpus`. `NO_PROXY` is `127.0.0.1,localhost`, so the demo's own web is reached without the egress proxy.

**Each session's conversation is kept.** Claude Code's own session file (from a folder of its own mounted as its
projects folder, `/home/dev/.claude/projects`, and nothing else of this machine's home) is copied as it grows, the
session token scrubbed, into `run/sessions/<gap>-<role>-<n>.jsonl` (at most 20 MB; a last line says when the rest was
cut), and recorded as the item `session/<gap>-<role>-<n>` (`dev/bin/sessions.py`): its role, round, model, cost, turns,
tools and time, related to its gap (the gap's page lists its sessions), its page showing the conversation while it
runs. In a terminal: `python3 dev/bin/status.py session GAP [ROLE] [N]`.

**What it needs from the owner:** the token file `~/.config/ergostat/claude-token` (one line, mode 600, from
`claude setup-token` in your own terminal). Without it, or with any other mode, sessions refuse to start. Then, once:

```sh
scripts/in_container.sh true                                  # the dev image, if not built
docker build -t ergostat-agent:latest dev/agent               # the agent image: the dev image and Claude Code
```

## Start it (the first time)

From a checkout of main (`cd ~/ergostat`):

```sh
python3 dev/bin/live.py install main          # ~/ergostat-live/<sha>: a worktree, uv sync, the model checked
python3 dev/bin/live.py init main              # ~/ergostat-live/instance, running that version
cd ~/ergostat-live/instance
cat > factory.local.toml <<'EOF'
[paths]
queue_lock = "/path/to/the/coordinator's/queue.lock"   # the same lock as queue-fast.sh, while both are in use
[suites]
slot = "/path/to/suite-slot.sh"      # the machine-wide suite slots every agent's suites share
EOF
cat > ergostat.local.yaml <<'EOF'      # only with a tunnel: its public name, this machine's alone (SPEC §2, §4d)
web: {names: [your-tunnel.example.org], open: read}
EOF
uv run --project ~/ergostat ergostat -C ~/ergostat-dev run --stop      # the old observe-only instance, on 8798
python3 dev/bin/live.py start                  # the engine of current, on port 8798
open http://127.0.0.1:8798
```

`live.py start` and `stop` start and stop it; `live.py health` says whether it is healthy; `live.py status` which
version runs. Every command here runs in the instance's folder; `ergostat` below is
`~/ergostat-live/current/.venv/bin/ergostat` there.

## Turn on intake

```sh
ergostat sensor intake-open.main --read 1      # the implementor may take ready gaps (0 pauses it again)
```

The reviewer, the queue and triage work on what is already in the pipe whatever the intake says. Each AI session is
held to the daily cap (fails closed: a spend not read stops them), each costs at most its `*_session_usd`, and the
merge queue and triage hold while the machine's suite slots are all taken; the implementor's and triage's suites each
hold a slot (`[suites] slot`), the queue's lock being its own (the load interlock). Triage never takes the queue's lock:
it reruns the failed tests in its own worktree, on the main the run failed on (`pre`), so neither its rerun nor its
wait for a quiet machine holds the queue.

**The kept slot.** While approved gaps wait and no queue run holds its slot (run/queue.json's `running`, with the
queue's lock held), a suite run in `[suites] slot` (the implementor's, triage's, the manager's reapprove, a measure run)
does not take the last of the `[suites] slots` (6, at most 32): it waits before the slot command until a slot is free
beyond that one, nothing is approved, or a queue run holds its slot (`dev/bin/slots.py`). A record that cannot be read
counts as approved gaps waiting. The suites taken are the ones ps sees (`fac.suites_running`, anyone's) and the
factory's own suites that passed in the last minute (a file each in `run/slots/`), looked at and written under
`run/slots.lock`, so two sessions looking at once never both take it. Implementor suites alone are then at most
`slots - 1`, inside machine-quiet's hold (`suites-running <= 6`), so they never hold queue-when off by themselves;
threads, memory and push-waiting still do. The queue's own waits (in its run, and in `main_red()`'s check of a main held
red, before `running` is written) are for that kept slot: fewer than `slots` suites running, not `[load] most_suites`.
The slot command stays the cap on the slots themselves; the kept slot is only kept by the factory's own suites, not by anyone else's on the machine.

**A usage-limit stop is a pause, not a failure** (`dev/bin/aihold.py`). A session whose result is the provider's
usage-limit message ("You've hit your weekly limit · resets Nov 25, 3pm (UTC)"; or a failed session whose output holds
it) records one factory-wide AI hold till the reset it names, in `run/ai_hold.json` (under its lock; a later hold is
never shortened by an earlier one). Its run ends at once, its lease given back uncounted and put off till the reset: no
attempt, nothing toward the kill rule, never parked or a dead letter. While the hold stands the goal `ai-not-held`
(the sensor `aihold.py held`, in its own system `ai-hold`; a stale reading counts as held) shuts implement-, review-
and research-when, and plan-when through `ai-stopped` (planning's one read of it and the budget), so no
AI-role lease is taken, and every AI program that took one in the sensor's lag gives it back the same way
(`fac.ai_holds`); the groomer starts no session (`fac.ai_held`). The merge queue, triage and the
suites read neither and run on. At the reset the hold lifts by itself and the items given back are taken again in their
blocks' order. A reset time that cannot be read (no time, an unknown zone, a date that does not exist, more than 8 days
off), or a hold file that cannot be read, holds for an hour and says so; the next session after it finds the limit
again or not.

**An outage is a pause, not a failure** (`dev/bin/outage.py`). A run that fails because Docker or the AI service cannot
be reached gives its item back uncounted, put off 10 minutes, and is taken again after it, as often as the outage
lasts: no attempt, nothing toward the kill rule, never parked or a dead letter. Docker's is told by its words naming
Docker (a container that did not start, exit 125, `docker ...`), confirmed by `docker info` failing or not answering in
30 s (a factory with no `docker` installed has no Docker outage); a queue suite whose container fails while `docker info`
fails is one too, never a red suite. The AI service's is told by a connection error in what the session said (refused,
no route, a name not resolved, a request timed out); an answer of the API's (a 4xx, a 5xx) is the service reached.
This covers the implementor and the reviewer (`fac.guarded`) and the merge queue's batch (main undone, no gap blamed).
The engine gives back a lease whose run's process is gone, uncounted too (SPEC §9.5, *A run gone*), and a kind's
`attention:` field puts the pipeline manager's latest finding (`finding`, on its handled situation) on the page's
attention list.

## Submit a gap

A GAPS.md entry is taken in by itself (`gap.found`, open). It is **ready** once it has a definition of done:

```sh
mkdir -p run/defs && $EDITOR run/defs/<branch>.md        # the gap's `branch` field (ergostat item gap/NAME)
```

(or `dev/records/<branch>.md` on main or on its branch: the gaps' working records, out of `docs/`; the old
`docs/roadmap/overnight/<branch>.md` is still read for a branch begun before the move, the new path first; a
`dev/records/<branch>.md` holding only its `## Entry` is not a definition, and the old file is read). A gap's GAPS.md
entry is written in its record, as its `## Entry` section (dev/prompts/definition.md shows the shape), never in
`docs/GAPS.md`: each landing of the merge queue carries the batch's own GAPS.md edits into the records
(`gapsdoc.carry`: a new entry gets a record of its own, `dev/records/<branch>.md` holding only its Entry, and text
outside the entries goes to `dev/records/GAPS-head.md`; one it cannot place, such as an entry whose branch names
another title's record, goes to `dev/records/GAPS-unplaced.md` and is said as `gaps_md_unplaced`), then
writes GAPS.md from the records and commits it as `docs/GAPS.md from the records` (a render that fails says
`gaps_md: why` on the run and lands the batch without it), and the implementor refuses, uncounted, a branch whose own
commits change GAPS.md. The dependency reader, the briefs (an implementor's, a reviewer's, a planner's, the join
judge's), the S definition and the knowledge block's related gaps read a gap's entry and its section from main's
records (`gapsdoc.entries`, through `brief.records_at_main`; GAPS.md only before the split); a record that cannot be
read is said in the brief by name where the entry would be, never as no entry. Intake still reads GAPS.md. A gap that is not in GAPS.md is asked for as an
event, its definition a file in `run/defs/` (a branch is lowercase words and dashes; nothing else is taken):

```sh
ergostat event --add gap.requested --item gap/my-change \
  --data '{"title": "My change", "source": "request", "branch": "my-change", "definition": "run/defs/my-change.md"}'
```

**Continuing a parked branch.** Ask for a new gap that `continues` it (`NAME` or `factory/NAME`, a branch of the
checkout or already in the drop; it is then the gap's branch, and its own `dev/records/NAME.md` (or old `docs/roadmap/overnight/NAME.md`) is the
definition, so add a "Where it stopped" section there rather than writing a new one):

```sh
ergostat event --add gap.requested --item gap/warm2-again \
  --data '{"title": "Warm 2, continued", "source": "request", "continues": "warm2"}'
```

A branch carried on under a new name (its first commit is another name's definition, e.g. `warm.md` on `warm2`) names
that file as its definition, `"definition": "factory/warm2:docs/roadmap/overnight/warm.md"` (or `dev/records/`): the implementor commits no
copy, the parked note is appended to it, and the reviewer's gate 1 checks that file is on the branch and unchanged since its first commit.

The intake fetches it into the drop as `factory/NAME` (never over a `factory/NAME` already there, and refusing a name
that is not lowercase words and dashes). It is not taken while another gap on the same branch is anywhere but parked or
merged (open, building, built, approved, in the queue...): that gap's reviewed work would be mixed with the new one's;
the intake says so on stderr and takes it once the other stops (of two requests to continue it asked at once, the first
read is taken, the other waits). Each run fetches its session's work to a side ref of its own
(`refs/incoming/<run>/factory/NAME`). Before each implementor run on a branch behind main, implement.py merges main in
itself: a clean merge is committed by the factory; a conflicted one is handed to the session with the files in its brief
(it may run `git merge`, `git add`, `git commit`, `git status`, and also `git rm`, `git mv`, `git restore`, `rm` and
`scripts/named_tests.py`, below; its refused calls are kept as `tool_denials`, and a session with no result or
a result silent on them as `tool_denials_unknown`, which the measure `tool-denials` leaves out and
`tool-denials-unknown` counts; `refused-commands-per-session` is the mean Bash calls refused per session that said,
so a rise shows. The implementor's and the reviewer's briefs end their working rules with `# How the shell works
here` (agents.shell_rule, from the role's own allowlist): one allowed command per Bash call, nothing chained, the
role's commands named, and a refusal never a reason to stop), and a branch that comes back without main in it (say, the merge aborted), or with the
merge unfinished, is refused before the drop's `factory/NAME` moves. The fast suites run
after: `[suites] build` (and ruff only when `[suites] ruff` is set; it is not), each under the watchdog in a suite
container of the agent image and the suite slot. Lint is no gate (owner, 2026-11-23): with `[suites] precommit` set,
the clone gets a pre-commit hook (`agents.precommit`, written after this program's own commits) that runs it on the
staged Python files (`ruff format`, `ruff check --fix --exit-zero`) and stages them again, whole; it never refuses a
commit. A merge commit (a conflicted merge of main the session finishes) is skipped: its staged files are main's,
not the session's. What the session leaves uncommitted is committed by `finish` with hooks off, so that commit is not formatted.
The four browser files run there too only with `[suites] build_browser = true` (default false: minutes of 4 CPUs a
round, plus a Chromium launch); then a browser test skipped fails them, as in the queue. `build` is the small set
(`scripts/affected_tests.py`: the test files the branch changed since main and `tests/test_<module>.py` of each
`ergostat/**/<module>.py` it changed; only collection when there are none; the full suite when the diff cannot be
read). With `build` commented out or empty, the full `unit` suite runs there instead. The merge queue never reads
`build`: it runs `unit`, `browser` and `demo` in full. **No browser stops the round** (with `build_browser` only):
before the session, `[suites] browser_ready` launches Playwright's Chromium once in that container; if it cannot (or the setting is
missing), the gap is given back uncounted with the reason (rebuild the dev image, then the agent image), and no session
starts. The session itself runs tests only through `scripts/named_tests.py`: 1 to 3 named `tests/test_*.py` files
or test ids, no options, pytest run serially (no xdist, the ini's addopts cleared); a browser file the same way under
`scripts/suite_watch.py` with `uv run --with playwright==1.63.0`. Never a whole suite: those run in the merge queue.
Each session's container has `[agents] session_cpus` CPUs (1.5; empty: the suites' 4), its suites' containers 4.
The script holds against habit, not against a session that edits it (it has Edit on its clone): such an edit shows in
the branch's diff, for the review.
The unit suite's tests/test_agents.py::test_implementor_environment_has_a_browser really launches Chromium that way, so
every unit run (the queue's on the host, a developer's, an implementor's offline container) needs Playwright 1.63.0
cached for `uv run --with` and its Chromium installed, or it fails: on purpose, a missing browser is a failure, not a
skip.

The reviewer's gate 1 takes the definition as first committed on the branch's own line (its first-parent line;
that commit need not be the branch's first; the file the gap's `definition` names, for a continued gap), and for a continued branch also requires it to hold the main
implement.py merged at its build (`built_main` on `gap.built`; current main when that is missing). Main moving on
between build and review is not a failed gate: the merge queue merges the branch into the main of its moment and runs
the suites again. Its reviews are numbered past the branch's earlier ones (`review/NAME-3` after a parked gap's `-1` and
`-2`), and run logs are named by when they ran.

**Dependencies.** A gap waits on others named by `depends-on: [name, ...]` in its definition (the template is
`dev/prompts/definition.md`), `"depends_on": ["gap/..."]` in its request, or `after `name``, `needs `name` first` and a
"Depends on" table column in GAPS.md, as main's records render it. It is built only once each is merged (a parked one
holds it, with `blocked_reason`; so does its own record when main's cannot be read, said by name); the implementor
takes the unblocked first,
the critical first. A name that is no gap, or a link that would close a cycle, is refused and said (the goal
`dependencies-sound`); a gap waiting on any unfinished one names it and its state (`blocked_reason`), and one whose
branch is already merged into main and whose own definition file is in main's tree (so a branch made from main with no
commits of its own is not) as 'landed, not closed': that wait is not explained away, so after its stuck
threshold the pipeline manager is raised with the reason, for the coordinator to close the dependency. The Items page's Graph and Timeline
draw the tree; `python3 dev/bin/deps.py` prints it as mermaid.

Then: the implementor commits the definition first and builds; the reviewer approves, sends it back (`fix`, with its
findings) or parks it; the sixth failed gate (`[gates] kill_after`) parks it with where it stopped; the queue lands it. `ergostat item
gap/NAME` shows each round, its reviews, the context each session was given and what it cost.

**The kill rule** is in `[gates]` (dev/factory.toml): `kill_after = 6` failed gates (fix verdicts, queue conflicts, real
failures in the queue), `build_failures = 6` failed fast-suite runs of the implementor's, or `build_hours = 12` of
building over its rounds, park a gap. The three count over the gap's whole life (each a `sum` in the gap kind's fold:
each failed build adds one to `build_failures`): a later successful build or a review round resets none of them, and a
gap continued from a park (`manage.py continue`, `parks.py resume`) is a new item, under an id not yet in the record,
that starts from zero. Within a run the implementor gets `[ai] suite_fix_rounds = 2` sessions to make its failing fast
suites pass.

**Scratch files are refused by a program, not a review.** After each session, before the fast suites, implement.py
lists the files the branch adds against main and refuses any with a path part matching `[gates] scratch_patterns`
(`.scratch*`, `scratch*`, `tmp*`, `_probe*`, `*_probe*.py`, `*.orig`, `*.rej`), or under a new top-level file or folder
the definition's "Files to touch" does not name (checked only when the definition has that section). A file already on
main is never refused. The list goes back to the session's next round (one of its `suite_fix_rounds`, not a review
round); still there after the last, the run counts as a failed build.

**A gap may not add findings to the model.** Next, still before the fast suites, implement.py runs `[suites] check`
(`ergostat check --json --no-coherence`) on the branch and on a clone of the main it merged, and compares their
findings by code and part (`code part`, or the code alone for a finding about no part). Every level counts, notes
too, but codes matching `fac.RECORD_FINDINGS` (`calibration-*`, `fit-*`, `takes-order-unset`), which depend on the
record rather than the change. Check waits only 5 s for its extreme-conditions tests, each side from cold, so how many
finish depends on load: when either side says some did not finish (an `extremes-running` or `extremes-skipped`
note), no `extreme-conditions` finding is compared on either side. A new one is then missed until a run where both
sides finish. A finding new on the branch goes back to the
session's next round with the list, as scratch files do. A side whose check printed no readable JSON is a failure to
compare, sent back the same way, never "no new findings". A definition may allow a named finding with a reason, one
line near its top: `allows-findings: [code part: why, ...]` (`code: why` for one about no part; no comma inside a reason; one with no reason allows
nothing). The allowances used are recorded on `gap.built` as `allowed_findings`, and the reviewer's brief lists each
allowance of the definition among the gates, to judge its reason.

**A failure on main is not the gap's.** When the implementor's fast suites fail and name tests, `dev/bin/onmain.py`
runs those tests again alone on the branch (the `[suites] alone` command, `rerun` for browser tests, in the same kind of suite container, in the
suite slot). Passing alone, they are flakes (`flake.seen`) and the fast suites run once more, uncounted. Still failing,
they run once on clean main (the commit the branch merged, `built_main`). A test that fails there too becomes
`flake/<test>` in the state `main-broken` and the intervention `intervention/main-broken-<sha12>` (class `main-broken`,
with the tests and the gaps it holds), which `interventions-trend` counts; fix it on main in a gap of its own (review
lesson 13). If every failing test fails on main, the failure is not counted and no fix session is spent on it: the gap
is given back with `waits_on_main`, the implementor skips it, and the intake releases it once main is another commit.
At most one alone run and one main run per failure, and none once the gap's building hours are nearly spent (then the
failure counts as before). A dead letter whose last failing tests were all main-broken is parked saying so.
Only a test main has can be main's: before that run each test is looked for at main (`onmain.present`: its file, and
each `class` and its `def` in it; a file or ref that cannot be read is not there). One main lacks is never run on main
and stays the gap's, or a stacked gap's first base's that has it (`not_on_main` on `suites_fast`); it is counted and
goes back through the fix path, the fix session and the nack naming whose it is. The run on main is on main itself,
never on the stack of main and the bases. A gap held (`waits_on_main`) on a test its main commit lacks, recorded
before this, is released by the intake at once, `not_on_main` saying which.

Every writer of a flake's state (onmain, the queue, triage, `manage.py flake`) goes through `dev/bin/flakes.py`, which
reads the item again under `run/flakes.lock` and records at once (`ergostat event --add`): a flake seen on a
`main-broken` test is `flake.measured` (counted; it stays main-broken), a second `flake.main-broken` moves `main` and
adds its gaps but keeps the first `main_broken_at`, and either on a `fixed` test makes it again (a patch: `times` 1,
the gaps and times said, `main_fixed_at`, `fixed_by`, `fixed_on` and `passed_on` removed, `green_passes` removed or,
for a seen, set to 0). An item it cannot read is written as said, the failure on stderr. A flake is said fixed by hand
with `manage.py flake-fixed TEST --why W` (below).

**Out of main-broken: main-mend.** The block `main-mend` (dev/model/landing.yaml; every 30 minutes, pool 1, a lease,
timeout 30 minutes) runs `dev/bin/mend.py`: it fetches main as pushed (the checkout's `<remote>/<base>`), waits for a
quiet machine (`fac.wait_quiet`), and takes the `main-broken` tests not tried since they broke, oldest
first (by `main_broken_at`), then the least lately tried (`run/mend/tried.json`), at most `[gates] mend_most` (default
5, held to 1-20), so tests that stay unknown run after run give up their place to those behind them. It runs them alone twice on that commit (together; after a run that died, killed by its timeout with one of them picked, one at a time, each counted tried as it starts, so a hanging test goes behind the others), in `<worktrees>/.mend` and a
suite container (`[suites] alone` with `-rA`; a test of a browser suite file with `rerun`, which has Playwright), and
reads each result from the whole log (`fac.outcomes`). A test passing both runs is `flake.main-fixed` (state `fixed`;
`passed_on`, `main_fixed_at`, `fixed_by: main-mend`). Failed, skipped, not collected, quarantined at that commit, or a
run that stalled or left no log: unknown, and it stays main-broken. The write is decided under `run/flakes.lock` on the
item read there, only when its `main` is the commit run on or an ancestor of it, and is a patch whose first op tests
that `main`: a newer break written in between refuses the whole event, and a refused patch moves no state (SPEC §5a).

**How a flake leaves seen.** Every `flake.seen` sets `green_passes` to 0. After each green landing, once its push
is asked, `flakes.green` reads the unit and browser logs of the run main landed on (both print `PASSED` lines:
`-rpfEs`) for each seen flake that is not quarantined (at most 50, by id). A test with a `PASSED` line and no `FAILED`
or `ERROR` line raises `green_passes` by one (under the lock, a patch that tests the value it read). A test absent
from the logs, one in a suite not run in that batch, or one in a red, stopped or unreadable log changes nothing.
At `[gates] flake_fixed_after` (default 5, 1 to 50) green runs in a row the flake is `flake.fixed`
(`fixed_by: green-runs`, `fixed_on`: main's head). A failure here is said on stderr and never fails or delays the
landing. Only seen flakes are counted; nothing here moves a main-broken one.

## Regression guarantees

What the factory promises of main, each a stock held at zero by a goal, in the system `guarantees` (within
`oversight`; dev/model/guarantees.yaml). Nothing in it acts on the world: each loop closes through people and the
programs already there.

- **main-green.** The stock `main-failing-tests` counts the flake items in `main-broken` (tests failing on clean main
  too). The flow `main-tests-broken` fills it (`flake.main-broken`). The flow `main-tests-fixed` drains it, counting
  `flake.main-fixed` by main-mend. The goal `main-green` (`<= 0`, tolerance 0, critical) is off while any test fails on
  main. Its `on-stale` is `off`, but an items sensor is never stale (SPEC §9.6), so today that changes nothing. Off, it
  asks the coordinator (`fix-main`, a person block in the system, so nothing outside reaches into its loop) to have
  the fix made.
  Once main-mend sees the test pass twice alone on the pushed main, it holds again. The loop is named `main-repair`
  and is drawn balancing.
- **tests-not-falling** (dev/model/guarantees-passing.yaml). `tests-passing` (`dev/bin/passing.py`, every 30m) is the
  summed `passed` of the latest landed queue run on main whose `suites` cover unit, browser and host (a run that did
  not run browser by rule is passed over, never read as a fall), chosen by main's first-parent seq of its `main_sha`,
  never by time. `tests-passing-change` is the latest less the earliest such run within main's last 10 merges, each
  sha once, by the code measures' trend helper (`measure.by_seq`, `measure.code_change`). Counts `unknown` on the
  latest full run, fewer than two full runs in the window, or no checkout: no value (exit 1); a run with no counts is
  never zero. The goal `tests-not-falling` (`>= 0`, tolerance 0, on-stale off) is off when main passes fewer tests than
  10 merges ago. Its loop closes through the coordinator (`restore-tests`, an external block: a fix gap brings the
  tests back; nothing in the factory acts) until regression-guarantees-wired gives it a factory block. This is not the
  test ratio's count (cx-test-ratio: the tests *defined* in the code, from the code-health cache): this counts the
  tests a queue run on main *passed*, so it falls when a test is skipped, deselected or fails to collect though
  still defined. The two are never summed.
- **quarantine-small.** The stock `quarantined` (dev/model/guarantees-quarantine.yaml) is the number of tests listed in
  tests/quarantine.txt on main as pushed (`held.py quarantined`: the checkout's `<remote>/<base>`, never fetched).
  The goal `quarantine-small` holds it at or under `quarantine-most`: 8, the count on main on 2026-11-23. A setpoint is
  a number, so the goal's `hold` writes the same 8, and a test keeps the two equal. The owner lowers both as tests are
  released. The goal goes off only when the quarantine grows, and a list not read counts as off. Off, it asks the
  coordinator (`release-quarantined`, a person block in the system, as `fix-main` is) to have a test released; the
  loop is `quarantine-release`. The stock's flows are its rises and falls over a day. The auxiliary `quarantine-oldest-days` (`held.py quarantine-oldest-days`) is the
  number of days since the oldest `when`. No goal is on it until the owner says how long a test may stay. A list, a
  line or a date held.py cannot read gives no value (exit 1), never 0. A listed test with no flake item marked
  `quarantined`, or such an item whose test is not listed, is named on stderr.
- **flakes-few, main-repaired-fast** (dev/model/guarantees-flakes.yaml). The stock
  `flakes-open` counts the flakes `seen`, filled by `flakes-seen` and drained by `flakes-fixed`, which counts every move
  out of `seen`: fixed by green runs or by hand, or to `main-broken`. So the two flows add up to the stock. `flakes-few` holds each seen flake by its hours in `seen` (`per: item`, on the stock
  `flakes-open-hours`, `measure: oldest` over the same items) at or under `flake-hours-most` (3). Off, it names the
  oldest first. check refuses `per: item` on a count (goal-per), so the definition's "at most 3, the oldest named" is
  one goal on the age, not on the count. Whether it should be the count instead is the owner's question.
  `main-repaired-fast` holds `main-repair-hours` at or under `main-repair-hours-most` (24). The two
  readings are `flakes.py main-repair-hours` and `flakes.py flake-fix-hours`. Each is the median, over the stays that
  ended `fixed` in the last 14 days, from the move into `main-broken` (or `seen`) to the move to `fixed`. The moves are
  read in the record's order, never by comparing stamps. A repeat break keeps the clock, and a flake made again from
  `fixed` starts a new stay. A `seen` stay that went to `main-broken` ended unfixed. At most 500 flakes are read, by
  id, and more is said on stderr. With no stay ended, or a flake that cannot be read, there is no value (exit 1). Both
  goals are `on-stale: off`. Nothing reads either goal yet: they are unserved until regression-guarantees-wired.
- **lessons-hold.** The auxiliary `lessons-recurring` (dev/model/guarantees-lessons.yaml, `measure.py
  lessons-recurring`) counts, over 14 days of reviews (every round), the librarian's classes found that the gap's
  first implementor brief carried. A review whose classes are not recorded, or whose gap has no first brief, is left
  out and counted on stderr, and with none left there is no value. The goal `lessons-hold` holds it `<= 2`
  (`on-stale: off`). Off, it commands `lessons-relearn`, an external block into the librarian that ergostat never
  runs, so nothing changes at run time. Wiring the real loop waits for regression-guarantees-wired.

## The backlog: ranked, groomed

Each gap has a `rank` (lower first), and `value` (1-5), `size` (S/M/L or hours), `risk` and `groomed_why`; the planner
and the implementor take the unblocked gaps in rank order (`takes: {order: rank}`), and the Items page's Timeline
projects them in that order. `dev/bin/solve.py` ranks them: a topological order, by value / size (risk weighs the
size) and a bonus for each gap waiting on it; pins held; a cycle refused. The groomer (`backlog.py groom`, an Opus
session, off until `ergostat sensor grooming-open.main --read 1`) proposes links, value, size and risk, closes (done on
main, or a duplicate) and splits, and asks for `groom-backlog` with the diff (`run/backlog/<time>.md`): approve it in the
inbox. By hand, each change re-ranking the backlog:

```sh
python3 dev/bin/backlog.py show                   # the backlog in rank order (* pinned)
python3 dev/bin/backlog.py pin GAP 1              # or: pin GAP --off
python3 dev/bin/backlog.py dep add GAP ON         # or: dep rm GAP ON (kept: GAPS.md does not add it again)
python3 dev/bin/backlog.py close GAP --done --why "landed in abc1234"   # or --duplicate-of OTHER
python3 dev/bin/backlog.py propose                # the solver's order and why, writing nothing
python3 dev/bin/backlog.py propose FILE           # a proposal as the program checks it, writing nothing
python3 dev/bin/backlog.py refuse-link GAP ON --why "its definition names no need of ON"
```

A refused link (run/backlog/refused-links.jsonl) is dropped from every later grooming proposal, shown among its
refusals with the reason; `dep add` of the same pair adds it and clears the refusal. An unreadable file refuses
nothing and says so in the proposal.

A GAPS.md entry whose head (its opening parenthetical, or the clause after its colon) begins with "done" or
"superseded by" is never found as open, and one the record holds not yet started is closed.

## Milestones: groups of gaps finished together

A `milestone` item (ergostat.yaml) is `waiting`, `active` or `completed`, and `completed` is final (`final:`: no event
moves it out). It may depend on other milestones (`depends_on`); a gap names its milestone in `milestone` (a group
relation: with kind `gap` chosen, the Items page's Graph draws a milestone's gaps in its frame, titled with what is
done, working, ready and blocked on what, and the Timeline gives it a summary row). The block `milestones` (`milestones.py pass`, every
minute, no AI) completes an active milestone with at least one gap once every one is merged or closed (a parked one
holds it open; an empty one never completes), then activates waiting ones whose dependencies all completed, by rank,
while fewer than `[milestones] active_max` (3; at most 20) are active. An `upkeep` milestone, for the factory's own
repairs, is always active and outside the limit; after `[milestones] upkeep_days` (7; at most 90) it completes, its
unfinished gaps move to a new upkeep milestone (`follows` it), which is active at once. The old free-text labels in
some gaps' `milestone` stay as written; `status` lists them until they are assigned.

With `[milestones] enforce = true` (false by default, and then nothing about dispatch changes) the planner and the
implementor take only the work of active milestones. The pass, and each command once it has written, keeps on every
unfinished gap the derived field `waits_on_milestone` (as deps.py keeps `waits_on_parked`): empty when its milestone is
active or it is `pull`ed (the owner's exception: taken as if its milestone were active), otherwise the milestone it
waits for, after the pass's placements (for a gap the pass left: an old label as written, `unassigned` for none). A
sub-gap of a split with no milestone of its own takes its parent's, and is pulled when its parent is (the pass places a
sub-gap in its parent's milestone; a pulled parent still pulls it there, but not one moved to another milestone). Their `takes: where` asks it empty; review and the merge queue ask nothing
of it, so what was built keeps landing. Turning enforcement off clears the field on the next pass.

With `[milestones] enforce = true` (off by default) the pass, under the same lock, then places every unfinished gap
with no milestone (none, an old label, a name that is no milestone) or a completed one, recording `gap.milestone-set`
with `milestone_was` and `assigned_for`: a sub-gap of a split, or a continued gap (the parked gap's `resumed_as` names
it), keeps its parent's milestone; one whose milestone completed joins the current upkeep milestone (the active upkeep
one whose cycle ends last, by its `upkeep_ends`), and so does one the factory filed itself (`source: simplifier`, the pipeline manager's `file-gap`, a
`gap/knowledge-*`); any other joins the first active milestone by rank, or the upkeep one when no other is active. So
a gap is placed at most a pass (a minute) after it is requested, by whatever path. No path assigns a completed
milestone: `assign` refuses it, an upkeep cycle never carries to a completed successor, and a gap that names one anyway
(a raw event) is moved out by the next pass. Each placement is checked for a cycle as `assign` checks one, against the
graph with the pass's earlier placements in it: one that would close a cycle (say the gap depends on a gap in a
milestone that waits on the one it would join) tries the upkeep milestone instead, and failing that the gap is left.
`status` gives the number of unfinished gaps with no milestone and how many of them the next pass places (all of
them after a pass with enforcement on, unless no milestone is active, or each would close a cycle).

A milestone with gaps is a summary in the precedence graph the implementor's take reads (its start before its gaps,
its end after them), and so is a split parent with its sub-gaps (`parent` is a group too), so a milestone dependency
with a gap dependency, or with a split across two milestones, can close a cycle, and a gap on a cycle is never taken. `add`, `depends` and `assign` refuse a change that would put an unfinished gap or milestone on a cycle
it was not on, naming the path, and the pass never places a gap where it would; `status` names any on one (deps.py
records gap dependencies without knowing milestones, so it can still close one). One such cycle is said by name: a gap depending on a gap of a milestone that can only finish
after its own (one that depends on it, at any depth), so both would wait forever. `assign` and `depends` refuse it and
`status` lists any. Pulling the needed gap does not lift the refusal: the link is still a cycle in the take's graph,
which takes neither gap, pulled or not.

```sh
python3 dev/bin/milestones.py add NAME --title "..." --rank 1 [--depends A,B] [--upkeep]   # refuses a name in use
python3 dev/bin/milestones.py depends NAME ON [ON ...]     # refuses a cycle, or a completed NAME
python3 dev/bin/milestones.py assign GAP NAME              # refuses a completed milestone, or a cycle
python3 dev/bin/milestones.py pull GAP                     # or: unpull GAP
python3 dev/bin/milestones.py status                       # each one, its state, what it waits on, its gaps by state
```

## Plans, research and what the factory knows

A gap with no definition is **planned** (`dev/bin/plan.py`), once you open planning
(`ergostat sensor planning-open.main --read 1`): the planner reads the code, docs and knowledge in a read-only clone of
main and writes its definition of done to `run/plans/<branch>.md` (acceptance tests, a budget, the review lessons that
apply as risks, the files to touch); a gap too large for one branch becomes sub-gaps with `depends-on` among them, the
gap waiting in `split` until each is merged. The planner is given the task graph (gaps merged in the last 3 days and
the files they changed, gaps active and ready with the files they touch, 40 lines at most). Each plan is linted by the
program (`plan.lint`, no AI: the sections, tests named `tests/...py::test_name`, a budget within
`[gates] plan_budget_most`, lessons, `depends-on` names and files that exist or are marked new); one that fails goes
straight back to the planner (the 6th failure parks), and a lint-clean one is the definition at once: the gap is ready.
A split is checked further, and sent back the same way, naming the sub-gap or point: each sub-gap's budget must name
at most 250 net lines (`plan.SUB_GAP_MOST_LINES`; no number counts as over; a single plan keeps
`plan_budget_most`), and the answer must hold exactly one `<coverage>` block restating what the parent must do, a
`- ` point per line ending `(by: name, name)`, every name one of the split's sub-gaps (matched exactly) and every
sub-gap named. An accepted block is written to `run/plans/<parent-branch>.md`, over any earlier split's, and is never
made a definition by the lint sweep. Once every sub-gap is merged the join moves the parent to `joined`, never to
`merged`, and the **join judge** (`plan.py join`, `[ai] join_judge_*`) reads, in a read-only clone of main,
the parent's entry, its coverage, and each sub-gap's definition and last review (anything unreadable shown as
`(missing: why)`). A sub-gap whose definition or last review cannot be read (or a child not in the record) makes the
verdict `short` at once, a point naming each, with no clone, no session and cost 0. `covered` moves the parent to
`merged` with its verdict, reasons and `judged_at`, but no `merged_at`: no work merged, so it stays out of
cycle-hours, cost-per-merged and fix-rounds. "Covered" is the planner's coverage mapping plus an AI judgment at the
join, not a proof. `short` requests a new sub-gap `<parent-branch>-join-<n>` (when that one is taken or not safe, the
next unused safe one of `-join-<n+1>`, …, then `<parent-branch>-rest`, `-rest-2`, …, at most 50 of each before it
stops with an error; its entry the parent's title and the points not built), adds those points to the coverage file as `(by: that
name)`, and only then splits the parent again, so the join waits for the new sub-gap. At most `plan.MOST_SHORT` = 1
short round splits again: the second `short` parks the parent, its "Where it stopped" listing the points not built. A
verdict that cannot be read or a failed session leaves it in `joined` (the run fails under its lease); a budget
refusal waits. The judge's verdicts are measured by `splits-covered` (of parents first judged in 14 days, the share
whose first verdict, in record order, was `covered`), `split-budgets-held` (of sub-gaps merged in 14 days, the share
whose `net_lines` are at or under their own definition's `## Size budget`; a definition, budget or `net_lines` that
cannot be read is not held), `split-joins` (parents judged at least once, whole record) and `split-overhead` (the
median, over parents judged covered in 14 days by `judged_at`, of the parent's and its children's AI cost, a parked
sub-gap's and its continuation's both, over the median cost of merged unsplit gaps of the children's size class; a
parent unpriced, with a child unmerged, unsized or unpriced, or with no unsplit gap of its class is left out and
named), and `splits-covered ≥ 0.7` over at least 5 joins is the condition gap/plan-by-size gates XL auto-split on.
There is no plan review: the advisory one was removed (the owner, 2026-11-23: it cost about as much as writing the
code and could not say a plan is good; `dev/records/plan-review-removed.md`). Its old records stay as they were
written (`review/<branch>-plan` items, `plan_review` fields, parks by `plan-review`), and nothing reads them now but
the parks' and the lint sweep's handling of what it left. A definition you write yourself skips all of this. Every brief carries the factory's knowledge (`dev/knowledge/README.md`), and records which entries.

```sh
python3 dev/bin/status.py                                   # one screen: in flight, blocked, failed, queue, spend
python3 dev/bin/request.py "My change" --depends-on other-gap [--definition my-def.md]
python3 dev/bin/ask.py "How does the queue decide a flake?"  # answered in run/research/, summary on the item
python3 dev/bin/lesson.py add "Title" --check "the check"   # or: retire N "why"; proposals wait in the inbox
```

**The knowledge queue.** The review lessons have a work queue of their own, not the gap queue (the owner,
2026-11-21). A `lesson` item moves proposed -> approved -> applied (or denied, retired), with its exact text on the
item (`entry`). The librarian proposes; approving `knowledge-change` in the inbox runs `lesson.py request`, which
records the item approved; `lesson.py add` and `retire` are approved at once. The program block `lesson-apply`
(`dev/model/knowledge.yaml`, pool 1, no AI) then applies it. A new lesson is numbered past the seed's and every applied
one's, and past one kept for each new lesson still requested as an unmerged gap (it numbers itself next in the seed);
a record lesson whose number the seed holds all the same is carried as `lesson-N-record`, said on stderr. A retire marks lesson N (and an applied entry carrying it) retired. There is no session, branch, review,
merge or gap. `knowledge.block` carries the repository's `dev/knowledge/review-lessons.md` (the seed) merged with the
applied items: a "seen as" line goes under its lesson, a new lesson is its own entry, and a retired one is left out
with its lines. The lesson ids and the item ids are recorded as carried, and the existing size budget is unchanged.
When the record cannot be read, the brief says so and carries the seed only. `knowledge.py sync` shows applied
entries as `knowledge/*` items. The items live in the instance's record, so a version switch keeps them.
`lesson-settle` also runs the migration, every run and idempotently. A lesson `requested` under the old path whose
own `gap/knowledge-*` has not merged is approved, for `lesson-apply` to apply and number, and that gap is closed
(`end: superseded`, with the reason). Only a gap in a state no run is in (open, planned, replan, ready, fix, parked)
that no lease holds is closed. A merged one is left alone, since its text is in the files already and is not carried
twice. One in flight or leased waits for a later run, and so does one whose lease fence moved as it was closed (taken
in between). A gap the record does not hold is left alone and reported. No other gap is touched. Measured: `lessons-to-apply` (approved, waiting) held at 0 by the goal `lessons-applied`, which
`lesson-apply`'s loop reads, and `lesson-apply-hours` (proposed, or approved for the coordinator's own, to applied,
over 14 days; `lesson.py hours`). A new lesson from the librarian has no check yet ("not yet written"): retire it and
`add` it again with one.

**Size classes.** Each plan's `## Size budget` holds `size: S|M|L|XL (confidence: low|medium|high)`, a class of the
net lines that will merge outside `tests/` and `docs/` (everything else counts: `dev/`, `scripts/`, `examples/`,
root files): S 50 or fewer (a net removal is S), M 51-150, L 151-400, XL over 400. A definition without it, or with
another class or confidence, is sent back like any other planner problem, never given a default; each sub-gap of a
split has its own. A replan replaces the size, and clears the lines of any earlier merge. At each merge the queue
counts the net lines from main before it to the merged head (in a batch, each gap's own merge, not the batch's) and
records `merged_lines` on `gap.merged`; when that count cannot be read the merge stands, `merged_lines` is null and
`merged_lines_error` says why (a merge again always writes both, so no older count survives).

`measure.py size-accuracy` is, over 14 days by each gap's latest merge, the share of merged gaps the planner sized
whose lines fell inside their class; `size-accuracy-high` is the same for high-confidence gaps. The class scored is
`planned_size` (with `size_confidence`), which only the planner writes. The planner never writes `size`: that is the
groomer's (`gap.groomed`, S/M/L or hours), which the solver ranks by, and it is never scored. A sized gap with no
count is left out of the share (never a hit) and named on stderr; with nothing measurable either one has no value
(exit 1), and `-high` too when only low or medium gaps can be measured.

**Not covered:** gaps whose definitions you wrote (no planner, no size; a plan that finds your definition already
there records no size either), and split parents (they merge nothing; a split clears an earlier size).

**Planning by size.** The planner reads the class already on an open gap (`planned_size` with `size_confidence`,
before it plans) and does as much as the class calls for. Today the only thing that records a class before planning
is the request itself: `ergostat event --add gap.requested --item gap/NAME --data '{"title": ..., "entry": "its
text", "planned_size": "S", "size_confidence": "high"}'`. Gaps from `docs/GAPS.md`, and those the coordinator files
with a definition, carry none. Whether the groomer, the coordinator or a sizing step should record one is still the
owner's call. A gap with neither field takes main's path: the full planner. So does every sub-gap of a split, since
they carry no class. The planner trusts a class only when it is exactly S, M, L or XL and its confidence (low 0.25,
medium 0.5, high 0.75) is at least `[planning] min_size_confidence`. A class or confidence that is present but not
trusted (`"s "`, a missing or unknown confidence, one below the bar) takes the full planner, and so does every replan
(the gap's state `replan`, which the fold sets from the send-back by seq), except an XL one.
- **S**: no session. The definition is written from the gap's own title and text (its entry in main's records,
  else a join sub-gap's `entry`; with neither, or a record that cannot be read, the gap takes the full path) with the house rules' done
  criteria and a 50-line budget, created exclusively in `run/defs/` (one already there, or one that lands first, is
  kept byte for byte and the gap is the coordinator's). `defined_by: size-s`, `planning_cost_usd: 0`. **No AI and no
  reviewer has looked at this definition**; the implementor names the tests.
- **M**: one session under `[ai] planner_m_session_usd`, then ready (`defined_by: plan-unreviewed`, the name it had
  while the plan review read other plans, kept so the record and the flow `plans-unreviewed` read on). If it splits,
  the sub-gaps take main's path.
- **L**: the full planner (`defined_by: plan`).
- **XL**: one definition for the gap itself is sent back ("an XL gap must split"). It counts toward the lint's park
  (the 6th send-back parks), so a planner that keeps answering whole stops costing money.
A cap above `planner_session_usd` (or 0), or a confidence outside [0, 1], stops the planner run with an error before
any session. Unset, the cap is the planner's own and no class is trusted.

Each planner session also adds its cost to `planning_cost_usd` (summed, so plan and replan add up; older gaps also
carry the removed plan review's). A session that times out, errors or is cancelled adds its whole reservation, to `ai_cost_usd` too.
`measure.py planning-cost-share` is planning dollars over AI dollars, of gaps merged in 14 days that carry the field.
A gap without it is left out, never counted as 0; one with a planning cost negative or above its total is left out
and named on stderr; with none it has no value (exit 1). It says where the money went, not that less planning is
safe.

**Done items the implementor cannot do** (`plan.env_needs`, run on every definition the planner, the size path, a
split or the plan lint makes, and on every definition the coordinator wrote, whether the intake or the planner finds
it, or it lands while the planner runs: `plan.route`, the coordinator's file left as it is). Each point of
`## Definition of done` (a numbered or bulleted point with its lines, or a paragraph) is read for what an implementor's
container cannot do. A backticked span that reads as a command (it starts with a known program such as `uv`,
`python`, `git`, `npm`, `docker` or `ergostat`, or a script path with arguments) passes only if it is on the
allowlist once `uv run`, `python -m` and `scripts/suite_watch.py ... --` are taken off: `git`, `ruff`, `pytest`,
`scripts/named_tests.py`, `scripts/demo_check.py`. Any other command is a **measure** need. So are a server on a port
(`port 8765`, `localhost:8000`, "on a port") and an environment variable on a command (`CORR_SHOTS=1 ...`). Screenshots
looked at by a person, the sandbox (`--sandbox`, "docker sandbox", or an item that runs or loads under seatbelt or
`sandbox-exec`) or the platform ("runs on macOS", "checked on a Mac"), and input files read from outside the repository (an input file, or a read, load or
import, followed by `~/`, `/Users/`, `/home/`, `$HOME` or "outside/not in the repo", in an item that does not say
the path is refused, rejected or denied) are **owner** needs. A bare mention is not: `docker run --init` in a test,
"macOS's five-entry limit", "its seatbelt filter lists to 5 entries", "a path outside the repository is refused" are pytest's to check (a command off the
allowlist, like `docker run`, is still a measure need). A measure need of a definition that names no acceptance test
is the owner's too. The definition is given a `## Needs before building` section, a line per such item ("done item N:
`needs: measure`, a server on a port"), and the gap records them as `env_needs`. A definition with only measure needs is
ready, with `measure_runs_wanted` (its acceptance tests and the items): the request a `measure-runs` of those tests
answers once it is built (*The pipeline manager*). One with an owner need is never ready: the same event that records
its definition parks it (`parked_for: needs`, `parked_by: plan-env`, `parked_in: plan`, `parked_until` the items,
who: owner), so the implementor, which takes only ready and fix gaps, never leases it. The owner answers with
`ergostat event --add gap.need-met --item gap/NAME --data '{"need_met": "what was done"}'`, and the park resumer
(`parks.py resume`) makes it ready again as itself (`gap.defined`, `released_from: parked`, then `gap.resumed` with
`resumed_as` its own id), re-read under the continue lock; `manage.py continue` refuses such a park, since no branch
was built to continue. What reads as a command, or as one of these needs, is a pattern list: an item that says it in
other words is not marked (its park comes after a review, as before, and `env-parks` counts it only if the gap was
marked), and one that names a need it does not have in these words (a read from `~/` that is a test's fixture, say)
is parked for the owner until `gap.need-met`: the lists both miss and over-match, and tests/test_plan.py pins only
the cases it names.

## The pools: sized by risk, against your tolerance

One implementor and one reviewer to start (`run/pools.json`; the blocks' `pool:` is only the most, 9 and 6, in
`[pools]`, never above 9). The pool tuner measures **risk** in expected interventions a day at each implementor pool size: factory-
caused interventions per gap given a verdict, plus escapes per merged gap, times the gaps a day at that size (from the
measured cycle time). Each rate is a Gamma posterior per pool size with a weak prior; a size never run starts with a
higher, wide prior, so its 90% bound is high until it has been run (`dev/bin/risk.py`). The **target** is the largest
pool whose 90% bound is within your **risk tolerance** and not above the gaps ready, at fix or building. The tuner
asks for `raise-pool` one step at a time (held in the inbox), only after `[pools] probation` gaps had a verdict since
the last raise; your approval is checked again when it runs (the pool unchanged, the bound still within the tolerance,
the probation over), so a late approval does nothing once those have changed. It lowers the pool by one at once when
the bound at the pool now crosses the tolerance, and never for want of demand alone (an idle slot costs nothing). The
reviewer pool follows the implementor's, up to its most: up with an approved raise, down with each drop. Each decision is a `pool.*` event carrying its evidence; `status.py` prints
the risk, its bound, the tolerance and the target.

**On hold for now**: `[pools] hold = true` in `dev/factory.toml` keeps your pause of 2026-11-20. The tuner
measures and says what it would do (`held` on `pool.measured`) but never moves the implementor or reviewer pool; the
queue's batch is still tuned. Set it to `false` to have the pools sized by risk. A pool you set by hand that was never
run has a wide bound, so the tuner then steps it down until the record narrows that bound.

**The tolerance is yours**: the parameter `risk-tolerance` in `dev/model/pools.yaml` (interventions a day, 2 to
start). Raising it trades risk for velocity: edit the value, and the next tune's target uses it.

**For an intervention to count**, record it (below) with a `class` the factory caused: `environment-defect`,
`self-reference`, `factory-missing-capability` or `queue-interleaving`, or `"factory": true`. The factory's own
records count by themselves: the merge queue stopped (`queue`) and the upgrader unable to bring the instance back
(`switch`). Review findings and a reviewer's park are not harm and do not count. Escapes count against the pools
too: a merge reverted on main (reverts are found by `main-watch`, dev/bin/escapes.py: each `This reverts commit
<sha>` pushed to main is matched to the merged gap whose reviewed head is that merge's second parent, else whose
`main_sha` it is when exactly one gap carries it, and recorded as `gap.reverted` once; one matching no gap is the
intervention `reverted-unmatched`, an escape at the pool size then; by hand,
`ergostat event --add gap.reverted --item gap/NAME --data '{"reverted": true}'`),
main broken by it (`ergostat event --add gap.measured --item gap/NAME --data '{"broke_main": true}'`; the
implementor's triage counts by itself: a `main-broken` intervention blames the gaps whose merge made that main
commit, their `main_sha`, or, with none found, counts one escape at the pool size then), or a later gap or
intervention naming it as its cause (`"caused_by": "gap/NAME"` in its data). By hand:
`python3 dev/bin/pools.py set implementor 2 "why"`.

## The simplifier: a gap that removes code

Every 3 days (`simplify-when`, `dev/model/code-health.yaml`), while no simplification gap is open and the day's money
is not spent, the simplifier (`dev/bin/simplify.py`, a program) picks one module of `ergostat/`, `dev/bin/` or
`scripts/` by its evidence (`scripts/code_evidence.py`, read from main): net lines over the 75th percentile, commits in
the last 60 days, duplicate function bodies and dead candidates, weighted in `[code_health]`. A "dead candidate" is
only a top-level name that nothing else names as a word (strings, tests, YAML `run:` lines and `pyproject.toml`
counted); a name built at run time is not seen, so it is a candidate, never a finding. A module under the coverage
floor (`coverage_floor`, or not in the report), touched by a gap in flight, or picked in the last 30 days is passed
over. Coverage is main's latest report under `run/coverage/`, chosen as `measure.py coverage` chooses it (by seq, on
main, at most 20 merges old); `[code_health] coverage = "FILE"` names one report instead.
It asks for `gap/simplify-<module>-<yyyymmdd>` (`source: simplifier`) with a definition from
`dev/prompts/simplify.md`: remove only, behaviour and tests unchanged, net lines below 0, and one trailer per removal,
`Removed: <class> <path>[::<name>] <lines>`. The ordinary implementor and reviewer build it. Pool 1 is fixed in the
code and held under `run/simplify.lock`. A git that fails, a missing coverage report or an in-flight definition it
cannot read means no pick; the run says why. On each merged simplification, `simplify.py removals` makes one
`removal/<gap>-<n>` item per trailer, and a class off the allowlist is recorded as `unclassified`. It reads only
the gap's own merge (found by its subject in the batch's range), never a batch-mate's commits. To see what it
would pick: `python3 dev/bin/simplify.py pick`.

**The code measures** (`dev/model/code-health.yaml`, hourly): `measure.py code-net-lines`, `code-long-functions`,
`code-duplicates` and `code-dead-candidates` are sums over `code_evidence.py`'s rows on the checkout's main;
`code-coverage` is the latest coverage report's covered statements over its statements. Each reading is appended to
`run/code-measures.jsonl` with the seq and sha it measured. `measure.py NAME-change` is the change over main's last 10
merges, by seq. A sha counts once (its last reading), and a sha no longer on main is not read. The goals
`code-net-lines-not-rising`, `code-long-functions-not-rising`, `code-duplicates-not-rising`,
`code-dead-candidates-not-rising` and `code-coverage-not-falling` each hold one measure, so net lines alone never
say the code got simpler. A size goal off sets `simplify-when`'s `drift` input (`code-drift`), which still waits
while a simplification is in flight. Any goal off asks the coordinator (`code-health-off`). No checkout, a failing
evidence run, no coverage report, an unreadable history line, or fewer than two of main's commits measured within
10 merges: no value (exit 1), never 0.

## Complexity: measured once per commit

`dev/bin/complexity.py` measures a commit of the checkout (by default main) from git, never from the working files.
Each family of measures is a module `dev/bin/cx_<family>.py`. The first is size: per file lines, net lines, bytes and
Python tokens. Its series are the code scope's tokens (`complexity-tokens`, a stock in `dev/model/complexity.yaml`),
net lines and files (cache only). Vendored libraries are marked and left out of every sum. Everything is cached under
`run/complexity/`: `commits/<sha>.json` (one per commit), `blobs/` (each blob measured once per family version and
env) and `locks/`. `complexity.py measure [SHA]` computes what is missing. `value NAME [SHA]` reads the newest
measured first parent and never computes (no value: exit 1). `history` reads the commit files; `rows` and `report`
measure the files, from the blob cache where it has them. `complexity.py list` names every series. No sensor runs it;
the readings are recorded per commit of main, at the commit's time.

## The machine's resources: a cap on the pools

The machine is measured every 30 s (`dev/bin/resources.py`, `dev/model/resources.yaml`): the host's CPU, memory,
disk and threads, the Docker VM's limits and use, and each factory container's CPU and memory, kept on its gap
(`resources`: each session's and suite's peak and mean) and in `run/resources/sessions.jsonl`. The setpoints are the
goals in `dev/model/resources.yaml` (change them there). `session-headroom` is how many more sessions fit, from the
measured use of a session and its suite (of the session alone when `[suites] slot` is set: the slots cap the suites,
and the readings include those running). **The effective pool is `min(pool, busy + headroom)`**: the pool stock is
the risk target (the tuner's, or whatever sets it), the headroom a separate cap in the gates and in each run
(`pools.my_turn`); it only ever lowers what the pool allows. A resource past its goal, or a headroom not known, holds
new sessions (`machine-full`). `disk-cleanup` removes session folders and installs (never current or previous, nor
one whose switch waits) older than `[resources] session_keep_hours`, by the factory's own names only: `python3 dev/bin/cleanup.py --dry-run` says
which. A finished gap's session folders go sooner: once every gap whose branch (or id) the folder's name begins with
is in a state of `[resources] finished_states` (approved, queued, push-pending, merged, closed: the work is on the
branch), unless touched in the last ten minutes or mounted by a running container. A record, the setting or Docker
that cannot be read removes none early. They are counted in `run/resources/cleanup.json`, read as the reading
`sessions-removed-early` (`resources.py line` shows it). `python3 dev/bin/resources.py line` (and `status.py`) prints it all on one line.

## Coverage: the modules below a floor

With `[suites] queue_coverage = true`, the queue's unit run on main (an implementor's runs never) sets
`ERGOSTAT_COVERAGE`. It is on: the tracer's overhead on the full unit suite was measured within the machine's noise
(273 s without, 255 s with, 2026-11-20). Until the queue's first green unit run after this lands, the measure below
has no value. A line tracer (`tests/coverage_lines.py`, Python 3.12's `sys.monitoring`, no package)
records the lines each test process ran of `ergostat/`, `dev/bin/` and `scripts/`. `scripts/coverage_report.py DIR`
combines the workers' files into `DIR/coverage.json`: per module its statements (from the file's `ast`, docstrings
not counted), those covered and the share, stamped with the commit and its `seq` (main's first-parent commits). The
last five reports are kept under `run/coverage/`, by that seq; one that cannot be read is removed at once. The queue
runs main's copy of the script (before the merge), so a branch never scores its own coverage, and a report that fails
or times out is "no report", never a failed merge. `coverage_report.py DIR --below 0.6` lists the modules under the
floor, worst first; the floor is `[code_health] coverage_floor` (0.6).

To measure the overhead again (after a change to the tracer), time the fast unit suite twice, the second time with
the tracer, and compare:

```sh
scripts/in_container.sh uv run python scripts/suite_watch.py -- uv run python -m pytest -q -n 8 --dist worksteal
scripts/in_container.sh env ERGOSTAT_COVERAGE=run/coverage/probe uv run python scripts/suite_watch.py -- \
  uv run python -m pytest -q -n 8 --dist worksteal       # (set inside: the container is not given the caller's env)
```

At 15% overhead or less, `queue_coverage = true` stays; above 15%, the tracer belongs on a nightly unit run instead
(the definition's point 3), with both times noted in `docs/roadmap/overnight/code-health-coverage.md`.

`python3 dev/bin/measure.py coverage-below-floor` counts the modules under the floor, and `measure.py coverage
ergostat/model.py` reads one module's share (the auxiliary `coverage-below-floor` in `dev/model/measures.yaml`). With
no report, an unreadable one, or the latest of a commit on main more than 20 of main's merges old, neither has a
value (exit 1): never 0, never everything below.

**What it does not see.** Code run only in a child process (the daemons, `python -m ergostat` under a subprocess, a
`dev/bin` program called by its path) is not traced, so every share is a lower bound. A module no test imported
in-process is marked `"subprocess-only": true`: its tests, if any, reach it only through a child process, and it is
not known to be untested.

## Approve the push

A green merge asks for `push-main` (exactly that commit to origin's main), held for you:

```sh
ergostat inbox                                  # the push and the switch wait here
ergostat inbox action/<id> --approve --as coordinator
```

One merge waits for its push at a time, and while it waits the queue takes no gap: each run reads `run/queue.json`
under the queue's lock before it takes one (an unreadable file counts as a push waiting), and gives its lease back,
uncounted, saying nothing of the gap; the sensor `push-waiting` only keeps runs from starting. The push is asked under
the lease of the run's own gap but is not fenced by it (`fenced: false` in `dev/model/landing.yaml`): once approved it
runs whatever became of that lease, safe because it pushes only that commit and only as a fast-forward of the remote's
main (a stale one is refused by git). When the run's own gap does not land (sent back, queue-failed) and others do, it
waits at `push-pending` (its lease ends there, not back at `approved`) and its outcome is said once the push settles.
If you deny the push, the queue undoes that merge (`git reset --keep`) and sends the gap back. A push that ran, failed
or was denied is settled within minutes even with no gap approved to start a run: the block `push-settler`
(`queue.py settle`, at most every 2 minutes) is commanded by the sensor `push-settleable` (`queue.py settleable`, every
minute), 1 while a pending push ran, was denied, failed or cannot be read, or a block was remedied. It settles under the
queue's lock when no run holds it (a run holding it settles the push itself), and saves `run/queue.json` before it says
anything, so a run killed part way says an outcome at most once (one killed between the two leaves its gap at `push-pending`
with no push carrying it, which the watch raises as stuck at once). A failed push says the held outcome at once and blocks
the queue; an action that cannot be read is read again on the next two runs before it counts as failed. The watch counts a `push-pending` gap as explained only while its push is held, requested or approved, and one that no
pending push carries as stuck at once.

**The suites in the queue:** ruff (only when `[suites] ruff` is set; it is not, so no batch is red for lint), then
unit and browser at once, then demo_check alone (under the other two's load
its pages drew nothing). The first of them to fail is the one reported, and it stops the rest: a unit failure kills
the browser run still going (and the other way round), which is recorded `stopped_by` it, its own result not judged.

**Which tests run where.** With `[suites] queue_container`, ruff (when set), unit, browser and demo run in containers, each on a
copy of the checkout (tarred into the container's stdin, never bind-mounted: Docker Desktop's file sharing keeps a
handle open on every file read through a mount; `vm-open-files` in `dev/model/resources.yaml` watches that count), where
bwrap cannot make its namespaces and there is no kqueue: `tests/test_repair2.py` and `tests/test_sandbox_attacks.py`
(the AI repair sandbox's tests) and `tests/test_notify.py`'s kqueue test skip there. `[suites] host` runs those three
files on the Mac, outside any container, after unit and browser and before demo, under the queue's lock: a required
step like the others (its log `run/queue/<run>-host.txt`, its result `host` in the gap's `suites_queue`; red fails the
batch and is split, and flake triage reruns its tests on the Mac too). It is held to the same `stall_minutes` and
`wall_minutes` as the boxed suites, in the queue and in triage's rerun: a host run that stops writing is a stall (the
run undone, no gap blamed until `STALLS_MOST`). `host = ""` turns the step off. Exit 126 or 127 from the outer shell
(the step's first command not found or not runnable) is a step that did not start, in the queue and in triage's
rerun: the run fails and is undone, no gap blamed, never read as a pass. A pytest missing behind `suite_watch.py` or
`uv` exits 1 with no test named, so it counts as a real host failure: red, the batch split. A test the host step
skips that the same run's unit suite skipped too (by `path:line` in their `-rfEs` summary) ran nowhere, and fails the
step, unless its reason is one of the stated needs outside the machine in use (an `ERGOSTAT_…_URL`, "spends money",
"no Chromium to drive", playwright not importable, "needs Docker and the agent image", "no N free ports in"), matched
as those exact phrases: a new external skip reason must be added to `queue.EXTERNAL`, or it counts. When the unit log
is missing, or counts skips without naming them, every host skip counts as one that ran nowhere.

**The quarantine.** `tests/quarantine.txt` (`test id | who | when | why` a line) names tests the queue's, flake
triage's and the implementor's suites deselect (`--deselect`, unit and browser only: a quarantined test in the host
step's files still runs there and blocks, since run beside in the container it would only skip). The list is read
from main (the queue's and triage's `pre`, the drop's main for the implementor), never from the branch under test: a
branch that adds its own failing test to the list is still red in the queue, and its line takes effect only once it
is on main. (The implementor's fast suites, which land nothing, also deselect the work's own lines, unrun: a branch
that adds the list, or a line to it, is not held up on its own machine by a test it quarantines; the queue still runs
it.) After each unit run (and each triage rerun) the quarantined tests run once more, with `-rA` (the queue and
implementor: `[suites] alone`; triage: `rerun`), never blocking. Each result is said on `flake/<test>`
(`flake.measured`: `quarantined`, `last_run`, `last_run_log`), read from that run's whole log: `pass` only on the
test's own PASSED line with no FAILED or ERROR line, `fail` on either, `unknown` otherwise (skipped, not collected, a
run that never started or left no log). A skip is never a pass. A flake item still marked `quarantined` whose test is no longer on main's list is
released at the next such run: one `flake.released` (`quarantined: false`, `released_at`), not a measurement. When a queue failure names only quarantined tests, triage
sends the gap back to the queue with no flake seen and no retry spent. Tests are added and released by hand, by
a change to main's list (which a reviewer reads in the diff); nothing in this code quarantines or releases one.

**Batches.** The queue merges up to `batch` approved gaps onto main in turn (in rank order) and runs the suites once.
The batch is 1 to start (`[pools] batch = 1`: one gap a run, the queue as it always was). A green batch asks for one
push, of its last merge, so one approval lands the batch, and a denial sends every gap of it back. A red batch is
handled by the first of two paths that applies, and any part still red takes them again. **By name:** the red run named
at most 10 tests, did not crash, and they fail alone on its tree: they run on every prefix at once, the first failing
prefix's last merge goes to flake triage, and one full run lands the survivors. **By halves:** anything else (no test
named, a crash, failures that pass alone, too many): two halves, stacks kept whole, each built from the current base and
run through the full suites at the same time (`dev/bin/halves.py`). A green half lands as the very commit tested and is
the new base; a red one is split again on it. A crash (pytest exit 3, `INTERNALERROR`, a full disk, a lost xdist worker)
names no test and proves no merge bad: both halves crashing, or one merge alone, is a stall.
When the red run named its failing tests (`FAILED`/`ERROR` lines), those are first run alone, serially
(`[suites] rerun`, `-rA`), on the whole red tree. **A flake lands:** when it named 1 to 3 tests, none in
`tests/test_page_polling.py`, and its failed suite skipped none, they are run alone there twice; each passing both
times (a PASSED line, rc 0), the suites the red run did not finish (stopped by its failure, or never reached) run, and
green there the batch lands with no split, each test a flake seen (`flake.seen` on `flake/<test>`: the run, the suite,
`passed_alone`, the log; `excused` in each gap's `suites_queue`). **A failure that is main's blames no gap:** before
any gap is blamed or sent back, the named tests (only those: seconds, not a suite) run alone on main as the batch
found it (`pre`), in the same container and settings. Failing there and again on a re-run (or a re-run that cannot
tell), the failure is main's: the batch is undone, no gap is sent back (they all stay `approved`; the run's own gap's
lease is given back uncounted), each test is `flake.main-broken`, run/queue.json holds `main_red` (main, the suite, the
tests), and an intervention of class `queue` naming main and the tests is recorded, which pipeline-watch raises as a
situation. Each later run first runs those tests alone on main's head, less any quarantined there and any main's head
lacks (its file gone, or no `def` of its name in it: a test removed or renamed on main holds nothing), and takes no
batch until they pass or none is left; it then records the intervention remedied. The coordinator may also remedy the
intervention themself (`manage.py remedy`): the next run clears `main_red` without checking. A check that cannot tell,
or whose container does not start, keeps the hold. If any one named test fails on main twice the whole batch is
held, so a test a gap really broke beside it is found only once main is fixed. A test that fails on main and
passes on its re-run is a flake seen (`failed_on_main`), not main's, and the batch is split. The check is made until
something settles, once for each test; a failure the red run did not name is not checked on main. A named run never
lands anything: only a tree a full run passed does. When both halves pass, the first lands and the other is tested on
it; a tree already proven red is not run again. **Cost of one failing merge of m:** by name, 2 full runs and a round of
its tests; by halves, one full run and at most `ceil(log2 m)` rounds of two at once, the first landing a half. Two half
runs each get half of `[agents] queue_cpuset` (12-17 and 18-23: unit 4 and browser 2 CPUs, half the pytest workers), and
twice the stall and wall limits up to their ceilings, as each may take twice as long. Each gap's `suites_queue` says `batch_rounds` and `rounds` (each round's
base, and each half's gaps and result). A
batch's other gaps stay `approved` until their merge lands (or is sent back), and the run's start is kept in
`run/queue.json`, so a queue killed part way strands nothing: the next run puts main back and takes them again.

The batch is filled with gaps that merge. The queue walks the approved gaps in rank order and dry-merges each onto the
batch so far (`git merge-tree --write-tree`, which leaves the checkout alone) until the batch is full. A gap that
conflicts with main is sent back at once, as a failed gate, and takes no slot. A gap that conflicts only with a
batch-mate stays `approved`, with no gate failed, and waits for a later run. The run's own gap is always in its batch
unless it is sent back: the last slot is kept for it, however low it ranks, and when it conflicts only with a
batch-mate the walk is made again with the own gap first, so the batch-mate is the one left `approved`. Its lease is
never given back while others land, since the batch's push is asked under it. When the own gap is sent back, the walk
is made again in rank order, so gaps passed over for its slot fill the batch. Whether a gap conflicts is git's exit
code, not the files it names. The batch's first run is built the same way, as commits of its own: its tree must
be the dry-merged one, or the run stops before any suite. A merge that conflicts on a new base (after the other
half landed) goes back to `approved` uncounted with what stacks on it, and the next run decides it against main. If git cannot make a dry merge at all, the run fails there: gaps
already sent back stay sent back, the rest stay `approved`.

A batch that comes back empty says why, and picks() gives the reason from its walk. Either the own gap was sent back
(its findings name what for, a conflict naming no file among them), and that is its outcome, or its dry merge failed
only with batch-mates on both walks. In that second case the gap is given back with the reason (uncounted, taken again
after 10 minutes), and the count is kept on the gap as `empty_batches`, per reviewed commit. The third such run on
the same commit (`EMPTY_MOST` in queue.py) sends the gap back instead, as a failed gate, with the reason as its finding,
so it is never taken forever.

A suite that hangs does not hold the queue for the block's 3 hour timeout. Each of the queue's and triage's suites is
stopped (its process group and its container) when its log has not grown for `[suites] stall_minutes` (10; at most 60)
or when it has run past `[suites] wall_minutes` (45, three times the 15-minute `suites-in-time` goal; at most 120).
A value past its ceiling, or not above 0, is refused when the settings are read, and again when a suite starts. Past
either limit the run's lease is no longer renewed. A stopped suite is a stall, not the batch's failure: main is
undone, the run's own gap gets `stalled` (the suite), `stalled_why`, `stalled_test`, `stalled_tail` and
`stalled_batch`, and its lease is given back uncounted, so it and its batch-mates (which never left `approved`) are
taken again, with no failed gate and nothing sent to fix or triage. `-q` prints no test ids while tests run, so each
of these suites runs with `PYTEST_ADDOPTS=-o faulthandler_timeout=<half the stall limit>`. A test still running then
has its stack dumped into the log, and `stalled_test` is the `tests/test_*.py::test_*` function in the last such
stack. A method or a parametrized case is named by its file and function only. With no stack, it is the last test id
the log names, or null. Each hung test's dump grows the log once, so it stops the suite up to half a stall limit
later. A stall also halves the next run's batch (at least 1), so a gap that hangs tends to come to run alone. This is
not guaranteed: any run that settles a gap clears the halving, and a stall in a batch of more than one counts on no
gap. A stall after a half landed keeps that half and gives the stalled merges back. Gaps that run already sent on (to
triage, or back for a conflict) keep that outcome, though `stalled_batch` still lists them. A stall
with the gap alone in its batch is counted on it (`stalls`). The clocks start once `[suites] slot` (triage's suites)
is held, so a wait for the slot is never a stall. Its third (`STALLS_MOST` in fac.py) is no longer given
back: it goes to triage as `queue-failed`, the stalled test as its failed test. In triage, a stalled rerun gets the
same fields and `stalls`, and its lease is given back the same way until the gap's third stall. Then the failure is
the branch's: back to fix, or parked by the kill rule.

The factory's own tests run inside these containers too, so a test of the factory must not depend on the queue's
environment. What the queue sets there (`PYTEST_ADDOPTS`, `UV_PROJECT_ENVIRONMENT`, `PYTHONPYCACHEPREFIX`,
`RUFF_CACHE_DIR`, `SPLIT_SHOTS`; `QUEUE_ENV` in tests/test_factory.py) is not passed on to the processes started with
the `Factory` fixture's `env`: it drops `PYTEST_ADDOPTS` and `SPLIT_SHOTS`, and sets the other three itself (the
running venv, caches under the test's own folder). A test that starts a process with `os.environ` of its own, or runs
factory code in its own process, must set or clear what it reads (monkeypatch). A new setting the queue gives its
containers goes into `QUEUE_ENV`: the queue-container test fails until it does.

To raise it: approve the pool tuner's `raise-pool` (role `batch`; it asks while the queue wait is over its goal,
`queue-wait-short`), or by hand, from the instance, `python3 dev/bin/pools.py set batch 2 "why"` (it is kept in
`run/pools.json`, which wins over `[pools] batch`; `set batch 1` goes back). At most `[pools] batch_max` (8, never
past 32). A run starts no suite run once `[pools] batch_minutes` (120; a value of 0 or less, over 150 or NaN is refused,
and the queue takes no gap) have passed since it began, the wait for the lock and a quiet machine and the dry merges
included: it stops splitting, what a full green run proved has landed, and the gaps not yet settled go back to
`approved` uncounted, for the next run. A run that settled none of its batch leaves the next one half as many
(`cap` in `run/queue.json`, cleared by the first run that settles one), down to a batch of 1, which is one suite run.
So, whatever the batch, the block's 3 hour timeout is reached only by a suite run begun inside the allowance that
lasts past it (over 60 minutes at 120, 30 at 150); nothing here bounds a suite run that hangs. Each run's
`queue_runs` entry says how many it `tried`, `landed` and `given_back`. Each pytest suite's result in `suites_queue`
(`unit`, `browser`, `host`; never `ruff` or `demo`) has `counts: {passed, failed, skipped, deselected, errors}`, read
from the last pytest summary line in its whole log (`fac.counts`), or `"unknown"` when it has none, was stopped by a
failing sibling or could not be read; never zeros; `"not_run"` is kept for a suite not run by a rule, neither unknown
nor zero (a suite turned off, as an empty `host`, has no entry at all). The one such rule: **a batch runs the four
browser files only when it touches what they test**, that is when `git diff --name-only` from main before the batch
to its merged head names a path matching one of `[suites] browser_paths` (by default `ergostat/web/**`,
`examples/**`, the two layout fixtures, `tests/layout_*` and the four browser files; fnmatch globs, `*` crossing `/`).
Otherwise `suites_queue` says `browser: {not_run: "no browser path changed", counts: "not_run"}`, and a red run counts
that suite as finished, never stopped, so a flake's rest of the run does not start it either. The batch decides once,
on its first full run, and the full runs of its halves keep that. An empty or absent list (or one that is not a list of
globs, or a diff that cannot be read) runs browser in every batch, as before. A page broken from a path not listed is
found by the daily browser run on main (below), the net for what the queue no longer runs. A landed run's
`queue_runs` entry has `counts` summed over the pytest suites that ran in the green run main ends at, `suites` naming
them, and `"unknown"` if any of them is. The browser's `skipped` field is unchanged. `merges-per-hour` (gaps merged over the hours
of every queue run, each run's whole length once) measures what it buys. If the push fails, or a merge cannot be undone, the queue stops and records an intervention
(`ergostat item --kind intervention --state open`); it goes on once you record that intervention remedied:
`ergostat event --add intervention.remedied --item intervention/queue-... --data '{"remedy": "..."}'`.

**The daily browser run on main.** Once a day (`browser-daily`, every 24h; `dev/bin/browserday.py`) the four browser
files run on the remote's main, whether or not anything merged since: it tests main, not changes, so a change that
breaks a page from outside the browser files' paths is still found. It takes the queue's lock, so it never runs
beside a batch (a batch waiting for the lock starts after it), then waits for a quiet machine. It runs in a detached
worktree of its own at `origin/main` (`<worktrees>/browser-daily`, made and removed by that name), in the queue's
suite container with main's quarantine deselected; the worktree, the suite's processes and its container go on every
way out (a stop, a timeout, an error; a SIGKILLed run's are removed by the next run, or by the queue's sweep). Green:
`run/browser-daily.json` keeps `{sha, at, green: true}` and that sha as `last_green`. Red, naming tests: each (the
first 8; the rest count as real) runs alone twice (`[suites] rerun`, `-rA`). One passing both times is a flake seen
(`flake.seen`, suite `browser`, the run and its log), and raises nothing; when every one is a flake the day counts as
green. The others raise one intervention of class `queue` (which pipeline-watch raises as a situation) naming them,
main's sha, and the first-parent commits since the last green sha as `suspects` (the latest 50 when no green is known
or it is no ancestor of main). A red run that names no test (a skip, a stall) raises one with the log's tail, and so
does a crashed run (the queue's `crashed()`: exit 3, `INTERNALERROR>`, a full disk, a lost worker, read from neither a
PASSED, SKIPPED, XFAIL or XPASS line nor the test name on a FAILED one, so a test named for `[Errno 28]` is no crash), whose FAILED lines
are not read, since they name whatever was running; neither is ever green. It holds no batch back: the queue's own check on main (`main_red`) is unchanged. The auxiliary
`browser-main-green` reads the file (1 green, 0 red; no reading when it is missing or cannot be read), and the goal
of that name shows it on the Dynamics diagram. The daily run reads the goal (read, not commanded, so it keeps its
schedule) and sets the auxiliary, so the goal's loop closes inside landing. What makes main green again is a fix
merged, by way of the intervention.

Each run's batch is an item, `batch/<run tag>` (`dev/bin/batches.py`; `ergostat item --kind batch`, the Items page, its
graph and Timeline), so what the queue is doing is read in ergostat, not in `run/queue.json` and the logs: `testing`
while a run of the suites is under way, `isolating` between the runs of a red batch, `pushing` once something landed
and its push waits, then `landed`, `partial`, `failed` (nothing landed and a gap failed, or the push was denied) or
`given-back` (nothing landed and nothing blamed: a stall, main red, out of time, an error). Its `runs` list each run:
its kind (`full`, `named`: the failing tests on each prefix, `halves`: a round of two halves, one run), the gaps it
covered, `outcome` (passed, failed, crashed, stalled), `failed` and `passed` summed over the pytest suites that said
counts (`counted` names them; none said: neither is known), the first ten failing tests, minutes and a crash's cause.
`isolated` says each gap found failing, how and on which tests; `given_back` and `why`, how it ended. It links to its
gaps, and each gap's page lists its `batches`; the events carry no logs. While a run is under way, `batch-run-percent`
and `batch-run-failures` read its progress from its own pytest logs (the least advanced; the F and E so far), never
from the record. Saying any of this never fails or delays a merge: a failure to write is dropped. A batch whose queue
run was killed ends when the next run takes over: `given-back` when recovery puts main back, and, killed after its
merges landed but before its push was recorded, with what it landed (`why` says it was killed) as the next batch begins.
The batch kind is a pipeline (SPEC §5a, *Stages*): each stage of each run is said as it starts and ends
(`batch.stage-started`, `-finished`, through `batches.stage()`): ruff, unit, browser, host and demo in `suites()`
(`passed`, `failed`, `stopped` when the failure of the suite beside it stopped it, `error`), `named` in `named()`
(the failing tests alone, on main, and on each prefix), and `push-wait` from `pending()` until `pushed()` settles it.
The Dashboard's Merge queue row (the root model's `record` sql source) reads them: the running batch and the gaps
waiting in rank order, its stage now with elapsed, expected and time left, each of its stages, recent batches and the
median of each stage over time; a Prometheus scraping `/api/stages/metrics` has them as histograms.

The merge pipeline's health is read from the batch items (`dev/bin/landing.py`, through `measure.py`):
`main-still-minutes` (since the latest batch whose landing stood, ended `landed` or `partial`, at its `landed_at`;
one still pushing, or whose push was denied, moved nothing), `batch-runs`, `batch-first-green`, `crash-lost-minutes`
and `gaps-landed-per-hour` (the last day, landings that stood), charted together on the dashboard
`landing.merge-pipeline`. The goal `main-moving` (in `landing.yaml`, beside its measure; the pipeline watch reads its
reason in code, with no `in:` edge, which would widen `managing`'s boundary) holds `main-stalled-minutes` at 120 (tolerance 30): the minutes main has
not moved while gaps wait (approved, queued, or leased by merge-queue), from the later of its last move and the oldest
waiting gap's approval, so it is 0, never off, while nothing waits. Its reason, `measure.py main-stalled-why`, names
the current batch, its run and the cause ("batch/x-… (isolating, 3 gap(s)), run 6 (halves) crashed: OSError: …"); the
pipeline watch puts it in its `no-merge` condition, and the pipeline manager's brief carries it and the current batch's
fields under *The merge queue*, in place of `run/queue.json`. A waiting gap's *Why isn't this done?* names the batch it
is in, with its run, or how many batches holding approved gaps are ahead of it (SPEC §5a, *place*).

A gap is never left a dead letter: a run that fails on its last attempt parks the gap with where it stopped, and the
`dead-letters` block parks any that a killed run left behind. Every container the factory starts is named
`ergostat-factory-*`, killed when its run ends or is stopped, and swept by `main-watch` once past its time.

## Stacked gaps

The factory does not wait for a dependency to merge. `depends_on` in ergostat.yaml is
`{kind: gap, starts_at: [approved, queued, push-pending]}`, so the implementor takes a ready gap as soon as each
dependency is reviewed (approved) or further along, and it is not yet on main.

- **Built.** A gap whose every unfinished dependency is approved, queued or push-pending is built on their reviewed
  heads, not on main (implement.py, step 1). main and each base are merged, in rank order, into
  `refs/stack/factory/<branch>`, and the branch starts from that. The gap says so in `stacked_on: [{gap, sha}]`, and
  says that base's commit as `stack_base` in the event that says its head. Its net lines, strays and check findings
  are measured against that base.
- **Reviewed.** The reviewer judges it against the same base, never main (review.py `stacked_base`), so its diff, its
  net lines (the same number its implementor counted) and gate 1 cover only its own commits. It reads the base from
  `stack_base`, said with the head it reviews (the ref only for a gap built before that field), so a review taken
  while stack-forward moves the gap sees one head and its own base. The brief says it is stacked and names its
  bases. When stack-forward brings a base's new head into a built gap, it makes a new base commit (the old base and
  that head merged, no ref written), merges it into the gap in the head's place (stack.py `restack`), says the new
  head and `stack_base` in one event, and only then moves `refs/stack/factory/<branch>`, from the old value only, so
  the base stays below the head and the base's fix commits stay out of the gap's diff. A
  head that does not hold that base, or a base that does not hold every `stacked_on` sha (one stack-forward could not
  move), is a blocking finding, and the gap is judged against main, its bases' lines included.
- **Landed.** The queue lands a stack bottom-up, all of it or none (queue.py).
- **Said.** Its `blocked_reason` on the Items page reads `stacked on gap/x (approved)` rather than "waits on". The
  auxiliary `gaps-stacked` (`deps.py stacked`: the gaps with a `stacked_on`, or one that cannot be read, and not
  merged or closed) shows stacked work on the Dynamics diagram. It is an auxiliary, not a stock, because those gaps
  are already counted in their own states' stocks.
- **When a base fails or parks.** A base sent back to fix, or failing in the queue, leaves `starts_at`. A gap not
  yet started waits on it again (`waits on gap/x, which is fix`). One already built stays as it is, and the merge
  forward below brings in the base's fixed head once it is approved again. A parked (or dead) base sets
  `waits_on_parked` on what depends on it, and the implementor does not take it until the base is continued or the
  dependency removed. A descendant already approved or queued is not landed without its base, because the queue
  takes a stack whole or not at all.

A base can move after that: sent back by review or triage, a fix round adds commits and it is approved again at a new
`reviewed_head`. The block `stack-forward` (`dev/bin/stack.py`, every 5 minutes while `stack-forward-when` commands
it: the sensor `stale-stacks`, which counts the stacked gaps whose base has moved or landed, above 0) merges the base's new head
forward into each gap stacked on it. It never rebases or squashes, so the review history stays. One pass runs under
the queue's lock, taken only if it is free (a queue run holding it means the next pass). It reads the gaps inside the
lock and takes the stale ones bottom-up, so a stack of three moves in one pass:

- a gap leased, building, in review or in fix is never touched: its next implementor round merges the base itself
  (`fac.stack_base` reads the bases' reviewed heads again), and a fix gap's review findings stay as they are;
- an approved gap whose branch is no longer its reviewed head is left alone (the queue refuses it as it is);
- otherwise each moved base's head is merged into the gap's branch (`--no-ff`, by the factory) in a scratch clone of
  the drop. The drop's branch moves only from the tip it was read at (update-ref's old value): a branch moved by
  another writer is refused and theirs is kept. The gap's state is read again just before, and a changed one is
  refused too (this narrows the window to a reviewer or implementor lease but does not close it). When the merge is
  clean, `stacked_on` is updated. An approved gap stays approved with the merge as its `reviewed_head`
  (`reviewed_by: stack-forward`): the merge brings in only reviewed commits, and the queue tests the result. A built
  gap gets the merge as its `head`, so the review judges it;
- a conflict is aborted and the gap is sent back to fix (`sent_back_by: stack-forward`, the files in
  `stack_conflict`), not counted as a failed gate. In fix it is no longer stale, so a later pass does not send it
  back again. The implementor's next round merges the base again and hands the conflict to its session;
- a base that has landed (merged or closed) is dropped from `stacked_on`, and nothing is merged.

A `stacked_on` that cannot be read, or that names a gap not in the record, counts in `stale-stacks` and is never
moved. The pass says what it did with each gap on stderr, in the block's log.

## Time in each state

(The measure sensors, `dev/bin/measure.py`, share one listing of each kind: run by the engine, the first reading of a
kind lists it, under that kind's lock in `<state>/listings/`, and the readings within the next 120 s, `listing.SHARE`,
read that listing, so readings due together make one listing of the gaps, not one each. A listing that fails is not kept. The
15-second load sensors, `dev/model/interlock.yaml`, read on the engine's fast lane, never behind them.)

Every ten minutes the `timer` block (`dev/bin/times.py`) reads the record of each gap whose events grew since it was
last read (at most 50 a run, those never read first) and writes `gap.timed` on it when its timing changed, for any gap
whatever its end (merged, parked, dead or still open). Its bookmark, each gap's count of events read, is kept in
`run/times.json`, outside the record, and moves on every read, so an event that changes no timing is read once; a lost
or unreadable bookmark makes it read every gap again (and write only a changed timing). Each is counted from the record alone:

- `time_in`: per state, the hours of its visits summed and how many (`visits`), and when it last left (`left`). A
  visit runs from the move into the state to the next move, in the record's order (the fold's moves, the lease's own
  `leased` and `dead` among them); the visit a gap is in now counts once it ends (`status.py` shows it apart).
- `loop_rounds`, `loop_hours`, `loop_ended`: the build-review loop as one span, from the first time the gap is taken to
  build (leased from ready or fix) to the first approval, park, close or dead letter after its last build and its last
  send-back; its rounds are its builds. A queue send-back (a conflict, a denied push, a real failure) reopens the loop:
  it ends at the approval after it, or at a park or close straight from fix. While it still goes round, `loop_ended` is
  empty and its span runs to its latest move.
- `gates`: the minutes of each gate, summed over its rounds, and when it last ran: `implementor` (its runs,
  `build_hours`), `fast` (its fast suites: ruff, build or unit, and browser with `build_browser`, every try in a round, `fast_seconds`; a build recorded before it
  has only its last try, `suites_fast`), `review` (`review_hours`), the queue's `unit`,
  `browser` and `demo` (`suites_queue`, failed runs too), and `push-wait` (a merge to `gap.pushed`, a push said pushed
  at once, or the coordinator settling it).
- `catches` (`{gate: n}`) and `catch_times` (`{gate: [time, ...]}`): each time a gate in `CATCHING` sent the gap
  back: `gap.sent-back` by its `sent_back_by` (`queue`, `triage`, `review`, `measure-runs`), `gap.plan-sent-back` by
  its `plan_sent_back_by` (`lint`), and `strays` (a `gap.measured` whose `suites_fast` names the implementor's stray
  files: its last try in the round only). Any other sender (the stack's `stack-forward`, a missing one) is counted
  under `unlisted` and named on the timer's stderr. `measure.py gate-catches-GATE` sums them over every gap by each
  catch's own time in the last 14 days (a gap whose catches are unknown left out and counted on stderr);
  `dev/model/guarantees-gates.yaml` holds one auxiliary per gate with no goal, and the simplifier's brief names each
  gate with no catch in 30 days as one to question, never to remove unasked. Rolled up, they start from the
  snapshot's `catch_times`; a snapshot without them leaves them unknown (`null`), as the gates.

A gap's record rolled up (after 7 days by default, `ergostat/rollup.py`) starts with a snapshot: its moves are kept
there, so `time_in` and the loop are counted as before, but the events carrying the gate times are in the archive. The
gates start from the snapshot's own (what the gap's last `gap.timed` before the roll-up said), and only the events
after it are added, so a later event or a lost bookmark recounts them the same; a merge in the snapshot still waiting
for its push is carried over from the snapshot's state. A gap rolled up before it was ever timed (the first run on an
old record) has its gates unknown (`null`), counted in no gate's measure rather than as zero, and stays so even if
it is built again (a sum of only its later rounds would be an undercount read as a whole); gate events between its
last `gap.timed` and the roll-up (only if the timer was stopped that long) are not counted.

The measures (`dev/model/times.yaml`, the system `times`: `in-STATE-hours` in its subsystem `state-times`, the loop's
and the implementor's, fast suites' and review gates' in `loop-times`, the queue's gates in `gate-times`) are
`in-STATE-hours`, `loop-hours`, `loop-rounds` and `gate-GATE-minutes`, each the median and with `-p90` the 90th percentile (nearest rank) over the last 14 days, of the
gaps that left the state, ended the loop or passed the gate in the window, not only the merged ones; 0 with none.
A median the pipeline manager can act on has a goal (`hold:`), read by the pipeline watch: off past its tolerance, it is
a trigger of the manager's next session, and each goal's reading is on the situation (`times`). With no gap in its
window the reading is None there and raises nothing (an empty window is no fault; the measure's own sensor still reads
0 then). One that cannot be read (a malformed or non-finite value, a measure times.py does not know) is None and a
trigger naming the goal and the error. Answered, a goal's trigger is raised again when it is a whole tolerance further
off, when its error changes, or when it goes off (or unreadable) again after a reading on target, unknown or unreadable
in between: when each such episode began is kept in `run/manager.json` (`episodes`), and is part of the fingerprint.
The p90s and the rest are plain measures, the file's header says which and why. The shipped holds are first guesses,
and `python3 dev/bin/times.py setpoints` in the instance's folder sets each to today's reading (one with nothing in the
window keeps its own). `status.py` prints them as a table, the waiting states first (time spent waiting on someone
else, the cheapest to remove: open and replan for the planner, planned for the plan lint's sweep, split for its sub-gaps,
ready and fix for the implementor, built for the reviewer, approved for the queue, queue-failed for triage, dead for a
park), then the working ones, where a run holds the gap (leased: the planner's and triage's whole
run and the others' start, the queue's wait for its lock with it; building; in-review; queued: the queue's run from its
`gap.queued`, said once it holds its lock, the merge and the suites), the loop and the gates, with how many gaps are in
each state now and the oldest of them.

## Record an intervention

Each time you step in by hand, say so: it is evidence of a loop the factory lacks. One the factory itself caused (its
`class` one of those under the pools, above, or `"factory": true`) counts against the pools' risk.

```sh
ergostat event --add intervention.recorded --item intervention/2026-11-20-unstick-alpha \
  --data '{"reason": "the worktree was left mid-rebase", "class": "worktree", "recorded_at": 1795160000}'
ergostat event --add intervention.remedied --item intervention/2026-11-20-unstick-alpha --data '{"remedy": "gap/..."}'
```

A flake that cannot pass again (its test deleted or renamed) would stay `seen` or `main-broken`, and every goal on those
stocks with it. Say it is fixed:
`python3 dev/bin/manage.py flake-fixed tests/test_x.py::test_y --why "renamed to test_z"`. That writes `flake.fixed`
(`fixed_by`: you, `why`) under `run/flakes.lock` and records the intervention (`flake-fixed`, class `flake`). It
refuses a test with no flake item, or one that is already `fixed`, and any call but the coordinator's: the pipeline
manager's is refused (it is not among its tools).

## The pipeline manager

What the coordinator did by hand and recorded as interventions (a gap parked on main's own failures continued, a gap
re-approved after an environmental queue failure, the queue unblocked, a missing gap filed) is the pipeline manager's:
an AI block (`pipeline-manager`, `dev/model/manager.yaml`; `[ai] pipeline_manager_model`, Opus, and its own
`pipeline_manager_session_usd`; pool 1; within the daily cap). **One session sees the whole pipeline**, in a container
on a read-only clone of main, its conversation kept as a session item related to its `situation/*`.

**When it runs** (`dev/bin/watch.py`, the block `pipeline-watch`, a plain `every: 5m`; `[manager]` in the settings):

- on a schedule, `every` (2h, never under 15 minutes; `broken_minutes` never under 5): the routine review;
- before the schedule is due when the merge pipeline has been broken past `broken_minutes` (30), but never sooner than
  `broken_minutes` after the last session of any kind (scheduled, broken or failed), so a break found just after a
  session waits up to that long again: the queue blocked, a pending push that
  old, no merge in that long while approved gaps have waited as long, the interlock holding the queue that long (its
  text names each reading that holds it, with its value and limit: `suites-running 8 over 6`, `threads`, `memory`, or
  `push-waiting 1` as `queue.py waiting` reads it, `push-waiting unreadable` when it cannot), or the same test failing on two main commits (at once; only while those `main-broken` interventions are unremedied). The
  sensor `pipeline-broken-minutes` reads the minutes past `broken_minutes`, so its goal holds at 0 and follows the
  setting; `minutes-since-manager` is a measure with no goal, as it rightly grows while nothing changes. When each
  began is kept in `run/manager.json`; a new push or block
  has its own clock. A break already looked at does not start another session;
- never when nothing changed since the last session (no new trigger, no new break, the pipeline the same).

**What it is given.** Every standing trigger no earlier session answered (by fingerprint): the queue blocked; a gap dead
past half an hour, or parked within `parked_within_hours` (48) for a kind no program resumes (`defect`, `kill-rule`, or
none said), unless another gap carries its branch on or the park is `deferred` or `cancelled` (its kind, or the
coordinator's `deferred: true` or `cancelled: true`), or an old park classified `unknown` whatever its age; a `waits_on`
or `needs` park not cleared in `park_wait_hours` (24, at least 1); a continuing gap whose branch intake could not fetch
(`unfetched`); a `split` park never (each stopped sub-gap raises its own
trigger); a gap past `[manager.stuck_hours]` in its state (`building` by its current visit alone, from its moves, a
lease taken and given back counting as the same visit, since rounds of rebuilding are bounded by the kill rule; every
other state by the sum, state-times' closed visits in `time_in` plus the current one when it has it, else its moves), unless it waits on main, its dependencies, a full pool or a held push; an open, unremedied defect past
`intervention_hours` (12), not the manager's own and not a record of a decision (`operator-decision`, `factory-tuning`,
`factory: false`). With them (`dev/bin/manager.py`): the first gaps' history, reviews, sessions and log tails, the
queue, main's commits, the open interventions, the flakes, the pipeline by state, the velocity record and the knowledge.
While approved gaps wait and nothing merged for 20 minutes, it also carries what holds the merge queue: each lease the
merge-queue block holds (item, run, taken, renewed, expires, the item's state, whether the run's process is alive, from
the engine's run record) and queue-when's inputs read now (`queue_holder()`).
It answers per trigger what it did or why it left it; a trigger it did not answer comes back in the next session.
Situations of the earlier one-trigger watch (a `print`, no `prints`) count as looked at once handled or failed; one
still `raised` is closed `superseded`, never run, and its trigger, if it still stands, goes to the next session. Each
situation's id ends in a random suffix, so two raised in one second are two items.

**The tools** (`dev/bin/manage.py`, at most `most_actions` (8, held to 1..12) calls a session, each through its own checks). Directly:
`continue GAP`, `reapprove GAP --why` (the failed tests run again on main where they failed, the checkout for the
queue's or a container for the fast suites', browser tests with Playwright (`rerun`, a skip not a pass), and must fail
there too), `flake TEST`, `file-gap`, `remedy INTERVENTION` (a queue one only once main is clean and pushed), `propose`, `ask`. Asked
in the inbox: `close GAP`, `park GAP`, `pool ROLE N`, `change --what` (dev/model, the settings, anything touching
origin). Every call is an `intervention.recorded` with a class and `by: pipeline-manager`. By hand, as the coordinator:
`python3 dev/bin/manage.py continue gap/NAME --why ...`. Pause it with `[manager] open = 0` in `factory.local.toml`.

**The routine review.** Each session's record has queue wait, minutes per merge and per batch, batch size and bisected
batches, time in state, first-pass yield, merges per hour, each goal against its setpoint and the binding constraint, and
the answers to its earlier questions. A scheduled session either `propose`s a change (a gap with a definition, one
open at a time) or `ask`s the researcher how to speed up the merge pipeline (one open at a time:
a question is open until answered, so one being researched or given up on (`dead`) holds the next), or says why neither.
Both check what is open and write under one lock (`run/one-open.lock`), so a session's and the coordinator's at once
never both get past the rule.
The measures `manager-triggers-per-session` and `manager-actions-per-session` say how much each session takes on.

**A definition's named measurement** (`measure-runs GAP --runs N --tests "T" [--load K]`, `dev/bin/runs.py`). Use it
when a definition's acceptance is a repeated or loaded run that its sessions cannot make, and the gap is parked or
built with "Where it stopped" saying the measurement was not run here. A gap whose plan marked a done item
`needs: measure` (*Plans, research and what the factory knows*) carries the request as `measure_runs_wanted`: the
tests to give `--tests`. One marked `needs: owner` was parked at plan time, before any build, and waits for the
owner's `gap.need-met`. The velocity record carries `env-parks` beside `first-pass-yield`: the parks such items caused
in 14 days, at plan time (`env_parked_at`) and by a review that parked a marked gap for a need. Such a review is left
out of `first-pass-yield`, since the failure was the container's, not the implementor's. The first user is gap/lease-shutdown-race:
`--runs 30 --load 4 --tests "-n 8 tests/test_leases.py"`. It makes N runs (1-50) of the selection T on the branch
head, in a clone of the drop at it. T is test files or ids under `tests/` and at most one `-n` of 1-8. Each run is
`[suites] measure`, under `scripts/suite_watch.py`, in the shared suite slot and a suite container. With `--load`, K
busy processes (1-8) of `[suites] load` run beside the runs under a watchdog of their own. Their process group, and
their container, are stopped when the runs end normally, on an error or on a SIGTERM. The load also ends on its own:
manage.py touches a heartbeat file in the clone every few seconds, and each busy process stops once that file is gone
or has not changed for `[suites] load_stale_s` (30 s, at most 300). So if manage.py is SIGKILLed, the load is gone
within about that time. A run during which the load had ended counts as a failure. The load's container has the role
`measure-load`, which other processes' container sweeps (`agents.sweep`) leave for 12 h (`runs.WALL`) plus 10 min, not
a suite's 70 min. A measurement starts no run that would end past those 12 h, judged by its longest run so far; each
run not started counts as a failure. A run still going at those 12 h (one that hangs) is stopped there, its process
group and container with it, and counts as a failure. Each run's own container is a suite's, so a single run past
70 min may be swept by another process and then counts as a failure. Each cap is checked when the call
is parsed and again when it runs. A run passes only on exit 0 with the watchdog's last line saying pytest's rc 0 and
nothing killed. A killed run counts as a failure, and so does one whose log or watchdog line cannot be read. A parked
gap is measured only if it was parked for `defect`, or for `needs` with a `parked_until` action that names a
measurement (a word starting "measure"), was not resumed, and no other live gap holds its branch: a deferred,
cancelled or kill-rule park is refused, and so is a need for anything else (an approval, say). The counts (passed and
failed of N, the head, each run's rc, and the log tail of each failed run) are appended to the gap's `measured_runs`.
They are also said in its `findings`, which both briefs carry. If every run passed, the gap goes to `built` at the same
head, for review. If any failed, it goes to `fix`, with the first failing run's tail as its input (one failed gate).
Before the gap is moved, its state, its branch and the park checks are read again, under the continue lock that
`continue` and the park resumer take. If the gap left parked or built while the runs ran, its branch moved, or it is no
longer one a measurement may move (resumed meanwhile, say), it keeps its state, the counts are recorded alone
(`gap.measured`) and the call is refused. The engine's takes share no lock, so a reviewer that takes a built gap
between the second read and the write is not seen: that window is one record read wide.
Who runs it: the coordinator by hand runs it at once, in their own process. The pipeline manager's call is never run
inside its block (which ends within 1 h, before a 30-run loaded measurement could): it is checked (the caps, the park
checks) and asked in the inbox as the action `manager-measure`. Once approved, ergostat runs that action's command,
`manage.py measure-runs --detach`, in whichever process carries out the approval (an `actions --approve` terminal,
a web request, the engine). That command checks the call again and starts the measurement in a session of its own
(no terminal, not in the approver's process group, its output in `run/measure/*-detached.txt`), then returns at once.
The action is recorded `ran` with the measurement's pid and log. Its timeout is 2 min. So the approver does not wait,
and a Ctrl-C to the approver, or the web server exiting, does not reach the measurement. The measurement then runs
as a plain `measure-runs` with `--asked-as` set to the action's id. It is recorded as by `pipeline-manager`, its asker,
with `asked_as` naming the action. It records its own end: the counts and the move as above, or, when it is refused or
fails, an intervention saying why (`ended`). A SIGTERM to its pid (or a Ctrl-C) stops its run and load, records an
intervention `ended: stopped` with `asked_as`, and exits 143. Only a SIGKILL to it leaves its end unrecorded (its
load still ends by its heartbeat). It is bounded by
`runs.WALL`. `runs.measure` refuses to run off the main thread, because only there can SIGALRM bound a run. A
refusal at the start (the gap no longer measurable) fails the action, and no run is made.

**Whoever parks a gap says what it waits for, and it is resumed when that clears** (`dev/bin/parks.py`). Every park
records `parked_for`, a kind: `defect` (its own work is wrong), `waits_on` (a gap, or commits, named in
`parked_until`), `needs` (an action named for someone), `kill-rule` (rounds, hours or attempts ran out: the implementor,
the reviewer, the queue, triage, the plan lint, dead letters), `deferred` (the manager's park, once the coordinator
approved it), `cancelled` (the removed plan review's, in older records), `split` (split-watch: the stopped sub-gaps). The reviewer's park verdict
gives its kind and condition; one naming nothing checkable is a `defect`. The block `park-resume` (every 5 minutes, no
AI) resumes `waits_on` once the gap's work is on main as pushed (its merge on the checkout's `origin/main`; a merge not
pushed has not cleared), through its continuation (`resumed_as`, followed) when it was continued, or once the commits
are on pushed main; `needs` once
`ergostat event --add gap.need-met --item gap/NAME --data '{"need_met": "what was done"}'` is recorded, and `split`
once each stopped sub-gap is resumed or closed (the split gap back to split, the continuations its children). A resume
is a gap that `continues` the branch, as by hand, and a `gap.resumed` on the parked gap saying what cleared (a
continue by hand records one too, so a park is resumed once). `defect` and `kill-rule` are the manager's. Each pass
first classifies, once, the parks from before kinds (`classified_by: park-classify`): `kill-rule` by who parked it,
`waits_on` the one other gap whose merge its branch carries (one merge in `base..branch`; whether main already has that
gap's work is not checked, and if it has, the wait clears on the next pass), else `unknown` (the manager's);
a `deferred` or `cancelled` one, one the plan review or the manager parked, or one continued already (`resumed_as`:
its work goes on in the continuation) is left alone, and an `unknown` one continued is not raised past its age. Expect the first
session after this lands to carry many `parked` triggers, one for each old park classified `unknown` (a reviewer's
included), once; after that, only new ones. An old park classified `waits_on` keeps its first `parked_at`, so one whose
gap is not on pushed main raises `waiting` at once too (past `park_wait_hours`). Measures:
`measure.py parks|resumes|parked-hours KIND`; the Items page shows `parked_for`.

## Upgrade and revert

Each green merge opens an `upgrade` item; the upgrader installs it into `~/ergostat-live/<sha>` and checks the model
with its own code, then asks for `switch-instance`. Only the newest waits: the switcher (`dev/bin/drain.py`, every
minute) withdraws a request for a version older than one waiting, or than the one running (its action denied by the
switcher, saying which version supersedes it); no request is withdrawn while a switch runs. Approving it (the inbox,
as above; or standing, with `gate: auto` on the action in the instance's model) switches at once, in the switcher's
next minute: it writes `run/switch.json`, says `upgrade.switch-begun`, and starts the switch in a process of its own.
The switch stops the engine, points `current` at the new version, starts it, and checks its health for two minutes (a
pass, the sensors reading, the record read, the merge queue in the model); unhealthy, it goes back to the previous
version by itself. Either way it removes `run/switch.json`. A switch that ends with no outcome recorded (it failed
before stopping the engine, as with a version no longer installed), or whose flag is still there 30 minutes on, is
recorded `failed`, with an intervention, and never begun again.

**What a switch does to running work: nothing.** The factory's model has `runs: outlive_engine` on, so every run
(an implementor's session, a review, the merge queue's suites) is held by a keeper of its own, not by the engine. A
switch, and a revert, stop the engine alone (`ergostat run --stop`, never `--runs`): each run under way carries on
under the version it started with (its process, its `$ERGOSTAT_CMD`, the modules it has loaded), its lease kept with
its fence, and writes what it says to its journal while no engine is up; the engine the switch starts takes it up
from its journal (SPEC section 9.1, *Runs taken up again*), every line recorded once, and ends it as if it had been
there: its `agent.ran`, its lease's ack or nack, no attempt lost. Nothing waits for the runs, and none is stopped or
given back. The version switched from is touched as it stops running, so `cleanup.py` keeps its folder `[resources]
session_keep_hours` (24) on, past any run's timeout, for the runs that still use it. What a run starts after the switch
from the instance's `dev/` (a module imported late, another script) is the new version's: the instance's model is
placed whole. A run of a journal format the new engine cannot read (`runs/RUN.json`'s `journal`) is refused and named
(`run.refused`), its keeper told to stop it and its lease released uncounted, so its item is taken again.
The first switch onto this version is still the draining switcher's (the version before runs it): its live.py marks
the switch under way in `run/drain.json` (`switch_started`) and removes it when the switch ends, so the new switcher
reads that mark as its own `run/switch.json` (a switch under way, failed only 30 minutes on), not as a switch that
recorded nothing.

The switcher reads the goal `upgrades-switched-to` (`in:`) rather than naming it (`goal:`): a goal named would command
it, and a commanded block leaves its `every:` (`ergostat check` says `schedule-removed`); the pipeline watch reads
`no-stuck-gaps` and `merge-pipeline-flowing` the same way. The `in:` is drawing only: neither program reads the goal's
value, as each finds what the goal measures itself. `status.py` says what the newest switch waits for, or since when it
has been switching. By hand:

```sh
python3 dev/bin/live.py switch <sha>           # the same, in the foreground
python3 dev/bin/live.py revert                 # back to ~/ergostat-live/previous
```

## Try it without AI or a push

`tests/test_factory.py` takes a fake gap through the implementor, the reviewer and the queue on a fixture repository
with the stand-ins (`[ai] mode = "standin"`). A whole instance on a fixture: point `factory.local.toml`'s `[paths]` at a
scratch repository, `[ai] mode = "standin"`, and trivial `[suites]` (`unit = "echo 1 passed"`).
