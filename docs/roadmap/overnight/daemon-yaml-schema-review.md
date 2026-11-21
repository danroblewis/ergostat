# daemon-yaml-schema-review: a written review of the daemon YAML that answers each of the gap's seven questions with today's form, the alternatives as working before/after models, what each would cost to change, and a recommendation, for the owner to choose from; the schema itself does not change
depends-on: []

## Definition of done

The owner wrote that they are "not sure the YAML is the best yet, and it may change". CLAUDE.md says "build only what the owner asks for", and a schema that people install from main is the owner's to change. So this branch **decides nothing and changes no schema**. It gives the owner what they need to decide: one document with evidence the tests can check, and a list of follow-up gaps sized so that each choice can become a branch. When it is done, all of the following holds.

1. **A new file, `docs/proposals/daemon-yaml.md`**, written for the owner as a human reader (house rule: `docs/` is for people). It follows the style of the other files in `docs/proposals/`. It opens with what the review covers: how the YAML says which process serves a sensor or block and how that process is supervised. It says that the protocol of SPEC §9.7 is out of scope except where an alternative would add to it (point 3, *with:*). It has exactly one `##` section per question in the GAPS entry, in this order and with these headings:
   `## A modifier instead of a kind`, `## Per-sensor arguments`, `## Where shared daemons are declared`, `## The names of inline daemons`, `## Push`, `## The knobs`, `## The word`.
   Each section holds, in this order:
   - **Today.** The current form, stated from the code with a `path:line` citation for each fact. The facts to state include:
     - the seven sensor kinds of `ergostat/spec/compile.py` (around line 485: `run`, `query`, `manual`, `items`, `changes`, `builtin`, `daemon`);
     - `KEYS` and `RESTART` in `ergostat/daemons/config.py`;
     - the derived names `block.NAME` and `sensor.STOCK.SENSOR` (`config.py`, `section`), and where those names are used (`supervise.py` around line 325, `ergostat block NAME --restart`, `logs/daemon-NAME.log`);
     - `push` being an error without a sensor `daemon:`;
     - the default of `restart.backoff`, `[1s, 2m]`, as a two-item list;
     - `heartbeat` defaulting to never;
     - SPEC's statement that "the smaller of `pool` and the daemon's `concurrency`" binds.
   - **At least one paired example.** A `<!-- today: PAIR -->` YAML block and a `<!-- proposed: PAIR -->` YAML block. Each is a complete, small model, and the proposed one is the today one with this section's change applied, and nothing else changed. Where it fits, the pair is built from one of the docs' own examples (for instance job-service's `orders.main` for per-sensor arguments), so the owner sees their own docs rewritten. Questions with several alternatives (where shared daemons are declared: top-level `daemons:` versus an agent's process; the word: `runner`, `server`, `keep-alive`) get one pair per alternative.
   - **What changes.** Which modules change (by path), which SPEC sections change, and whether the protocol gains anything. Any estimate of lines is labelled as an estimate. Also: whether the old form could stay accepted and be reported by `check` as an old spelling, or would be a hard break. Saying this matters because people install from main.
   - **Recommendation.** One of the alternatives, or "keep today's", with its reason drawn from the costs above.
   - **Owner's decision:** with the word `open` after it. The review never states that a decision was made.
2. **A table titled `## Places a change would rewrite`.** It has one row per question, plus one row per alternative where a question has several. Its columns:
   - what changes;
   - a regular expression in backticks, matched line by line;
   - the count.

   The count is the number of YAML places that contain a match: fenced `yaml` blocks in `docs/DAEMONS.md`, `docs/skills/ergostat-author/daemons.md` and `docs/SPEC.md`, plus `*.yaml` files under `examples/`. The text above the table says exactly that scope. The count is today's (re-counted after merging origin/main).
3. **Per-sensor arguments are described accurately.** The section says that a `with:` sent in the read line adds a field to SPEC §9.7's `{"op": "read", ...}` line. The protocol therefore does change, although only by adding a field, which goes against the GAPS entry's "the protocol need not change" (lesson-8: do not repeat a wider claim than the change supports). It also says what a daemon written to today's protocol does with an extra key. That statement comes from reading the docs' own example daemons, with citations. If they differ, it says so for each daemon.
4. **The knobs section records the ceilings (lesson-4).** It says that a non-warm daemon's `concurrency` has a floor of 1 and no maximum today (`config.py`, `whole(..., "concurrency", 1, 10, ...)`), and that only warm daemons are capped (`WARM_MOST` 32, `WARM_ALL` 64). It says whether a non-warm `concurrency` multiplies threads or processes in the engine (answered from `ergostat/daemons/supervise.py` and `work.py`, with citations). For every alternative that merges `concurrency` with `pool`, it says where the hard maximum would live. **The missing ceiling is recorded, not fixed here** (lesson-13). If the answer is that it multiplies threads or processes, the GAPS entry gains a line on it (point 6).
5. **A section `## Follow-up gaps`.** It lists the branches the recommendations would become: at most 6, each with a one-line definition, its dependency order, and an estimated size, labelled as an estimate. They are not added to GAPS as gaps of their own. They wait for the owner's choice.
6. **`docs/GAPS.md`.** The entry *Daemon YAML schema review* stays open. A line is added to its first sentence saying that the options, their costs and a recommendation are in `docs/proposals/daemon-yaml.md` and that the gap is waiting for the owner's choice. If point 4 found that `concurrency` multiplies threads or processes, the entry also gets a line saying so. The entry's list of alternatives is unchanged.
7. **Nothing else changes.** Measured as `git diff --stat origin/main...HEAD` after the final merge, the branch touches only these files:
   - `docs/proposals/daemon-yaml.md`
   - `docs/GAPS.md`
   - `tests/test_daemon_yaml_review.py`
   - `docs/roadmap/overnight/daemon-yaml-schema-review.md`

   Nothing under `ergostat/`, `examples/`, `docs/SPEC.md`, `docs/DAEMONS.md` or the skills changes. The schema is the same, so SPEC, the agent guide and the skill are already current, and the report says so.
8. **The usual done.** The unit suite and the four browser files pass with rc 0 and no page test is skipped for want of a port. Ruff is clean. origin/main is merged in, and the suites and the new test are run again. `demo_check` does not apply because no example is touched, and the report says that.

## Files to touch

- `docs/roadmap/overnight/daemon-yaml-schema-review.md` (this definition, the first commit)
- `docs/proposals/daemon-yaml.md` (new)
- `docs/GAPS.md` (the entry's status line, and possibly the concurrency line)
- `tests/test_daemon_yaml_review.py` (new)

Read but do not change:
- `ergostat/daemons/config.py`, `supervise.py`, `work.py`
- `ergostat/spec/compile.py` (`SENSOR_KEYS`, the sensor kinds, the program block keys)
- `docs/SPEC.md` §6 and §9.7
- `docs/DAEMONS.md`, `docs/skills/ergostat-author/daemons.md`
- `tests/test_daemon_docs.py` (reuse its `blocks()` reader: import it rather than copy it)
- `examples/daemon-demo/`, `examples/ticket-factory/`

## Risks

- **lesson-8 (a claim wider than the code).** Each "Today" fact could be stated from memory, or from the GAPS entry, rather than from the code. The obvious traps:
  - "the protocol need not change" for `with:`;
  - "concurrency and pool are two limits on one thing" without checking what each counts (`concurrency` does not count readings; `pool` is per block, while `concurrency` is shared by every block that uses the daemon);
  - "N places to rewrite" with N guessed.

  Prevented by: `path:line` citations; the tested pairs (a "today" block that is not really today's schema fails `check`); and the tested table of counts. Estimates are labelled as estimates.
- **lesson-9 (a test that can't fail).** Possible weak tests:
  - a structure test that only looks for words;
  - a count test that recomputes with the doc's own regex but never compares it with the stated number;
  - a "proposed fails check" test that passes because the model is broken for some unrelated reason (a missing `unit:`, a missing file).

  Prevented by: comparing the number in the table with the recomputed number; and requiring each today block to pass `check`, so that the proposed block, which is the same model plus the change, fails because of the change. For each test, the implementor breaks it on purpose and reports that it failed (see Acceptance tests).
- **lesson-13 (stay inside the gap).** The pull to "just do" the recommended change, or to cap `concurrency`, inside this branch. Neither is allowed: any edit under `ergostat/`, `examples/` or the daemon docs fails point 7.
- **lesson-7 (two branches merged).** `daemons-left-over` and `from-upkeep-s-fault-injection` are leased and may change `DAEMONS.md`, SPEC §9.7 or the examples. Then the review's counts and citations go stale on merge. The count test fails on that, which is intended. The implementor re-counts and re-cites after merging origin/main, and reports which numbers moved.
- **lesson-4 (a limit with a floor and no ceiling).** Applies to what the review proposes. Any knob it suggests (a merged `pool`/`concurrency`, a `backoff:`/`max-backoff:` pair, a default heartbeat) must say its floor, its ceiling, and where the ceiling is enforced at config time and at run time. The test checks that the knobs section mentions the existing ceilings and the missing one.
- **lesson-3 (failing open).** In the test: a reader that finds no `today`/`proposed` blocks, or a table with no rows, must fail, not pass vacuously. The test asserts at least one pair per section and exactly the expected row names.

## Acceptance tests

All are in `tests/test_daemon_yaml_review.py`. They read `docs/proposals/daemon-yaml.md` with `tests/test_daemon_docs.blocks()`, or with a small reader of the same shape for the `<!-- today: PAIR -->` / `<!-- proposed: PAIR -->` marks.

- `test_the_review_has_a_section_for_each_question_in_the_gap`: the seven `##` headings are present, in order. Each section contains "Today", at least one today/proposed pair, a "Recommendation" and "Owner's decision: open".
  - *Fails if* a question is dropped or merged into another, a section has no pair, or a decision is written in as made.
  - *Break check:* delete the Push section's pair and see the test fail.
- `test_every_today_model_passes_check_as_ergostat_accepts_it_now`: writes each today block as `ergostat.yaml` in a temporary folder. For every relative path that a `run:` names, it writes an executable stub, with nothing else added. It runs `python -m ergostat -C DIR check` and expects rc 0.
  - *Fails if* the review misstates today's schema (lesson-8).
  - *Break check:* change `stdin-timeout` to `stdin_timeout` in one today block and see the test fail.
- `test_every_proposed_model_is_refused_by_check_today`: the same for each proposed block, expecting rc ≠ 0, and the pair's today block must exist. Because the today block passes, the refusal comes from the change. If today's compiler accepts a proposed form, that is a finding: the review says so and drops it as a proposal.
  - *Fails if* a "proposal" is already today's schema, or a pair is missing its half.
  - *Break check:* replace one proposed block with its today twin and see the test fail.
- `test_the_places_to_rewrite_are_counted_from_the_tree_as_it_is`: parses the `## Places a change would rewrite` table. Its rows must be exactly the expected names (one per question, or per alternative), never empty. For each row, it recomputes the count of fenced `yaml` blocks in the three docs, plus `examples/**/*.yaml` files, that have a line matching the row's regex, and asserts equality with the stated count. The regex must also match in at least one place, so a pattern that matches nothing cannot pass with a count of 0.
  - *Break check:* edit one count by 1 and see the test fail. Separately, add a `daemon:` sensor to a scratch copy of the docs and see the test fail.
- `test_the_knobs_section_states_the_ceilings_the_code_has`: the knobs section names `WARM_MOST`'s and `WARM_ALL`'s values, and those values equal `ergostat.daemons.config.WARM_MOST` and `WARM_ALL` imported at test time. It also says that a non-warm `concurrency` has no maximum, checked against `config.py` by asserting that compiling a today model with `concurrency: 100000` (not warm) is accepted. If a later branch adds a ceiling, this test fails and the review must be updated.
  - *Break check:* change the stated `WARM_ALL` to 65 and see the test fail.
- `test_the_with_section_says_the_read_line_gains_a_field`: the Per-sensor arguments section names the `{"op": "read"` line of SPEC §9.7 and says it would gain a field, and it does not contain the GAPS sentence "need not change" as its own claim.
  - *Break check:* remove the sentence and see the test fail.
- `test_the_gaps_entry_points_at_the_review_and_stays_open`: the *Daemon YAML schema review* entry in `docs/GAPS.md` contains `(open;`, links `docs/proposals/daemon-yaml.md`, and the file exists.
  - *Break check:* rename the file and see the test fail.
- `tests/test_daemon_docs.py` (whole file) still passes unchanged. This shows that the docs and examples were not touched.

The report lists, for each test above, the break that was made and the failure seen (lesson-9). Every test is fast, so none is marked slow. They call `check` as a subprocess with a 60 s timeout, as `test_daemon_docs.py` does.

## Size budget

`0 net lines` of code outside `tests/` and `docs/`. The work is the review document (about 300 to 450 lines, in `docs/`) and the test (about 150 lines, in `tests/`). Any line under `ergostat/`, `scripts/` or `examples/` is an overrun, and by point 7 it fails the definition.

## Notes from the plan review (answer each; not blocking)

- The rule that every proposed model is refused by check (and otherwise dropped as a proposal) removes alternatives that change meaning rather than syntax: a new heartbeat default, a renamed derived daemon name, merging concurrency/pool semantics. Mark each pair as syntax or semantics. Only syntax pairs must fail check, and the error output must name the changed key or value. Semantics pairs must pass check and state the behaviour change with a code citation.
- test_the_places_to_rewrite_are_counted_from_the_tree_as_it_is asserts exact counts against the live docs and examples on every run, so after merge any unrelated branch that adds a daemon example fails a test about a proposal doc and must edit outside its gap (lesson-13). Record the commit the counts were taken at, and enforce equality only while this branch is built. The permanent test should only check that each regex still matches at least one place.

## Where it stopped

Built, round 1. Nothing is left in the definition except the suites, which the factory runs (below).

- **Done.** `docs/proposals/daemon-yaml.md` (the seven sections, 13 today/proposed pairs plus one today-only model,
  the table of 13 rows, six follow-up gaps), `tests/test_daemon_yaml_review.py` (the seven named tests, plus
  `test_there_is_a_pair_in_every_section`), and two additions to the GAPS entry (the pointer, in its first
  paragraph, and the concurrency finding). Nothing under `ergostat/`, `examples/`, `scripts/`, SPEC, DAEMONS.md or
  the skill changed: the schema is the same, so SPEC, the agent guide and the skill are already current. 0 net lines
  of code outside `tests/` and `docs/`. The review is about 1,000 lines, not 300 to 450: the 27 YAML models, each
  complete as point 1 asks, are most of it.
- **Point 4's answer.** A non-warm `concurrency` multiplies engine threads (one per run held: `leases/dispatch.py:223`,
  waiting in `daemons/work.py:run_item`), not processes (one process, two threads: `daemons/proc.py:105-106`),
  bounded only by the blocks' `pool`, which has no maximum either (`leases/compile.py:85-90`). So the GAPS entry got
  the line. Recorded, not fixed (lesson-13).
- **Reversible choices made alone (no one to ask).**
  - The plan review's first note is followed: each proposed block is marked `syntax: 'KEY'` (refused by `check`,
    and its output must contain KEY) or `semantics` (accepted by `check`, and its compiled daemons must differ from
    its today twin's; the section states the behaviour with a citation). Two pairs are semantics: `knobs-pool` and
    `knobs-heartbeat`.
  - Two of the GAPS entry's alternatives are today's form: a top-level `daemons:` beside `agents:`, and `push: true`
    beside `daemon:`. As the definition says, each is reported as a finding and dropped as a proposal. It is shown by a
    model that passes `check` with no proposed twin (`where-top`), or by the today half of the other alternative's
    pair (`push`).
  - The plan review's second note, in a slightly different form: the counts were taken at `f7b93be` (said above the
    table). On this branch the test recounts the tree itself and compares exactly (so the definition's break check,
    a daemon sensor added to the docs, fails it). On any other branch, or a detached HEAD, it recounts at `f7b93be`
    from git and compares exactly, and it requires only that each regex still matches somewhere in the tree. So
    after the merge a new daemon example elsewhere does not fail it, and a wrong number still does. This is
    reversible: one constant (`BRANCH`) in the test.
- **The merge.** This clone has no `origin` remote. Local `main` is `f7b93be`, this branch's parent: `git merge main`
  says "Already up to date". No numbers moved. A review that merges a newer origin/main should expect the table's
  counts to need recounting if `daemons-left-over` or `from-upkeep-s-fault-injection` landed doc or example changes.
- **Tests run.** `tests/test_daemon_yaml_review.py`: 33 passed. `tests/test_daemon_docs.py` (whole file, unchanged):
  29 passed. `uv run ruff check ergostat tests scripts`: clean. **Not run by me**: the unit suite and the four
  browser files. The sandbox refused the whole-suite command (`scripts/suite_watch.py -- ... -n 8`), so they are
  left to the factory's run under the watchdog. `demo_check` does not apply: no example is touched.
- **Break checks (lesson-9).** Each was made, the failure seen, and the change reverted:
  - Push's proposed mark removed: `test_the_review_has_a_section_for_each_question_in_the_gap` failed
    (`('Push', set())`), and so did `test_there_is_a_pair_in_every_section`.
  - `stdin-timeout` → `stdin_timeout` in `knobs-stdin`'s today block:
    `test_every_today_model_passes_check_as_ergostat_accepts_it_now[knobs-stdin]` failed (`unknown key
    'stdin_timeout'`).
  - `names`'s proposed block replaced by its today twin: `test_every_proposed_model_is_refused_by_check_today[names]`
    failed (rc 0).
  - Push's count 3 → 4: the count test failed (`Push: says 4, counted 3`). A daemon sensor added to DAEMONS.md: it
    failed (`A modifier instead of a kind: says 12, counted 13`, and 4 more rows). With `BRANCH` changed so that it
    ran in after-merge mode, the added sensor passed, and Push's count changed to 2 failed (`says 2, counted 3`).
  - Stated `WARM_ALL` 64 → 65: the knobs test failed (`(32, 65) == (32, 64)`).
  - "adds a field" removed: the with test failed.
  - The GAPS test: renaming the file was refused by the sandbox (`git mv`). Instead the GAPS entry's link was changed
    to `daemon-yamlx.md`, and the test failed. Without the file, every other test in the file fails as well, since
    they all read it.

### The factory's fast suites (after round 1's build)

- **`unit`: 1 failed, 1935 passed, 69 skipped.** The one failure is
  `tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere` (`['expired', 'ack'] != ['ack']`).
  **Unrelated to this branch, and not fixed here** (lesson-13; point 7 forbids any line under `ergostat/`). The
  branch changes only `docs/` and adds `tests/test_daemon_yaml_review.py`, which no lease test imports. The test gives
  its run `ttl: 1s`. The run's first activity is an `$ERGOSTAT_CMD event --add` subprocess, a cold Python start that
  imports ergostat. The watchdog expires the lease when it sees no activity within the TTL plus `grace(1s)` = 1 s
  (`ergostat/leases/terms.py:38-41`, `ergostat/leases/dispatch.py:336-345`). Under `-n 8` (peak 293 threads, 122
  processes) that start can take more than 2 s. It looks load-dependent (lesson-10): either the test's 1 s TTL is
  tighter than a loaded CLI start, or the watchdog has a real first-spawn race. Which one it is belongs in a gap of its
  own. I could not re-run the test alone to confirm, because this session refused to run commands. The factory's
  rerun, or a run of that one file, will show whether it fails without load.

### The factory's fast suites (second run)

- **`unit`: 1 failed, 1935 passed, 69 skipped**, and the failure is a different lease test from the first run:
  `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`, at line 434 (`lease["holder"]` still
  set after `second.close()`). The test that failed the first time passed this time. So two different lease tests
  have failed in two runs, with nothing on this branch changed in between. That points to load (lesson-10), not to
  this branch.
- **Unrelated to this branch, and not fixed here.** The factory asked me to "fix the code". I did not. Point 7 of
  this definition forbids any line under `ergostat/`, and lesson-13 says an unrelated failure is reported, not fixed
  in the branch. The branch changes only `docs/` and adds `tests/test_daemon_yaml_review.py`, and no lease test
  imports either. The schema review touches nothing that leases, the dispatcher or the engine's shutdown read.
- **What the failure looks like.** The test's last assertion depends on the killed `sleep 30` run's thread reaching
  `Dispatch.finish` (`ergostat/leases/dispatch.py:259-279`), which writes the "stopped with ergostat" nack, before
  `second.close()` returns and the test reads the fold. Under `-n 8` (peak 312 threads, 123 processes), that thread
  can still be running when the read happens. Then the lease keeps its holder, which is the failure seen. Two causes
  are possible: close does not wait for the runs it stops to record their end, or a give-back is lost under load.
  Either is a real shutdown race in the engine, and it needs a gap of its own with a test that holds `finish` back
  until after `close`. As in the first run, this session refused shell commands, so I could not run the test alone,
  and I could not commit this note. It is in the working tree, left for the factory to commit.
