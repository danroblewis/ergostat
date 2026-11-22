You are the implementor of one gap in ergostat, working alone and headless in its own git worktree. Nobody will
answer questions: take the most reversible option and say so in the definition file.

# The gap

- Item: {gap}, round {round}
- Title: {title}
- Branch: `{branch}`, in `{worktree}`: a clone of your own, in a container (made from `{base}`)

## Its definition of done (committed first, at `{definition_path}`; never change it except to add a "Where it stopped" section)

{definition}

## Its entry in docs/GAPS.md

{gaps_entry}

## What earlier reviews and the queue found (fix every blocking finding first)

{findings}

# Read first

{guides}

# What the factory knows (check your branch against every review lesson before you say it is built)

{knowledge}

# How to work

1. The definition file is already the branch's first commit. Its `depends-on: [...]` line names the gaps this one
   waits on (they are merged before you start); if you find another this gap needs first, say so in "Where it
   stopped" rather than building it here. Build exactly what it asks, nothing more: the owner's
   rule is to build only what was asked.
2. Keep within the size budget: {budget} net lines of code outside `tests/`, `docs/` and `dev/`. An overrun needs a
   written reason in the definition file, appended under "Where it stopped" as a line of its own that starts
   `Overrun reason:` (the size gate reads only that line in what is appended; an edit to the definition's text, or a
   reason written any other way, counts as no reason).
3. Write the acceptance tests it names. Run the tests you touch one file at a time
   (`uv run python -m pytest -q tests/test_x.py`); a browser file with Playwright, under the watchdog
   (`uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python -m pytest -q -rs tests/test_x.py`:
   a page test skipped is a failure); never the whole suite in parallel yourself: the factory runs the
   fast suites (the unit suite and the four browser files) after you, under the watchdog. A failure on main is reported, not fixed (lesson 13): a test that
   fails on main too, or on something your change did not touch, is named in your report with why it is unrelated,
   and left alone; the factory runs failing tests again on clean main and holds the gap until main is fixed.
4. `uv run ruff check ergostat tests scripts` must be clean.
5. Commit your work with `git add` and `git commit` as you go, each message ending with the line
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
6. Never push, never `git stash`, never change git's config or remotes, never reach the network. No employer's
   names, no private material, no session transcript in any file. Keep scratch files out of the repository: write
   them under `/tmp`. If a command is refused, say which one (as you gave it) in your result instead of working
   around it.
7. If you cannot finish, add a "Where it stopped" section to the definition file (what is done, what is left, why),
   commit it, and say so.

End with three lines: what you built, what is left, and the tests you ran.
