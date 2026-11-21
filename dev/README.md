# The factory: ergostat developing itself

`ergostat.yaml` at the repository's root is the factory that develops ergostat: gaps (from `docs/GAPS.md`, or asked
for) defined first, built by an AI implementor in their own worktrees, judged by a disagreeable AI reviewer, landed one
at a time by a merge queue behind the four suites, and the new main installed and switched to, with a revert. Its
programs, prompts and model files are here, in `dev/`. The plan it automates is
`docs/roadmap/overnight-2026-11-19.md`; what it is meant to do is `docs/roadmap/overnight/factory.md`.

It ships **off**: the implementor takes nothing until you open the intake.

## Where things are

| | |
|---|---|
| `~/ergostat` | the checkout the queue merges into, runs the suites in, and pushes from. Never the instance's code |
| `~/ergostat-live/drop.git` | the factory's own bare repository: each gap's work, on `factory/<branch>`, as the sessions bundled it back; the queue fetches the reviewed commit from it |
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
hold a slot (`[suites] slot`), the queue's lock being its own (the load interlock).

## Submit a gap

A GAPS.md entry is taken in by itself (`gap.found`, open). It is **ready** once it has a definition of done:

```sh
mkdir -p run/defs && $EDITOR run/defs/<branch>.md        # the gap's `branch` field (ergostat item gap/NAME)
```

(or `docs/roadmap/overnight/<branch>.md` on main or on its branch). A gap that is not in GAPS.md is asked for as an
event, its definition a file in `run/defs/` (a branch is lowercase words and dashes; nothing else is taken):

```sh
ergostat event --add gap.requested --item gap/my-change \
  --data '{"title": "My change", "source": "request", "branch": "my-change", "definition": "run/defs/my-change.md"}'
```

**Continuing a parked branch.** Ask for a new gap that `continues` it (`NAME` or `factory/NAME`, a branch of the
checkout or already in the drop; it is then the gap's branch, and its own `docs/roadmap/overnight/NAME.md` is the
definition, so add a "Where it stopped" section there rather than writing a new one):

```sh
ergostat event --add gap.requested --item gap/warm2-again \
  --data '{"title": "Warm 2, continued", "source": "request", "continues": "warm2"}'
```

A branch carried on under a new name (its first commit is another name's definition, e.g. `warm.md` on `warm2`) names
that file as its definition, `"definition": "factory/warm2:docs/roadmap/overnight/warm.md"`: the implementor commits no
copy, the parked note is appended to it, and the reviewer's gate 1 checks that file is the branch's first commit.

The intake fetches it into the drop as `factory/NAME` (never over a `factory/NAME` already there, and refusing a name
that is not lowercase words and dashes). It is not taken while another gap on the same branch is anywhere but parked or
merged (open, building, built, approved, in the queue...): that gap's reviewed work would be mixed with the new one's;
the intake says so on stderr and takes it once the other stops (of two requests to continue it asked at once, the first
read is taken, the other waits). Each run fetches its session's work to a side ref of its own
(`refs/incoming/<run>/factory/NAME`). Before each implementor run on a branch behind main, implement.py merges main in
itself: a clean merge is committed by the factory; a conflicted one is handed to the session with the files in its brief
(it may run `git merge`, `git add`, `git commit`, `git status`), and a branch that comes back without main in it (say,
the merge aborted), or with the merge unfinished, is refused before the drop's `factory/NAME` moves. The fast suites run
after. The reviewer's gate 1 takes the branch's own first commit (its first-parent line) as the definition (the file the
gap's `definition` names, for a continued gap), and for a continued branch also requires it to hold the main
implement.py merged at its build (`built_main` on `gap.built`; current main when that is missing). Main moving on
between build and review is not a failed gate: the merge queue merges the branch into the main of its moment and runs
the suites again. Its reviews are numbered past the branch's earlier ones (`review/NAME-3` after a parked gap's `-1` and
`-2`), and run logs are named by when they ran.

**Dependencies.** A gap waits on others named by `depends-on: [name, ...]` in its definition (the template is
`dev/prompts/definition.md`), `"depends_on": ["gap/..."]` in its request, or `after `name``, `needs `name` first` and a
"Depends on" table column in GAPS.md. It is built only once each is merged (a parked one holds it, with `blocked_reason`); the implementor takes the unblocked first,
the critical first. A name that is no gap, or a link that would close a cycle, is refused and said (the goal
`dependencies-sound`); a gap waiting on a parked one says so (`blocked_reason`). The Items page's Graph and Timeline
draw the tree; `python3 dev/bin/deps.py` prints it as mermaid.

Then: the implementor commits the definition first and builds; the reviewer approves, sends it back (`fix`, with its
findings) or parks it; the sixth failed gate (`[gates] kill_after`) parks it with where it stopped; the queue lands it. `ergostat item
gap/NAME` shows each round, its reviews, the context each session was given and what it cost.

**The kill rule** is in `[gates]` (dev/factory.toml): `kill_after = 6` failed gates (fix verdicts, queue conflicts, real
failures in the queue), `build_failures = 6` failed fast-suite runs of the implementor's, or `build_hours = 12` of
building over its rounds, park a gap; within a run the implementor gets `[ai] suite_fix_rounds = 2` sessions to make
its failing fast suites pass.

**A failure on main is not the gap's.** When the implementor's fast suites fail and name tests, `dev/bin/onmain.py`
runs those tests again alone on the branch (the `[suites] alone` command, in the same kind of suite container, in the
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
```

A GAPS.md entry whose head (its opening parenthetical, or the clause after its colon) begins with "done" or
"superseded by" is never found as open, and one the record holds not yet started is closed.

## Plans, research and what the factory knows

A gap with no definition is **planned** (`dev/bin/plan.py`), once you open planning
(`ergostat sensor planning-open.main --read 1`): the planner reads the code, docs and knowledge in a read-only clone of
main and writes its definition of done to `run/plans/<branch>.md` (acceptance tests, a budget, the review lessons that
apply as risks, the files to touch); a gap too large for one branch becomes sub-gaps with `depends-on` among them, the
gap waiting in `split` until each is merged. A short plan review (the plan and the lessons only) approves it into
`run/defs/` (the gap is ready) or sends it back; a second failure parks it. A definition you write yourself skips all
of this. Every brief carries the factory's knowledge (`dev/knowledge/README.md`), and records which entries.

```sh
python3 dev/bin/status.py                                   # one screen: in flight, blocked, failed, queue, spend
python3 dev/bin/request.py "My change" --depends-on other-gap [--definition my-def.md]
python3 dev/bin/ask.py "How does the queue decide a flake?"  # answered in run/research/, summary on the item
python3 dev/bin/lesson.py add "Title" --check "the check"   # or: retire N "why"; proposals wait in the inbox
```

**Size classes.** Each plan's `## Size budget` holds `size: S|M|L|XL (confidence: low|medium|high)`, a class of the
net lines that will merge outside `tests/` and `docs/`, `dev/` counted: S 50 or fewer (a net removal is S), M 51-150,
L 151-400, XL over 400. A definition without it, or with another class or confidence, is sent back like any other
planner problem, never given a default; each sub-gap of a split has its own. A replan replaces the size, and clears the
lines of any earlier merge. At each merge the queue counts the net lines from main before it to the merged head and
records `merged_lines` on `gap.merged`; when that count cannot be read the merge stands, `merged_lines` is null and
`merged_lines_error` says why (a merge again always writes both, so no older count survives).
`measure.py size-accuracy` is, over 14 days by each gap's latest merge, the share of merged gaps the planner sized
whose lines fell inside their class; `size-accuracy-high` is the same for high-confidence gaps. A sized gap with no
count is left out of the share (never a hit) and named on stderr; with nothing measurable either one has no value
(exit 1), and `-high` too when only low or medium gaps can be measured. **Not covered:** gaps whose definitions you
wrote (no planner, no size), and split parents (they merge nothing; a split clears an earlier size). The groomer's
own `size` (`gap.groomed`) carries no confidence and is never measured, but a groomer that regrades a gap after its
plan replaces the planner's class, and that regrade is then what is scored.

## The pools: one at a time, raised on good results

One implementor and one reviewer to start (`run/pools.json`; the blocks' `pool:` is only the most, 4 and 2, in
`[pools]`). After three gaps in a row are approved within one fix round and none was reverted after merging, the pool
tuner asks for `raise-pool` (the implementor first), held in the inbox; a park, a second fix round or a reverted merge
lowers the pools by one at once. Say a merge was reverted on main with
`ergostat event --add gap.reverted --item gap/NAME --data '{"reverted": true}'`. By hand:
`python3 dev/bin/pools.py set implementor 2 "why"`.

## The machine's resources: a cap on the pools

The machine is measured every 30 s (`dev/bin/resources.py`, `dev/model/resources.yaml`): the host's CPU, memory,
disk and threads, the Docker VM's limits and use, and each factory container's CPU and memory, kept on its gap
(`resources`: each session's and suite's peak and mean) and in `run/resources/sessions.jsonl`. The setpoints are the
goals in `dev/model/resources.yaml` (change them there). `session-headroom` is how many more sessions fit, from the
measured use of a session and its suite. **The effective pool is `min(pool, busy + headroom)`**: the pool stock is
the risk target (the tuner's, or whatever sets it), the headroom a separate cap in the gates and in each run
(`pools.my_turn`); it only ever lowers what the pool allows. A resource past its goal, or a headroom not known, holds
new sessions (`machine-full`). `disk-cleanup` removes session folders and installs (never current or previous) older
than `[resources] session_keep_hours`, by the factory's own names only: `python3 dev/bin/cleanup.py --dry-run` says
which. `python3 dev/bin/resources.py line` (and `status.py`) prints it all on one line.

## Approve the push

A green merge asks for `push-main` (exactly that commit to origin's main), held for you:

```sh
ergostat inbox                                  # the push and the switch wait here
ergostat inbox action/<id> --approve --as coordinator
```

One merge waits for its push at a time. If you deny the push, the queue undoes that merge (`git reset --keep`) and
sends the gap back. If the push fails, or a merge cannot be undone, the queue stops and records an intervention
(`ergostat item --kind intervention --state open`); it goes on once you record that intervention remedied:
`ergostat event --add intervention.remedied --item intervention/queue-... --data '{"remedy": "..."}'`.

A gap is never left a dead letter: a run that fails on its last attempt parks the gap with where it stopped, and the
`dead-letters` block parks any that a killed run left behind. Every container the factory starts is named
`ergostat-factory-*`, killed when its run ends or is stopped, and swept by `main-watch` once past its time.

## Record an intervention

Each time you step in by hand, say so: it is evidence of a loop the factory lacks.

```sh
ergostat event --add intervention.recorded --item intervention/2026-11-20-unstick-alpha \
  --data '{"reason": "the worktree was left mid-rebase", "class": "worktree", "recorded_at": 1795160000}'
ergostat event --add intervention.remedied --item intervention/2026-11-20-unstick-alpha --data '{"remedy": "gap/..."}'
```

## Upgrade and revert

Each green merge opens an `upgrade` item; the upgrader installs it into `~/ergostat-live/<sha>` and checks the model
with its own code, then asks for `switch-instance`. Approving it (the inbox, as above) stops the engine, points
`current` at the new version, starts it, and checks its health for two minutes (a pass, the sensors reading, the record
read, the merge queue in the model); unhealthy, it goes back to the previous version by itself. By hand:

```sh
python3 dev/bin/live.py switch <sha>           # the same, in the foreground
python3 dev/bin/live.py revert                 # back to ~/ergostat-live/previous
```

## Try it without AI or a push

`tests/test_factory.py` takes a fake gap through the implementor, the reviewer and the queue on a fixture repository
with the stand-ins (`[ai] mode = "standin"`). A whole instance on a fixture: point `factory.local.toml`'s `[paths]` at a
scratch repository, `[ai] mode = "standin"`, and trivial `[suites]` (`unit = "echo 1 passed"`).
