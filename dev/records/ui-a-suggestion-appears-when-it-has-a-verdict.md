# ui-a-suggestion-appears-when-it-has-a-verdict: A suggestion appears when it has a verdict

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q80 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list Suggestions

**The problem:** 'loop requests-handled was off 92% of the time; why (a flow too small to close the gap, or acting too seldom) is said after 10m of record (1m51s so far)': it names the goal twice, offers two causes and defers. The Agents page calls the same cause 'a valve too small'.

**The change:** Hide a suggestion until its verdict exists; until then its goal's entry carries 'diagnosis in 8m'. Name the goal once. One phrase for the cause on every page.

**User stories it serves:** C2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
No suggestion contains 'is said after'; no suggestion contains its goal's name more than once; the cause phrase for one goal is identical on /diagram and /agents.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built (round 1), net −1 line of code (state.py +15/−14, dynamics.py +1/−4, diagram.js +3/−2).

- Hidden until its verdict: under 10m of record, `ladder_hints` no longer adds the deferring hint; it sets
  `diagnosis_in` on the loop, which `state.attention` copies onto that loop's Needs attention entry, and the side
  list writes it as "· diagnosis in 8m". It applies on every page that reads the hints (/agents, the loop panel, the CLI).
- Goal named once: a loop's suggestion is headed `loop NAME` (it was `controller NAME`) and its text drops the leading
  `loop NAME `. The anti-windup hint's "Hold NAME back" became "Hold it back". The Evidence link now reads the
  loop from the heading.
- One cause phrase: each verdict now says its cause right after "of the time:" in words that no view rewrites
  ("saturated, moving its most each run", "falling behind the load", "answering too late, though it keeps up on
  average"). I removed the three Dynamics `_WORDS` rules that only rewrote the old phrases. `dynamics.attention` no
  longer replaces a loop *hint's* text with the gap sentence (that is for the off-loop entry only).
- Choices made without asking (the most reversible): "its goal's entry" is taken to be the loop's Needs attention
  entry, so a loop off most of the window but holding right now shows no note until the verdict. The CLI's
  `ergostat` status shows the new heading/text as well, and has no "diagnosis in" note.
- Tests: new browser test `tests/test_diagram_rendering.py::test_a_suggestion_appears_when_it_has_a_verdict`
  (Blocks and Dynamics on /diagram, and /agents). I watched it fail on four breaks: hint not held back; the prefix
  not stripped (goal twice); "its valve keeps up" in the cause (pages differ); the diagnosis note not drawn.
  New unit test `test_a_suggestion_waits_for_its_verdict_and_names_its_goal_once`. I updated the two unit tests that
  pinned the old wording.
- Not run: the whole of tests/test_diagram_rendering.py. A foreground run passed its 600s limit, was moved to the
  background and was stopped at the time limit there, and a longer background run was refused. Six of its tests
  were run by name and pass; the merge queue must run the whole file. The unit suite and the other browser files
  were not run here (per the brief). main had not moved since the clone, so merging it changed nothing.

Round 2 (net +1 line of code: ergostat/cli/status.py).

- Review finding (blocking), ergostat/cli/status.py:112-114: fixed. The status command adds " · items about it: …"
  only to a loop's attention entry, not to an entry with level "hint". Before this, a loop's suggestion (now headed
  `loop NAME` too) got the items as well, in the plain output and in --json `attention`. It is pinned by the new
  `tests/test_item_about.py::test_status_names_the_items_on_the_loops_attention_line_not_its_suggestion`, which adds
  a `loop a` hint beside a real off loop. I removed the level check and watched the test fail, then put it back.
- Review finding (not blocking), suites not run: still not run here. I ran tests/test_item_about.py (17 passed),
  the acceptance browser test by name (passed, rc 0 under the watchdog) and ruff (clean). The whole of
  tests/test_diagram_rendering.py, the unit suite and the other browser files are left to the merge queue, as the
  brief says.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:21).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:22).

Its runs failed past their attempts (a dead letter):
- attempt 12: nack exited 1
- attempt 13: nack given back
- attempt 14: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 15: nack the run ended with gap/ui-a-suggestion-appears-when-it-has-a-verdict still parked
