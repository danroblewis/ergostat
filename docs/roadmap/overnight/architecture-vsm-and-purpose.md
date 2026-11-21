# architecture-vsm-and-purpose: per system, an AI reviewer (haiku by default) checks the system against Beer's Viable System Model and checks whether its goals cover its purpose. It works from a computed evidence list, its answers are checked against the model, and what it finds is held for the owner as modelling requests.
depends-on: []

## Definition of done

The computed rung (`ergostat/spec/architecture.py`: `system-splits`, `systems-merge`, `interface`, `time-scales`, `purpose`) is already built and stays as it is. This branch adds the AI rung that `docs/proposals/architecture.md` §7 and §8 describe as "not computed". Aggregation from loop dominance, the relative gain array, interface stability, any daily or automatic schedule, and the redesign are all outside it. The owner runs it on demand.

1. **The computed checklist** (`ergostat/spec/vsm.py`, new, structure only, no run). `checklist(spec, system) -> dict` gives, for each of `S1`, `S2`, `S3`, `S3*`, `S4`, `S5`, the candidate parts the structure shows, each with a short reason:
   - S1: the system's goals whose `of` is a stock inside the system, plus its direct subsystems.
   - S2: blocks of the system that `takes` an item kind that a block outside the system also takes (they share leases, SPEC §9.5), or whose `params["workspace"]` names a pool that a block outside also uses.
   - S3: goals in `spec.inner_loops` of a subsystem whose setpoint is set from this system, plus goals inside whose setpoint another goal's block commands.
   - S3*: blocks of `type: judge`, and blocks with a `claims` param.
   - S4: flows into the system from a cloud that have a sensor (the outside, measured). The model's `use: modelling` loop is listed too, marked model-wide.
   - S5: the system's `description`, the model's `purpose:`, and the descriptions of its subsystems.

   A function with no candidates is an empty list. The checklist is evidence only: it raises no `check` note and makes no finding.

2. **The reviewer** (`ergostat/numbers/vsm_review.py`, new, plus the prompt `ergostat/numbers/vsm_prompt.md`). `review(p, spec, system, model="haiku", cap=PER_CALL) -> dict` works in five steps:

   a. **The brief.** It builds a Markdown brief of the system: its description, the model purpose, its parts with their descriptions, its subsystems with theirs, its `interface` ports, the architecture notes that `check` reports about it, and the computed checklist. The brief is cut to `BRIEF_CHARS = 30000` characters, and the cut is stated in the brief.

   b. **One call.** It makes one call through `decisions.ai.call`: `$ERGOSTAT_AI` (default `claude -p`), `--model haiku` unless told otherwise, no tools, `--max-budget-usd` set to the per-call cap, and a timeout of `TIMEOUT = 300` s (a module constant).

   c. **The answer form.** It asks for one JSON line:
      `{"functions":[{"s":"S1..S5|S3*","present":bool,"parts":[ids],"why":str}],"purpose":{"goals":[{"goal":id,"serves":bool,"quote":str}],"uncovered":[{"quote":str,"why":str}]}}`

   d. **Checks on the answer.** The answer is checked, not trusted:
      - `s` must be one of the six functions. The first entry for each function counts and later ones are dropped.
      - A function said **present** must name at least one part that is in the system, or (for S5) `description`/`purpose` when the system has that text. If it names none, the function is **unsupported**: dropped and counted.
      - A function said **missing** is kept. Where the computed checklist had candidates for it, the request says so and names them.
      - A goal in `purpose.goals` must be one of the system's goals, or the entry is dropped. If it is said to serve the purpose, its `quote` must appear verbatim in the system's description, compared after `decisions.ai.norm`, or the entry is dropped.
      - Each `uncovered.quote` must have at least two words and appear verbatim (after `norm`) in the system's description or the model's `purpose:`, or it is dropped.
      - A system with no description gets no purpose coverage (the computed `purpose` note already says so). Only its VSM checklist is reviewed.

   e. **The record.** The review is recorded as the event `ergostat.architecture.reviewed`. Its data holds:
      - `system`;
      - `signature`, from `redesign_due.signature(spec, system)`;
      - `words`: a hash of the model purpose, the system's description, its subsystems' descriptions and its goals' descriptions;
      - `model`;
      - `cost_usd`, with `cost: reported` when Claude Code reported dollars, or `cost: charged`, set to the whole per-call cap, when it did not;
      - `tokens`;
      - the checked functions and purpose coverage;
      - `dropped`, the count of entries dropped;
      - `applied`.

      A call that fails, times out, returns `is_error`, or gives no readable answer line is recorded as `ergostat.architecture.unreviewed`, with its `why` and the cost (the cap when not reported). It raises nothing and answers nothing.

3. **What it raises.** Each kept result becomes a modelling request with `source: architecture`, id `rq.rid("architecture", code, about)`. Each request is raised **held for the owner** (`owner: True`, `tier: owner`), so no tier writes a model change for a judgement:
   - `vsm-s1`, `vsm-s2`, `vsm-s3`, `vsm-s3-audit`, `vsm-s4`, `vsm-s5` about `system.NAME`, for each function said missing;
   - `purpose-uncovered` about `system.NAME`, whose `says` lists the quotes;
   - `goal-off-purpose` about `goal.NAME`.

   An applied review **answers** every open architecture request about that system (and its goals) that it no longer says. A request answered before and said again is reopened with fresh `says`, `version`, `review` (the review event's seq), and `why`/`change` cleared, then held again. `requests.sync` leaves `source: architecture` requests alone, as it does `redesign`.

4. **Concurrency and order.** Before the call, the reviewer reads the seq of the latest `ergostat.architecture.reviewed` for the system. The record and request writes happen under an fcntl lock on `p.dir / "architecture.lock"`. Inside the lock it reads the latest seq again. If a review of the same system was recorded since, this review is recorded with `applied: false` and changes no request. Reviews are ordered by `seq`, never by `at`.

5. **Bounds.** There is one call per system. `ergostat improve --architecture [SYSTEM]` reviews one system, or, with no SYSTEM, every system except a once template's own (the modelling template's system is never reviewed).
   - At most `MOST_SYSTEMS = 12` systems per run. The rest are listed as not reviewed.
   - `--max-cost USD` defaults to 1.00 and is refused above `CEILING = 5.00`, both when the arguments are parsed and inside `review_all`.
   - Before each call the run checks `spent + PER_CALL (0.25) > max_cost` and stops if true. Unreported costs count as the whole cap.
   - `--model M` defaults to `haiku`.
   - It prints one line per system (functions present, missing, unsupported; requests raised and answered; its cost) and the run's total. `--json` gives the same as data.

6. **Shown where things already are** (no new page or panel). The requests appear on the Items tab, in the inbox (they are held) and in `ergostat status`, as every modelling request does. `ergostat explain system.NAME` (with a project) adds a `Viable System Model:` block from the latest applied review: each function, present (with its parts) or missing, the purpose quotes left uncovered, and the model and cost. When the system's `signature` or `words` differ from the review's, it adds "reviewed on an earlier version of this system". `explain` stays read-only, so it is unchanged on the read-only fallback.

7. **Docs.**
   - SPEC §12: a paragraph under *How the model is divided into systems* on the AI rung: the checklist, the checks on the answer, the requests, the bounds.
   - SPEC §12e: the `architecture` request source.
   - `docs/proposals/architecture.md` §7 and §8: "Computed today" says what is built.
   - GAPS: the architecture entry's *Left* loses "the Viable System Model checklist and purpose coverage".
   - `docs/AGENT-GUIDE.md`: one line on `improve --architecture`.

   The docs claim only what the tests show: that a function said present names one of the system's parts, that quotes are the owner's words, and that a failed review changes nothing. They never claim the reviewer finds every missing function.

## Files to touch

- `ergostat/spec/vsm.py` (new)
- `ergostat/numbers/vsm_review.py` (new)
- `ergostat/numbers/vsm_prompt.md` (new; counted in the budget)
- `ergostat/numbers/requests.py` (`sync` skips `source: architecture`)
- `ergostat/cli/__init__.py`, `ergostat/cli/numbers.py` (`improve --architecture [SYSTEM] --model --max-cost`)
- `ergostat/spec/explain.py` (the `Viable System Model:` block on `system`)
- `docs/SPEC.md`, `docs/proposals/architecture.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md`
- `tests/test_vsm_review.py` (new)

## Risks

- **lesson-1.** Read the requests, call for a minute, write: another review of the same system can land in between, and one review's answers then overwrite the other's. Writes happen under `architecture.lock`, after reading the latest seq again inside the lock.
- **lesson-2.** Deciding which review is current by `at` would get it wrong. Order by event `seq`, and compare the `signature`/`words` stamps for equality.
- **lesson-3.** Several things can go missing or fail: the AI times out, errors, gives garbage or reports no cost; a cited part does not exist; the system has no description. These must never count as "all functions present" or answer earlier requests. An unreported cost counts as the whole cap, and the cap is checked as `spent + PER_CALL > max_cost` before each call.
- **lesson-4.** The number of systems and the dollars per run need a ceiling: `MOST_SYSTEMS` and `CEILING`, enforced when the arguments are parsed and again inside `review_all`.
- **lesson-5.** A request id is the same for the same code on the same system. A request answered and then said again must start fresh (`says`, `review`, `version`; `why`/`change` cleared).
- **lesson-6.** A hung `claude -p` must not outlive the review. `subprocess.run(timeout=)` kills and waits for its child, and the call runs with no tools, so there are no grandchildren. A test shows the process is gone.
- **lesson-7.** `requests.sync` would answer every architecture request on its next pass, and `improve`'s new flags must not land on a read topic. `improve` is not in `goodmodel.READS`, and `tests/test_cli_fallback.py` keeps that true. Merge origin/main and run the suites again.
- **lesson-8.** The docs could overclaim what the reviewer does, for example that it finds what is missing. Claims are narrowed to what the checks enforce: present means at least one real part is named, and quotes appear verbatim.
- **lesson-9.** A test could still pass with the code it guards removed. For each test, the implementor breaks that code and reports that the test failed.
- **lesson-10.** A timeout test that depends on load. The hung-AI test uses a 1 s timeout against a 60 s sleep, and asserts only that the process is gone and the review is unreviewed, never the elapsed time.
- **lesson-13.** Unrelated suite failures are reported, not fixed here.

## Acceptance tests

All tests are in `tests/test_vsm_review.py`. A fake `$ERGOSTAT_AI` script prints a canned answer, writes its argv and stdin to files, and counts its calls.

- `test_the_computed_checklist_names_each_function_s_candidates`: a system with a goal on its own stock, a judge block, an inner loop set from it, a kind taken by it and by another system, and a description gets S1, S3*, S3, S2 and S5 candidates, and S4 is empty. A system with nothing gets empty lists. Fails if any mapping is wrong (lesson-9).
- `test_a_review_raises_a_held_request_for_each_missing_function_and_records_its_cost`: the answer says S4 is missing. Request `vsm-s4@system.ops` is held with `owner: True`. The review event has `model: haiku`, the reported `cost_usd`, `signature` and `words`, and the argv had `--model haiku` and `--max-budget-usd 0.25`.
- `test_a_function_said_present_must_name_a_part_of_the_system`: S1 present citing `stock.nope`, and S3 present citing a part of another system, are both unsupported and counted in `dropped`. They raise nothing and mark nothing present (lesson-8).
- `test_purpose_quotes_must_be_the_owner_s_words`: an uncovered quote not in the description is dropped. One with curly quotes and different whitespace is kept and raises `purpose-uncovered`. A `goal-off-purpose` naming another system's goal is dropped (lesson-8).
- `test_a_failed_answer_reviews_nothing_and_answers_nothing`: with a held `vsm-s4` from an earlier review, a garbage answer, an `is_error` result and a nonzero exit each record `unreviewed`. The request stays held, and the cost recorded is the cap when none was reported (lesson-3).
- `test_the_cost_cap_is_checked_before_each_call_and_bounds_hold`: three systems with `--max-cost 0.6` make two calls, and the third system is listed as not reviewed. An unreported cost counts as 0.25. `--max-cost 50` is refused with exit code 2. With `MOST_SYSTEMS` monkeypatched to 2, a run stops at 2 (lessons 3 and 4).
- `test_a_later_review_answers_what_it_no_longer_says_and_a_remade_request_starts_fresh`: first S4 missing (held), then S4 present (answered), then S4 missing again. The same id is reopened and held, with the third review's seq and `says`, and no `why`/`change` from before (lesson-5).
- `test_a_review_recorded_while_this_one_ran_wins`: the call step is monkeypatched to record a competing applied review of the same system, stamped with an earlier `at`. This review is recorded `applied: false`, and the requests match the competitor's. Fails if writes skip reading the seq again inside the lock, or if order comes from `at` (lessons 1 and 2).
- `test_sync_never_answers_an_architecture_request`: after a review raises `vsm-s4`, `requests.sync` leaves it held (lesson-7).
- `test_explain_says_the_latest_review_and_when_it_is_stale`: `explain system.ops` lists S1–S5 present or missing. After only the system's description is edited, it says the review was of an earlier version (because the `words` hash changed).
- `test_a_hung_ai_is_killed_at_its_timeout`: the fake writes its pid and sleeps 60 s, with `TIMEOUT` set to 1. The review is unreviewed, and the pid is no longer alive (lessons 6 and 10).
- `test_the_template_s_own_system_is_never_reviewed`: with `use: modelling`, `improve --architecture` with no system skips the template's system.
- `test_improve_architecture_prints_each_review_and_its_cost`: CLI exit code 0, one line per system and the total. `--json` gives the same data.
- `tests/test_cli_fallback.py::test_every_flag_of_a_read_topic_is_called_acting_or_read_only` still passes: `improve` is not a read topic.
- The unit suite and the four browser files pass with exit code 0, with no page test skipped for want of a port. `ruff` is clean. No example is touched, so no `demo_check` is needed. Origin/main is merged in and the suites run again.

## Size budget

550 net lines outside `tests/` and `docs/`, including the prompt file; expected about 450. Roughly: `vsm.py` 110, `vsm_review.py` 230, prompt 30, CLI 45, explain 30, `requests.py` 3.

## Notes from the plan review (answer each; not blocking)

- Answering is fail-open (lesson-3): an applied review answers every architecture request it 'no longer says', so a function whose present claim was dropped as unsupported, a function omitted from the answer, a dropped goal entry, or a system with no description (purpose skipped) all answer earlier held requests. Answer only on positive kept evidence: vsm-sX only when that function is kept present with a real part; purpose requests only when purpose coverage was reviewed; goal-off-purpose only when that goal's entry was kept serves:true. Add tests for each where the held request must stay held.
- The hung-AI test cannot fail on lesson-6: subprocess.run(timeout=) kills only the direct child. A fake shell script's `sleep 60` (or claude's own Node children) is a grandchild that survives and keeps the pipes open, so communicate() blocks ~60 s, while the test checks only the shell's pid, which is gone. Start the call in a new session and kill the process group on timeout; the fake must spawn a child sleep and record its pid; assert both pids are gone and the review returned well before 60 s (generous bound).
