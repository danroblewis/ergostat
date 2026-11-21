# model-edit-293151c1c2: bring the model changes accepted in the instance into the repository

## Definition of done

The changes below, made to the instance's copy of the model while it ran 2388572aebcb, are in the repository's model files, `ergostat check` is clean, and tests/test_factory.py passes.

```diff
--- a/ergostat.yaml
+++ b/ergostat.yaml
@@ -206,7 +206,7 @@
   opus:
     kind: ai
     model: claude-opus-5-5
-    at-once: 3
+    at-once: 24                         # operator, 2026-11-20: was 3, shared by every AI block, so planning got no slot while 3 implementors ran
     description: headless Claude Code sessions (claude -p) on Opus for the implementor and the reviewer; dev/factory.toml
   coordinator:
     kind: person
--- a/dev/bin/agents.py
+++ b/dev/bin/agents.py
@@ -209,7 +209,10 @@
         fac.git(d.parent, "init", "-q", "--bare", str(d))
     base = cfg["git"]["base"]
     fac.git(d, "symbolic-ref", "HEAD", f"refs/heads/{base}")
-    fac.git(d, "fetch", "-q", str(fac.path(cfg, "checkout")), f"+refs/heads/{base}:refs/heads/{base}")
+    # operator 2026-11-20: main as pushed (the checkout's origin/main), never the checkout's own main, where the queues
+    # merge before testing: branches forked from that carried merges that later failed and were undone
+    remote = cfg["git"].get("remote", "origin")
+    fac.git(d, "fetch", "-q", str(fac.path(cfg, "checkout")), f"+refs/remotes/{remote}/{base}:refs/heads/{base}")
     return d
 
 
--- a/dev/bin/implement.py
+++ b/dev/bin/implement.py
@@ -25,8 +25,8 @@
 import fac  # noqa: E402
 import pools  # noqa: E402
 
-KILL_HOURS = 4.0             # the kill rule: a gap that has taken this long building stops
-FAILS = 2                    # the kill rule: a gap whose fast suites fail this many times stops
+KILL_HOURS = 12.0            # the kill rule: a gap that has taken this long building stops
+FAILS = 6                    # the kill rule: a gap whose fast suites fail this many times stops
 
 
 def definition_first(cfg: dict, gap: dict, work: Path) -> tuple[str, str]:
--- a/dev/bin/plan.py
+++ b/dev/bin/plan.py
@@ -25,7 +25,7 @@
 import brief  # noqa: E402
 import fac  # noqa: E402
 
-MOST_SPLIT, MOST_RESEARCH, KILL, MOST_WAITS = 6, 3, 2, 12      # 12 waits of 30 minutes
+MOST_SPLIT, MOST_RESEARCH, KILL, MOST_WAITS = 6, 3, 4, 12      # 12 waits of 30 minutes
 TAG = re.compile(r'<definition branch="([^"]*)"(?: title="([^"]*)")?>\n?(.*?)</definition>', re.S)
 DEPS = re.compile(r"^depends-on:\s*\[([^\]]*)\]", re.M)
 
@@ -139,13 +139,16 @@
     v = review.verdict(str(got.get("result", "")))
     record = dict(contexts=[context], ai_cost_usd=round(float(got.get("total_cost_usd") or 0), 4), sessions=1,
                   plan_reviews=[{"verdict": v["verdict"], "blocking": v["blocking"], "at": time.time()}])
+    if v["verdict"] == "fix":           # operator, 2026-11-20: not a gate; its findings travel as notes (owner)
+        v = {**v, "verdict": "merge", "non_blocking": list(v["blocking"]) + list(v.get("non_blocking") or [])}
     if v["verdict"] != "merge":
         return send_back(cfg, gap, v["blocking"] or [v["where_it_stopped"] or "parked"], v["verdict"] == "park",
                          **record)
     target, by = fac.run_dir(cfg, "defs") / f"{branch}.md", "plan"
     try:
+        notes = "".join(f"- {n}\n" for n in v.get("non_blocking") or [])
         with target.open("x") as fh:                     # never over a definition the coordinator wrote meanwhile
-            fh.write(plan)
+            fh.write(plan + (f"\n## Notes from the plan review (answer each)\n\n{notes}" if notes else ""))
     except FileExistsError:
         by = "coordinator"
     fac.say("gap.defined", definition=fac.rel(target), ready_at=time.time(), branch=branch, defined_by=by,
--- a/dev/bin/pools.py
+++ b/dev/bin/pools.py
@@ -77,6 +77,7 @@
 
 
 def tune(cfg: dict) -> int:
+    return 0      # operator, 2026-11-20: paused; it lowered the owner's pools on parks caused by main (pool-control replaces it)
     st = state(cfg)
     evidence = outcomes(fac.items("gap"), fac.items("upgrade"))
     what, why, streak = decide(evidence, st["since"], st, cfg)
--- a/dev/bin/queue.py
+++ b/dev/bin/queue.py
@@ -39,19 +39,37 @@
 
 
 def suites(cfg: dict, repo, branch: str, logs, began: float) -> dict:
-    out = {}
-    for name in ("ruff", "unit", "browser", "demo"):
+    """ruff first; then unit, browser and demo at once (operator 2026-11-20: they are independent, and the queue is
+    the factory's binding constraint); the first failed, in that order, is the one reported."""
+    import threading                    # not concurrent.futures: this file is named queue.py, which shadows the stdlib
+
+    def one(name):
         log = logs / f"{fac.run_tag(branch, began)}-{name}.txt"
         rc, secs = fac.suite(cfg, name, repo, log, slot=False)        # the queue's lock is its slot
+        return name, rc, secs, log
+
+    out = {}
+    first = [one("ruff")]
+    rest = []
+    if not first[0][1]:
+        got = {}
+        ts = [threading.Thread(target=lambda n=n: got.__setitem__(n, one(n))) for n in ("unit", "browser")]
+        for t in ts:
+            t.start()
+        for t in ts:
+            t.join()
+        rest = [got[n] for n in ("unit", "browser")]
+        if not any(r[1] for r in rest):         # demo after: under the other two's load its pages drew nothing
+            rest.append(one("demo"))
+    for name, rc, secs, log in first + rest:
         text = log.read_text()
         skipped = len(re.findall(r"^SKIPPED", text, re.M)) if name == "browser" else 0
         out[name] = {"rc": rc, "seconds": round(secs), **({"skipped": skipped} if skipped else {})}
-        if rc or skipped:
+        if (rc or skipped) and "failed" not in out:
             out["failed"] = name
             out["tests"] = fac.failed_tests(text)
             out["tail"] = text[-2000:]
             out["log"] = str(log)
-            break
     return out
 
 
@@ -160,6 +178,12 @@
         why = clean_main(cfg, repo) or settle(cfg, repo)
         if why:
             fac.nack(f"queue: {why}", after="10m", count=False)
+            return 0
+        remote = cfg["git"].get("remote", "origin")          # operator 2026-11-20: merge onto main as pushed, never a
+        fac.git(repo, "fetch", "-q", remote, base)           # stale checkout main (other queues push from elsewhere)
+        if not fac.git_ok(repo, "merge", "-q", "--ff-only", f"{remote}/{base}"):
+            fac.nack(f"queue: the checkout's {base} cannot fast-forward to {remote}/{base} (unpushed commits?)",
+                     after="10m", count=False)
             return 0
         sha, why = reviewed(cfg, repo, gap)
         if not sha:
--- a/dev/bin/review.py
+++ b/dev/bin/review.py
@@ -45,8 +45,8 @@
     commits = fac.git(wt, "rev-list", *own, f"{base}..HEAD").split()
     touched = fac.git(wt, "log", *own, "--format=%H", f"{base}..HEAD", "--", rel).split()
     on_base = fac.git_ok(wt, "cat-file", "-e", f"{base}:{rel}")
-    if not on_base and (not touched or not commits or touched[0] != commits[0]):
-        found.append(f"gate 1: {rel} is not the branch's first commit")
+    if not on_base and not touched:          # operator 2026-11-20: its place in history is not a defect; its absence is
+        found.append(f"gate 1: {rel} is not on the branch")
     if continued and not fac.git_ok(wt, "merge-base", "--is-ancestor", built_main, "HEAD"):
         found.append(f"gate 1: the continued branch does not hold main as of its build ({built_main[:12]}): main is "
                      "not merged in")
--- a/dev/factory.toml
+++ b/dev/factory.toml
@@ -11,7 +11,7 @@
 run = "run"                          # briefs, logs, the cost ledger (from the model's folder)
 
 [gates]
-kill_after = 3                       # failed gates (reviews, queue conflicts, real failures) that park a gap
+kill_after = 6                       # failed gates (reviews, queue conflicts, real failures) that park a gap
 
 [git]
 base = "main"                        # what a gap's branch starts from, and what the queue merges into
@@ -23,7 +23,7 @@
 reviewer_model = "opus"
 implementor_session_usd = 15.0       # the most one implementor session may spend (claude --max-budget-usd)
 reviewer_session_usd = 5.0
-suite_fix_rounds = 1                 # sessions the implementor gets to make its failing fast suites pass
+suite_fix_rounds = 2                 # sessions the implementor gets to make its failing fast suites pass
 planner_model = "opus"               # the planner: a gap's definition of done, or its split (dev/bin/plan.py)
 planner_session_usd = 5.0
 plan_reviewer_model = "opus"         # the plan review: the definition and the lessons only, so cheap
@@ -45,8 +45,8 @@
 token_file = "~/.config/ergostat/claude-token"   # the owner's, from `claude setup-token`; mode 600, or no session
 
 [pools]                              # the AI pools start at 1 and ramp up on good results (dev/bin/pools.py)
-implementor_max = 4                  # the most each may reach (the blocks' pool: in the model is this cap)
-reviewer_max = 2
+implementor_max = 9                  # the most each may reach (the blocks' pool: in the model is this cap)
+reviewer_max = 6                    # operator: reviewers spend AI budget, not machine; suites are capped by the suite slots
 streak = 3                           # good gaps in a row before an increase is asked for
 
 [instance]
--- a/dev/model/budget.yaml
+++ b/dev/model/budget.yaml
@@ -16,7 +16,7 @@
 goals:
   ai-budget:
     auxiliary: ai-spend
-    hold: "<= 80"
+    hold: "<= 3000"
     tolerance: 0
     on-stale: "off"                    # a spend not read is counted as over: the gates close
-    description: the implementor and the reviewer spend at most $80 a day (change it here)
+    description: the implementor and the reviewer spend at most $3000 a day (change it here)
--- a/dev/model/building.yaml
+++ b/dev/model/building.yaml
@@ -206,7 +206,7 @@
     prompt: dev/prompts/implementor.md
     takes: {kind: gap, at: [fix, ready], to: [built], unblocked: true, where: {waits_on_parked: null}}
     # (its dependencies finished, none of them parked; the critical first)
-    pool: 4                          # the most: the pool now is implementor-pool (dev/model/pools.yaml)
+    pool: 9                          # the most: the pool now is implementor-pool (dev/model/pools.yaml)
     lease: {ttl: 90m, attempts: 2}
     timeout: 6h
     in: block.implement-when
@@ -229,7 +229,7 @@
     run: python3 dev/bin/review.py
     prompt: dev/prompts/reviewer.md
     takes: {kind: gap, at: built, to: [approved, fix, parked]}
-    pool: 2                          # the most: the pool now is reviewer-pool (dev/model/pools.yaml)
+    pool: 6                          # the most: the pool now is reviewer-pool (dev/model/pools.yaml)
     lease: {ttl: 60m, attempts: 2}
     timeout: 2h
     in: block.review-when
--- a/dev/model/interlock.yaml
+++ b/dev/model/interlock.yaml
@@ -26,19 +26,19 @@
 goals:
   machine-quiet:
     auxiliary: suites-running
-    hold: "<= 3"
+    hold: "<= 6"                    # operator 2026-11-20: six suite slots now
     tolerance: 0
     on-stale: "off"                    # not knowing the load holds the suites
     description: the machine's suite slots not all taken (three shared, and the queue's) when the queue or triage starts one
   suite-threads-within:
     auxiliary: suite-threads
-    hold: "<= 1200"
+    hold: "<= 3000"                 # operator: 28 CPUs; the panic was at ~14k threads
     tolerance: 0
     on-stale: "off"
     description: the suites' threads below the watchdog's 1,500, with room
   suite-memory-within:
     auxiliary: suite-memory
-    hold: "<= 5"
+    hold: "<= 40"                   # operator: GB; 256 GB machine, each suite container capped at 12 GB
     tolerance: 0
     on-stale: "off"
     description: the suites' memory below the watchdog's 6 GB, with room
--- a/dev/model/knowledge.yaml
+++ b/dev/model/knowledge.yaml
@@ -267,7 +267,7 @@
     run: python3 dev/bin/plan.py
     prompt: dev/prompts/planner.md
     takes: {kind: gap, at: [open, replan], to: [planned, split, ready, replan, parked]}
-    pool: 1
+    pool: 12                           # operator: planners spend AI budget, not machine
     lease: {ttl: 60m, attempts: 2}
     timeout: 2h
     in: block.plan-when
@@ -288,7 +288,7 @@
     run: python3 dev/bin/plan.py review
     prompt: dev/prompts/plan_reviewer.md
     takes: {kind: gap, at: planned, to: [ready, replan, parked]}
-    pool: 1
+    pool: 8
     lease: {ttl: 30m, attempts: 2}
     timeout: 45m
     in: block.plan-review-when
--- a/dev/model/pools.yaml
+++ b/dev/model/pools.yaml
@@ -54,7 +54,7 @@
     type: program
     description: raises a pool (asked of the coordinator) after a streak of good gaps; lowers them at once on a park, a second fix round or a reverted merge
     run: python3 dev/bin/pools.py tune
-    every: 10m
+    every: 7d                         # paused by the operator: it lowered the owner's pools on parks caused by main; pool-control replaces it
     timeout: 2m
     actions: [raise-pool]
     in: [goal.pools-earned.error, +auxiliary.first-pass-yield, -auxiliary.fix-rounds]
--- a/dev/prompts/plan_reviewer.md
+++ b/dev/prompts/plan_reviewer.md
@@ -22,6 +22,13 @@
 - The definition says what is true when done so a reviewer can check it; the files to touch and the size budget are
   plausible for one branch.
 
+# The bar
+
+Send a plan back (`fix`) only when building it as written would go wrong: the design is wrong (it would build the
+wrong thing, or a rule or formula in it is wrong), an acceptance test could not fail on the risk it names, or it is
+too big for one branch. Everything else - a sharper test, a missing edge case, wording - goes under `non_blocking`
+with a `merge`: those notes are appended to the definition, and the implementor must answer each.
+
 # Your answer
 
 End with exactly one fenced JSON block: `merge` approves the plan, `fix` sends it back to the planner, `park` stops it.
--- a/dev/prompts/planner.md
+++ b/dev/prompts/planner.md
@@ -48,6 +48,13 @@
      fails if the change falls into it (a test that can't fail is lesson-9);
    - `## Size budget`: `N net lines` of code outside `tests/` and `docs/`.
 
+# Keep it small (operator, 2026-11-20)
+
+Say **what** must be true, not **how**: name files and the behaviour, not function signatures or line numbers - the
+implementor reads the code. At most **8 acceptance tests**, each the one that would fail if the change were wrong;
+no test of something the code already guards. A size budget over 250 lines means split it. List only the review
+lessons that truly apply (two or three), each in one line. The definition should fit on one screen (about 60 lines).
+
 # Your answer
 
 End with the definitions, each in its own tag, and nothing after them:
--- a/dev/prompts/reviewer.md
+++ b/dev/prompts/reviewer.md
@@ -41,6 +41,14 @@
 Read the code; run single test files if you need to (`uv run python -m pytest -q tests/test_x.py`), never the whole
 suite. Change nothing.
 
+# The bar (operator, 2026-11-20)
+
+Block only for what would hurt main: a bug, a wrong behaviour, a missing test of the definition's risk, a security or
+data-loss hole, scope outside the definition, a scratch or stray file committed. Not blocking (put under
+`non_blocking`): main having moved since the build (the merge queue merges it and runs the suites again), a size
+overrun under 25% (say it), wording, docs polish, a finding the definition does not ask for. A finding you raised
+before and that is fixed is not raised again.
+
 # Your answer
 
 End with exactly one fenced JSON block:

```

## Size budget

0 net lines of core code (the model and dev/ only).

## Where it stopped

Nothing to change: every hunk of the diff above is already on main (2388572a "Bring the live instance's edits into
main" and the plan-review, pools and queue work before it). Some of it was reworked along the way:

- ergostat.yaml `opus: at-once: 24`; dev/factory.toml `kill_after = 6`, `suite_fix_rounds = 2`, `implementor_max = 9`,
  `reviewer_max = 6`; dev/model/budget.yaml `<= 3000`; interlock.yaml `<= 6`, `<= 3000`, `<= 40`; building.yaml
  pools 9 and 6; knowledge.yaml planner pool 12; pools.yaml `every: 7d`; reviewer.md's "The bar" and planner.md's
  "Keep it small": these are as in the diff.
- agents.py fetches `refs/remotes/<remote>/<base>`. queue.py fast-forwards to `<remote>/<base>` with `--ff-only` and
  runs the suites in threads. review.py's gate 1 says "is not on the branch". These are as in the diff.
- implement.py's KILL_HOURS and FAILS are now `[gates] build_hours = 12` and `build_failures = 6` in dev/factory.toml.
- pools.py's `tune` is paused by `PAUSED = True`. The batch tuning still runs.
- The plan review moved out of plan.py into dev/bin/planreview.py. It is advisory and never a gate, so the diff's
  `fix`-to-`merge` rewrite, plan.py's KILL = 4 and the review knowledge.yaml pool 8 no longer apply. Its findings are
  appended as "Notes from the plan review (answer each)". plan_reviewer.md says to block only for what would make the
  build go wrong.

Checked: tests/test_factory.py 52 passed, 2 skipped; ruff is clean. Not run: `ergostat check`, because this
session's shell refused the command. The factory's suites should run it. Committing was also refused, so this
section may be left uncommitted in the worktree.
