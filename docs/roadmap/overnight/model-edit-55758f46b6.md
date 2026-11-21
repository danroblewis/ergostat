# model-edit-55758f46b6: bring the model changes accepted in the instance into the repository

## Definition of done

The changes below, made to the instance's copy of the model while it ran 24756e50c5d3, are in the repository's model files, `ergostat check` is clean, and tests/test_factory.py passes.

```diff
--- a/dev/bin/resources.py
+++ b/dev/bin/resources.py
@@ -256,8 +256,12 @@
     def median(suite: bool, key: str, default: float) -> float:
         xs = [x[f"{key}_max"] for x in rows if (x.get("role") == "suite") == suite and f"{key}_max" in x][-20:]
         return statistics.median(xs) if len(xs) >= 3 else float(default)
-    return (median(False, "cpu", r.get("session_cpus", 0.5)) + median(True, "cpu", r.get("suite_cpus", 4)),
-            median(False, "memory", r.get("session_memory_gb", 1)) + median(True, "memory", r.get("suite_memory_gb", 4)))
+    # operator 2026-11-20: with machine-wide suite slots the suites are capped on their own, and the load read already
+    # holds the ones running: a new session adds only its own cost (counting a suite too held the pool at ~4 of 9)
+    suites = 0.0 if (cfg.get("suites") or {}).get("slot") else 1.0
+    return (median(False, "cpu", r.get("session_cpus", 0.5)) + suites * median(True, "cpu", r.get("suite_cpus", 4)),
+            median(False, "memory", r.get("session_memory_gb", 1))
+            + suites * median(True, "memory", r.get("suite_memory_gb", 4)))
 
 
 def setpoints() -> dict:
--- a/dev/bin/watch.py
+++ b/dev/bin/watch.py
@@ -114,7 +114,8 @@
         if g["state"] == "dead" and now - float(g.get("entered") or now) > 1800:     # (dead-letters parks it first)
             out.append(sit("dead", g["id"], f"{g['id']} is a dead letter: {str(g['fields'].get('last_error'))[:300]}",
                            g.get("entered")))
-        elif g["state"] == "parked" and now - at < s["parked"] * 3600 and branch(g) not in holders:
+        elif g["state"] == "parked" and now - at < s["parked"] * 3600 and branch(g) not in holders \
+                and not (g["fields"].get("deferred") or g["fields"].get("cancelled")):   # a coordinator's decision, not a stall
             out.append(sit("parked", g["id"], f"{g['id']} was parked: {str(g['fields'].get('where_it_stopped'))[:300]}", at))
     out += stuck(cfg, gaps, now)
     for i in sorted(opened, key=lambda i: float(i["fields"].get("recorded_at") or i.get("first") or 0)):
--- a/dev/knowledge/decisions.md
+++ b/dev/knowledge/decisions.md
@@ -27,3 +27,9 @@
   factory, pool.*
 - **Security effort goes where code nobody vouched for runs** (the sandbox, repair). For the owner's own tooling, review
   for correctness and these rules rather than hardening. *Areas: sandbox, repair, security, guard, container.*
+- **A branch carrying another gap's unlanded merge is continued, not rebased, once that merge lands on main.** Merging
+  main in makes the carried commits main's, and they drop out of the diff; history is never rewritten. While the other
+  work has not landed, the gap waits for it (a dependency), it is not rebuilt by hand. *Areas: factory, branch, queue,
+  manager.*
+- **Areas the coordinator deferred stay deferred** (a gap parked with `deferred: true`): no rebuild, continue or
+  re-plan is asked for them until the coordinator reopens the area. *Areas: manager, backlog.*
--- a/dev/model/knowledge.yaml
+++ b/dev/model/knowledge.yaml
@@ -338,7 +338,7 @@
     description: a session per gap in a read-only clone of main - its definition of done (acceptance tests, budget, risks from the lessons, files), a split into sub-gaps, or research questions first
     run: python3 dev/bin/plan.py
     prompt: dev/prompts/planner.md
-    takes: {kind: gap, at: [open, replan], to: [split, ready, replan, parked], unblocked: true, order: rank}
+    takes: {kind: gap, at: [open, replan], to: [split, ready, replan, parked], unblocked: true, order: rank, where: {continues: null}}   # a continued gap is the intake's
     pool: 12                           # operator: planners spend AI budget, not machine
     lease: {ttl: 60m, attempts: 2}
     timeout: 2h
--- a/dev/model/manager.yaml
+++ b/dev/model/manager.yaml
@@ -100,7 +100,6 @@
     run: python3 dev/bin/watch.py
     every: 5m
     timeout: 4m
-    goal: no-stuck-gaps
     out: flow.situations-found
 
   manage-when:

```

## Size budget

0 net lines of core code (the model and dev/ only).

## Where it stopped

Built. Main already had four of the five hunks, in later forms, so they were not applied again:

- `dev/bin/resources.py` `per_session`: a session is charged no suite cost when `[suites] slot` is set (main's `suite()`).
- `dev/model/knowledge.yaml` block `plan`: `where: {continues: null}` is in its `takes`.
- `dev/model/manager.yaml` `pipeline-watch`: no `goal:`; it reads `no-stuck-gaps` through `in:` (so it keeps its schedule).
- `dev/knowledge/decisions.md`: both decisions are there, as sections in main's later format ("A branch carrying another
  gap's merge is continued once that merge lands", "Deferred areas stay deferred").

`dev/bin/watch.py`: main skips parks whose `parked_for` is `deferred` or `cancelled`. The instance's change also skips a
park the coordinator marked with a `deferred: true` or `cancelled: true` field, which main still raised. That check is
now in the condition, reflowed onto the same two lines (0 net lines). The test
`test_dead_and_parked_gaps_are_raised_but_not_old_or_carried_on_ones` has two more parked gaps with those fields. It
fails with the check removed and passes with it. The dev/README sentence on the trigger says so too. Keeping main's
forms and adding only the missing field check was the most reversible choice.

Run: tests/test_factory_manager.py (18 passed), tests/test_factory.py (97 passed, 2 skipped), ruff clean. Not run:
`ergostat check` (the shell refused it). The model is read with no errors in
`test_the_model_has_the_block_its_kind_triggers_and_gated_actions`. The rest of the unit suite and the browser files,
and a merge with origin/main, are left to the queue.

After the fast suites: `unit` was reported failed, but its tail ends mid-run at 81% with no `F`, no error and no failure
summary. That looks like the run was cut off (a timeout or a kill), not a test failing. No failing test was named, so no
code was changed. On the branch again: tests/test_factory_manager.py 18 passed, tests/test_factory.py 97 passed and 2
skipped, ruff clean. The branch changes only `dev/bin/watch.py` (one condition), its test and a README sentence. Nothing
outside tests/test_factory_manager.py exercises them. Running `unit` again under the watchdog should show whether a real
failure exists. If it names one, that failure is the thing to fix.
