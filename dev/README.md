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

## Submit a gap

A GAPS.md entry is taken in by itself (`gap.found`, open). It is **ready** once it has a definition of done:

```sh
mkdir -p run/defs && $EDITOR run/defs/<branch>.md        # the gap's `branch` field (ergostat item gap/NAME)
```

(or `dev/records/<branch>.md` on main or on its branch: the gaps' working records, out of `docs/`; the old
`docs/roadmap/overnight/<branch>.md` is still read for a branch begun before the move, the new path first). A gap that is not in GAPS.md is asked for as an
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
`tool-denials-unknown` counts), and a branch that comes back without main in it (say, the merge aborted), or with the
merge unfinished, is refused before the drop's `factory/NAME` moves. The fast suites run
after: ruff and `[suites] build`, each under the watchdog in a suite container of the agent image and the suite slot.
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
"Depends on" table column in GAPS.md. It is built only once each is merged (a parked one holds it, with `blocked_reason`); the implementor takes the unblocked first,
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
made a definition by the lint sweep; each sub-gap's plan review is given it (`(none)` for a gap with no parent or no
file). Once every sub-gap is merged the join moves the parent to `joined`, never to `merged`, and the **join judge**
(`plan.py join`, the plan reviewer's model and session cap, `[ai] join_judge_*`) reads, in a read-only clone of main,
the parent's entry, its coverage, and each sub-gap's definition and last review (anything unreadable shown as
`(missing: why)`). `covered` merges the parent, its verdict, reasons and `judged_at` recorded. `short` requests a new
sub-gap `<parent-branch>-join-<n>` (its entry the parent's title and the points not built), adds those points to the
coverage file as `(by: that name)`, and only then splits the parent again, so the join waits for the new sub-gap. At
most `plan.MOST_SHORT` = 2 short rounds: the third `short` parks the parent with what is still missing. A verdict that
cannot be read or a failed session leaves it in `joined` (the run fails under its lease); a budget refusal waits.
The judge's verdicts are measured by `split-quality` (of parents first judged in 14 days, the share whose first
verdict, in record order, was `covered`), `split-joins` (parents judged at least once, whole record) and
`split-overhead` (the median, over parents merged in 14 days, of the parent's and its children's AI cost, a parked
sub-gap's and its continuation's both, over the median cost of merged unsplit gaps of the children's size class; a
parent unpriced, with a child unmerged, unsized or unpriced, or with no unsplit gap of its class is left out and
named), and `split-quality ≥ 0.7` over at least 5 joins is the condition gap/plan-by-size gates XL auto-split on.
The plan review is advice, never a gate (`[plan] review`: `sample`, 1 in `sample_every` = 3, `all` or `off`;
`dev/bin/planreview.py`): in a read-only clone of main with the task graph, it reads a marked gap's definition; its
findings are appended to the definition as notes the implementor answers, and recorded by class on
`review/<branch>-plan` for the knowledge loop. "This should not be built" is only asked of you (`park-gap`, in the
inbox). `plan-review-agreement` and `plan-{flagged,clean}-{fix-rounds,parks}` say what the stage is worth. A definition you write yourself skips all of this. Every brief carries the factory's knowledge (`dev/knowledge/README.md`), and records which entries.

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
too: a merge reverted on main (`ergostat event --add gap.reverted --item gap/NAME --data '{"reverted": true}'`),
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
which. `python3 dev/bin/resources.py line` (and `status.py`) prints it all on one line.

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

**The suites in the queue:** ruff, then unit and browser at once, then demo_check alone (under the other two's load
its pages drew nothing). The first of them to fail is the one reported, and it stops the rest: a unit failure kills
the browser run still going (and the other way round), which is recorded `stopped_by` it, its own result not judged.

**The quarantine.** `tests/quarantine.txt` (`test id | who | when | why` a line) names tests the queue's, flake
triage's and the implementor's suites deselect (`--deselect`, unit and browser). The list is read from main (the
queue's and triage's `pre`, the drop's main for the implementor), never from the branch under test: a branch that adds
its own failing test to the list is still red in the queue, and its line takes effect only once it is on main. (The
implementor's fast suites, which land nothing, also deselect the work's own lines, unrun: a branch that adds the list,
or a line to it, is not held up on its own machine by a test it quarantines; the queue still runs it.) After each unit run
(and each triage rerun) the quarantined tests run once more, with `-rA` (the queue and implementor: `[suites] alone`;
triage: `rerun`), never blocking. Each result is said on `flake/<test>` (`flake.measured`: `quarantined`, `last_run`,
`last_run_log`), read from that run's whole log: `pass` only on the test's own PASSED line with no FAILED or ERROR
line, `fail` on either, `unknown` otherwise (skipped, not collected, a run that never started or left no log). A
skip is never a pass. A flake item still marked `quarantined` whose test is no longer on main's list is marked
released (`quarantined: false`) at the next such run. When a queue failure names only quarantined tests, triage
sends the gap back to the queue with no flake seen and no retry spent. Tests are added and released by hand, by
a change to main's list (which a reviewer reads in the diff); nothing in this code quarantines or releases one.

**Batches.** The queue merges up to `batch` approved gaps onto main in turn (in rank order) and runs the suites once.
The batch is 1 to start (`[pools] batch = 1`: one gap a run, the queue as it always was). A green batch asks for one
push, of its last merge, so one approval lands the batch, and a denial sends every gap of it back. A red batch is
bisected (the suites again on the first half of the merges, and so on) to the first merge that fails; that gap goes to
flake triage with its failures, the merges before it land, and those after it are merged again and run once more.
When the red run named its failing tests (`FAILED`/`ERROR` lines), those are first run alone, serially
(`[suites] rerun`, `-rA`), on the whole red tree. **A flake lands:** when it named 1 to 3 tests, none in
`tests/test_page_polling.py`, and its failed suite skipped none, they are run alone there twice; each passing both
times (a PASSED line, rc 0), the suites the red run did not finish (stopped by its failure, or never reached) run, and
green there the batch lands with no bisect, each test a flake seen (`flake.seen` on `flake/<test>`: the run, the suite,
`passed_alone`, the log; `excused` in each gap's `suites_queue`). Only if one fails alone does each bisecting step run only those:
red when one of them fails, green only when the run passes and each says PASSED; a step that cannot tell (a test not
found on that prefix, a run that never started) runs every suite instead. A failure that shows only in the full run
(order, pollution, load), one the rerun cannot tell, and one naming no test (ruff, demo_check, a collection error, a
killed run) are bisected with every suite, as before. A green on the named tests alone never lands anything: the
merges before the failing one are merged again with those after it, and the lot lands only on a full green run of
that very tree; the failing gap's `pre` is then main's head before them, so its triage runs it on main alone. Each
failing merge costs at most `2 + 2 ceil(log2 m)` runs (the red run, the rerun on its tree, and each step, two when a
named run cannot tell), most of them its failing tests rather than the suites. A
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
code, not the files it names. The real merges then make the batch's first run: when they all succeed, their tree must
be the dry-merged one, or the run stops before any suite. A real merge that conflicts (one merged again after
bisecting, or one where the dry merge was clean) is undone and sent back as a failed gate, and the rest go on to the
suites, so what is tested is still what lands. If git cannot make a dry merge at all, the run fails there: gaps
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
gap. A stall during a bisect throws away a green prefix that run already found. Gaps that run already sent on (to
triage, or back for a conflict) keep that outcome, though `stalled_batch` still lists them. A stall
with the gap alone in its batch is counted on it (`stalls`). The clocks start once `[suites] slot` (triage's suites)
is held, so a wait for the slot is never a stall. Its third (`STALLS_MOST` in fac.py) is no longer given
back: it goes to triage as `queue-failed`, the stalled test as its failed test. In triage, a stalled rerun gets the
same fields and `stalls`, and its lease is given back the same way until the gap's third stall. Then the failure is
the branch's: back to fix, or parked by the kill rule.

To raise it: approve the pool tuner's `raise-pool` (role `batch`; it asks while the queue wait is over its goal,
`queue-wait-short`), or by hand, from the instance, `python3 dev/bin/pools.py set batch 2 "why"` (it is kept in
`run/pools.json`, which wins over `[pools] batch`; `set batch 1` goes back). At most `[pools] batch_max` (8, never
past 32). A run starts no suite run once `[pools] batch_minutes` (120; a value of 0 or less, over 150 or NaN is refused,
and the queue takes no gap) have passed since it began, the wait for the lock and a quiet machine and the dry merges
included: it stops bisecting, the prefix a full green run proved lands, and the gaps not yet settled go back to
`approved` uncounted, for the next run. A run that settled none of its batch leaves the next one half as many
(`cap` in `run/queue.json`, cleared by the first run that settles one), down to a batch of 1, which is one suite run.
So, whatever the batch, the block's 3 hour timeout is reached only by a suite run begun inside the allowance that
lasts past it (over 60 minutes at 120, 30 at 150); nothing here bounds a suite run that hangs. Each run's
`queue_runs` entry says how many it `tried`, `landed` and `given_back`. `merges-per-hour` (gaps merged over the hours
of every queue run, each run's whole length once) measures what it buys. If the push fails, or a merge cannot be undone, the queue stops and records an intervention
(`ergostat item --kind intervention --state open`); it goes on once you record that intervention remedied:
`ergostat event --add intervention.remedied --item intervention/queue-... --data '{"remedy": "..."}'`.

A gap is never left a dead letter: a run that fails on its last attempt parks the gap with where it stopped, and the
`dead-letters` block parks any that a killed run left behind. Every container the factory starts is named
`ergostat-factory-*`, killed when its run ends or is stopped, and swept by `main-watch` once past its time.

## Time in each state

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

A gap's record rolled up (after 7 days by default, `ergostat/rollup.py`) starts with a snapshot: its moves are kept
there, so `time_in` and the loop are counted as before, but the events carrying the gate times are in the archive. The
gates start from the snapshot's own (what the gap's last `gap.timed` before the roll-up said), and only the events
after it are added, so a later event or a lost bookmark recounts them the same; a merge in the snapshot still waiting
for its push is carried over from the snapshot's state. A gap rolled up before it was ever timed (the first run on an
old record) has its gates unknown (`null`), counted in no gate's measure rather than as zero, and stays so even if
it is built again (a sum of only its later rounds would be an undercount read as a whole); gate events between its
last `gap.timed` and the roll-up (only if the timer was stopped that long) are not counted.

The measures (`dev/model/times.yaml`, the system `times`) are `in-STATE-hours`, `loop-hours`, `loop-rounds` and
`gate-GATE-minutes`, each the median and with `-p90` the 90th percentile (nearest rank) over the last 14 days, of the
gaps that left the state, ended the loop or passed the gate in the window, not only the merged ones; 0 with none.
Each has a goal (`hold:`) to set; the shipped ones are first guesses, and `python3 dev/bin/times.py setpoints` in the
instance's folder sets each to today's reading (one with nothing in the window keeps its own). `status.py` prints them
as a table, the waiting states first (time spent waiting on someone else, the cheapest to remove: open and replan for
the planner, planned for the plan review, split for its sub-gaps, ready and fix for the implementor, built for the
reviewer, approved for the queue, queue-failed for triage, dead for a park), then the working ones, where a run holds
the gap (leased: the planner's, the plan review's and triage's whole run and the others' start, the queue's wait for
its lock with it; building; in-review; queued: the queue's run from its `gap.queued`, said once it holds its lock, the
merge and the suites), the loop and the gates, with how
many gaps are in each state now and the oldest of them.

## Record an intervention

Each time you step in by hand, say so: it is evidence of a loop the factory lacks. One the factory itself caused (its
`class` one of those under the pools, above, or `"factory": true`) counts against the pools' risk.

```sh
ergostat event --add intervention.recorded --item intervention/2026-11-20-unstick-alpha \
  --data '{"reason": "the worktree was left mid-rebase", "class": "worktree", "recorded_at": 1795160000}'
ergostat event --add intervention.remedied --item intervention/2026-11-20-unstick-alpha --data '{"remedy": "gap/..."}'
```

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
  old, no merge in that long while approved gaps have waited as long, the interlock holding the queue that long, or the
  same test failing on two main commits (at once; only while those `main-broken` interventions are unremedied). The
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
trigger); a gap past `[manager.stuck_hours]` in its state (from state-times' `time_in` when it has it,
else its moves), unless it waits on main, its dependencies, a full pool or a held push; an open, unremedied defect past
`intervention_hours` (12), not the manager's own and not a record of a decision (`operator-decision`, `factory-tuning`,
`factory: false`). With them (`dev/bin/manager.py`): the first gaps' history, reviews, sessions and log tails, the
queue, main's commits, the open interventions, the flakes, the pipeline by state, the velocity record and the knowledge.
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

**Whoever parks a gap says what it waits for, and it is resumed when that clears** (`dev/bin/parks.py`). Every park
records `parked_for`, a kind: `defect` (its own work is wrong), `waits_on` (a gap, or commits, named in
`parked_until`), `needs` (an action named for someone), `kill-rule` (rounds, hours or attempts ran out: the implementor,
the reviewer, the queue, triage, the plan lint, dead letters), `deferred` (the manager's park, once the coordinator
approved it), `cancelled` (the plan review's), `split` (split-watch: the stopped sub-gaps). The reviewer's park verdict
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
switcher, saying which version supersedes it), except that a drain under way is not withdrawn for a newer version
only installed: the drain goes on to its switch and the newer one waits, its request open; a newer one approved takes
the drain over, keeping its start. Approving it (the inbox, as above; or standing, with `gate: auto` on the
action in the instance's model) does not switch at once: the switch waits for a quiet moment (at most `[upgrade]
quiet_runs` AI runs under way) or, at the latest, the daily window (`[upgrade] daily_at`, 04:00 local) passing; then it
drains: `run/drain.json` is written and the AI blocks take no new item (each run gives its item back uncounted) while
the runs under way finish, for at most `[upgrade] drain_minutes` (45); the runs still going then are given back
uncounted (not a failure of their gaps) and stopped with the engine. The switch then stops the engine, points `current`
at the new version, starts it, and checks its health for two minutes (a pass, the sensors reading, the record read, the
merge queue in the model); unhealthy, it goes back to the previous version by itself. Either way it removes
`run/drain.json`. A switch that ends with no outcome recorded (it failed before stopping the engine, as with a version
no longer installed), or whose flag is still there 30 minutes on, is recorded `failed`, with an intervention, and
never begun again. A drain never switches in the step that began it, and no request is withdrawn while a switch
runs. The goal `drains-within-bound` holds the minutes past `[upgrade] drain_minutes` (`drain.py overrun`) to 2;
`drain-minutes` stops counting once the switch begins. The switcher reads the goal (`in:`) rather than naming it
(`goal:`): a goal named would command it, and a commanded block leaves its `every:` (`ergostat check` says
`schedule-removed`); the pipeline watch reads `no-stuck-gaps` and `merge-pipeline-flowing` the same way. The `in:`
is drawing only: neither program reads the goal's value, as each finds what the goal measures itself. The groomer and
the plan review start no session while `run/drain.json` is there. `status.py` says what the newest switch waits for, or how long it has drained. By hand:

```sh
python3 dev/bin/live.py switch <sha>           # the same, in the foreground
python3 dev/bin/live.py revert                 # back to ~/ergostat-live/previous
```

## Try it without AI or a push

`tests/test_factory.py` takes a fake gap through the implementor, the reviewer and the queue on a fixture repository
with the stand-ins (`[ai] mode = "standin"`). A whole instance on a fixture: point `factory.local.toml`'s `[paths]` at a
scratch repository, `[ai] mode = "standin"`, and trivial `[suites]` (`unit = "echo 1 passed"`).
