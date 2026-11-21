# mode-advise-on-a-block-that: `check` refuses `mode: advise` on a block that takes items, and says to gate it instead
depends-on: []

## Definition of done

1. **The refusal.** In `ergostat/leases/compile.py::check`, a block with `takes:` and `mode: advise` gets a compile error with the new code `advise-with-takes`, at the block's `where`. The message names the block and says three things:
   - advise asks before a command or an event, never before each item;
   - to have a person let its items through, gate the block with `goal:` or `in: block.X` from a block a person commands, and its items wait while that is off;
   - otherwise leave `mode` out.

   The check runs right after the `b.type not in ("program", "ai")` check and before the kind and state checks. A block whose `takes.kind` is unknown, or whose states are wrong, still gets `advise-with-takes` as well as its other errors. A block whose `takes:` was refused at parse time (`b.takes is None`) gets no `advise-with-takes`: its own error already stops the model.
2. **Nothing else is refused.** These still compile with no `advise-with-takes`:
   - a block with `takes:` and no `mode`, or with `mode: auto`;
   - `mode: advise` on a commanded block without `takes:`;
   - `mode: advise` on an event-started block (`on:`), as in `tests/test_triggers2.py`;
   - `examples/docs-fresh` (its `doc-writer` is advised and takes nothing).
3. **The dispatcher is not changed.** `ergostat/leases/dispatch.py`, `engine.py`, `triggers.py` and `inbox/` are untouched. The inbox lists `advise:BLOCK` only for blocks it can really ask about, because no model that compiles has advise together with `takes:`.
4. **The docs say it.**
   - **docs/SPEC.md:** line ~1906, where `mode` is defined, adds "not on a block that takes items (`check`: `advise-with-takes`); gate it instead". The §9.5 key table's `takes` row, or the *Dispatch* paragraph, says the same, with the gate as the way to have a person hold items.
   - **docs/AGENT-GUIDE.md:** line ~429, which lists `mode: advise` as human approval, adds the same exception and the gating alternative.
   - **docs/GAPS.md:** this entry is marked **done** (branch `mode-advise-on-a-block-that`), saying the refusal was chosen and that asking per item is left unbuilt.
5. The house "done" rules hold:
   - the unit suite and the four browser files pass with rc 0;
   - ruff is clean;
   - origin/main is merged in and the suites are run again;
   - `demo_check` is not needed, because no example is touched.

## Files to touch

- `ergostat/leases/compile.py`
- `tests/test_leases.py`
- `docs/SPEC.md`
- `docs/AGENT-GUIDE.md`
- `docs/GAPS.md`

## Risks

- **lesson-8 (a claim wider than the code):**
  - The docs might say "an advised block always asks", or that the inbox's advise guards are all real, when only this check stands behind it. Each doc sentence must point at the check, and the check must have a test that fails without it.
  - The GAPS entry must not claim asking per item was built.
- **lesson-3 (failing open):**
  - The check might sit after a step that sets `b.takes = None` (unknown kind or state), so an advise block with a mistyped kind loses the refusal. The model would still fail, but on a different error, and fixing the kind would then expose a silently ignored advise. That is why the check runs before those steps.
  - The check must read `b.mode` as compiled. `mode` defaults to `"auto"`, and only `"auto"` and `"advise"` pass `bad-mode`, so there is no third value to fall through.
- **lesson-9 (a test that can't fail):**
  - A test that only checks "some error exists" would pass on the existing kind or state errors. Tests must assert on `code == "advise-with-takes"` and on the block's name.
  - The negative test must assert that this code is absent, not that the model has no errors at all.
- **lesson-7 (two things merged that each passed alone):** another branch (for example `a-block-s-pool-set-by-the-model`, which also edits `leases/compile.py::check`) could add a test model or example with advise and `takes:`, or conflict in `check`. Merge origin/main, run both suites again, and grep merged models for `mode: advise` beside `takes:`.
- **lesson-13 (stay inside the gap):** no change to the dispatcher, the engine or the inbox. A suite failure elsewhere is reported by name, not fixed here.

## Acceptance tests

- **`tests/test_leases.py::test_mode_advise_on_a_block_that_takes_is_refused`**
  - **Model:** a `program` block and an `ai` block, each with `takes: {kind: ticket, at: ready}` and `mode: advise`, plus a third advised block whose `takes.kind` is `tickets` (unknown).
  - **Asserts:**
    - each of the three has exactly one error with code `advise-with-takes` whose message names it;
    - the message says to gate it (contains `goal:` and `in: block.`);
    - the third block also has its `unknown-ref`.
  - **Guards:** this fails if the check is removed (lesson-9). It also fails if the check is moved after the kind check, because the third block's assertion breaks (lesson-3).
- **`tests/test_leases.py::test_mode_advise_without_takes_and_takes_without_advise_compile`**
  - **Models:**
    - `takes:` with no `mode`;
    - `takes:` with `mode: auto`;
    - a commanded `mode: advise` block (`in: block.c` from an `expr` block) with no `takes:`;
    - the `tests/test_triggers2.py` `MODEL` with `mode: advise` added to `triage`.
  - **Asserts:** no problem has code `advise-with-takes`.
  - **Guards:** this fails if the check is written too broadly, for example on `mode == "advise"` alone or on `takes` alone (lesson-9).
- **Existing tests, unchanged and passing:**
  - `tests/test_leases.py::test_takes_is_checked`;
  - the advise tests in `tests/test_triggers2.py` and `tests/test_triggers3.py`;
  - `tests/test_inbox.py`.

  Together these show the event-started and commanded advise paths and the inbox are untouched (lesson-13).
- **Report:** say that each new test was run with the check commented out and with the check moved after the kind check, and that it failed as expected (lesson-9).

## Size budget

15 net lines (the check and its message in `ergostat/leases/compile.py`, plus one line in the `check` docstring). Anything over 30 needs a written reason.

## Notes from the plan review (answer each)

- lesson-8: the error message and docs promise that gating a takes-block with `goal:` or `in: block.X` makes its items wait while the gate is off. No acceptance test shows this. Name an existing test that proves a gated takes-block holds its items and that `in:` compiles together with `takes:`, or add one. If neither holds, narrow the message, because telling users to do something that check refuses or the dispatcher ignores is worse than saying nothing.
- lesson-8: Definition-of-done item 3 says the inbox lists `advise:BLOCK` only for blocks it can really ask about. That rests only on this compile check. Either word it as 'because check refuses advise with takes' in the GAPS entry and docs, or don't state it as an inbox property.
- lesson-3: the guard is `b.takes is None`, which means 'refused at parse'. Confirm that check keeps no other path where `takes` was written but parsed to something falsy other than None, for example an empty dict. If there is one, test it so the refusal is not skipped.
- lesson-7: before merging origin/main, also grep the current tree (tests/, examples/, docs/ snippets that run as tests) for `mode: advise` beside `takes:`. A fixture that exists today would now fail to compile, and it is part of this change, not something outside the gap.
- lesson-9: in the positive test, assert the error's `where` is the block's location (as definition-of-done item 1 says), not only its code and name.
- The 'run with the check commented out and moved' step in the report should include the actual failing assertion lines, not just say the tests failed.
