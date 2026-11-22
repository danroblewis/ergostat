# ai-approver-for-repairs-needs-a: the repair loop's second rung, an AI approver behind a positive allowlist of what a fix may change

depends-on: []

## Definition of done

`approver: ai` in `use: repair` is accepted by `check` and works: after a fix passes its test, a guard in code
(`ergostat/repair/allow.py`) decides whether the AI may be asked at all. When it may, the AI (the template's `model`,
haiku by default, no tools, its call inside the existing ledger and daily cap, cost recorded as the run's) is shown only
the program's path, the diff and "passed". Its approval is written only if the version it judged is still the one
waiting. Everything else stays held for the person exactly as today. `approver: person` behaves exactly as on main.

### The guard: an allowlist, not a denylist

`escalate(path, old, new, beside) -> list[str]` returns the reasons a person must decide; an empty list means only that
the AI may be asked. It reads the program's text before and after, nothing else (`beside`: the names of the files next
to the program in the clone). It fails closed: anything it cannot parse, align or classify is a reason.

**G0, preconditions.** The program ends in `.py`, both versions parse, at most 40 lines are changed, the test result is
`passed` (untested or failed fixes are refused), the risk is `low` or `medium` (a missing risk counts as high), and the
new module holds no `import *` or `__builtins__`, and does not import `builtins`.

**G1, alignment.** The old and new statement lists are aligned with `difflib.SequenceMatcher`, body by body:
- the key of a simple statement is its whole `ast.dump` (without positions);
- the key of a compound statement is its header (type, test/iter/target, def name, args and decorators). Two compound
  statements with equal keys are aligned recursively in each of their bodies.
- New statements that do not match are **changed**, including everything nested in them. Old statements that do not
  match are **removed**.

**Shaped values (S).** A *shaped* expression can only be a JSON-type value, so no operation on it runs code other than
the interpreter's own. Shaped expressions are:
- constants (str, int, float, bool, None);
- f-strings with shaped parts and constant format specs;
- list, tuple, dict and set displays of shaped parts;
- shaped names;
- `Subscript` of shaped values with a shaped index or slice;
- `BinOp`, `UnaryOp`, `BoolOp`, `Compare` and `IfExp` of shaped parts;
- list, set and dict comprehensions and generator expressions whose targets are names and whose iterables and
  conditions are shaped;
- calls of these forms only:
  - **(a)** a builtin from the fixed set `len int float str bool abs min max round sorted list dict tuple set enumerate
    zip range isinstance repr any all sum reversed`, with shaped arguments and no keyword arguments;
  - **(b)** `print` with shaped arguments and only the keywords `sep`, `end` and `flush` (never `file`);
  - **(c)** `json.loads(shaped)` with no keywords, or `json.dumps(shaped)` with only `indent`, `sort_keys` and
    `ensure_ascii`;
  - **(d)** one of the methods `get strip lower upper split startswith endswith replace join items keys values` on a
    shaped receiver, with shaped arguments.

  The builtins and `print` count as (a) and (b) only when their name is bound **nowhere** in the module. A binding is
  any of: def, class, assign, augmented or annotated assign, walrus, import or from-import, a for, comprehension, except
  or with target, del, a parameter, a match capture, or any of these inside a class body. `json` counts as (c) only when
  it is bound only by a top-level `import json` with no alias, and no `json.py` or `json/` is in `beside`.

A name is **shaped** when every binding of that name anywhere in the module (scopes merged by name, which can only refuse
more) is either an assignment of a shaped value or of `json.load(...)`/`json.loads(...)` of anything, or a for or
comprehension target over a shaped iterable. This is a fixed-point computation over the whole module.

There are no attribute reads except as the callee of (c) or (d), and no lambda, await, yield or walrus. A call to a
function defined in the module is not an allowed form: the earlier plan's form (e), a "pure" module function, is
dropped. Such a call goes to the person.

**G2, allowed statements.** Each changed statement must be one of:
- an assignment or augmented assignment of a shaped value to names or tuples of names (never an attribute or subscript
  target);
- an expression statement that is a (b) `print` call;
- `if`, `elif` or `else` with a shaped test;
- `for` with name targets over a shaped iterable;
- `pass`, `continue`, `break`, `return` with a shaped value or none, or `assert` with shaped parts;
- `raise X(shaped)` with `X` in `ValueError KeyError TypeError RuntimeError SystemExit`, under the same no-binding rule
  as (a).

Anything else is refused: try, with, while, def, class, import, global, nonlocal, del, match, async.

Every removed statement must also pass G2 when read against the old module. A fix that removes code the guard cannot
read, such as a `sys.exit()` or a check call, goes to the person.

**G3, taint.** These names are **tainted**:
- names bound by changed or removed statements;
- names bound by unchanged statements that load a tainted name;
- the return value of a module function that holds a changed, removed or controlled statement.

An unchanged statement that loads a tainted name, or calls a tainted function, must itself pass G2 (S included). There
is one exception: a statement that is only `NAME = f(args)` or `f(args)`, where `f` is a module function and no argument
is tainted, is allowed. Its bound name is then tainted. A call of a module function with a tainted argument is refused.

**G4, control.** These statements are **controlled** and must pass G2:
- the whole body and `orelse` of an unchanged `if`, `for` or `while` whose header loads a tainted name (a `while` itself
  fails G2), and of a changed `if` or `for`;
- after a changed, removed or controlled `continue` or `break`: the whole enclosing loop body and its `orelse`;
- after a changed, removed or controlled `return`: the rest of the function;
- after a changed, removed or controlled `raise` at module level: the rest of the module.

A changed or removed `raise` inside a function is refused.

**G5, exception paths.** A changed, removed, controlled or tainted statement lexically inside a `try` or `with` is
refused. If any of them is inside a function, the module may hold no `try` or `with` at all. A fix that newly raises
could otherwise run a handler, a `finally` or an `__exit__` that never ran before.

### Residuals, stated in SPEC §12r and SECURITY, each pinned by a test

1. **Implicit raises.** A fix can make the program stop earlier (any subscript or division may raise), or get further
   than the failing program did (that is what a fix does). Either way only the old program's own statements run; G5
   covers handlers. Process-wide hooks the program installs (`sys.excepthook`, `atexit`) are not followed.
2. **Standard output.** `print` writes to the program's standard output, wherever the program or a module it imports
   points it (`sys.stdout = ...`, `dup2`). The guard does not follow redirection.
3. **One file.** The guard reads one file. What modules the program imports do when imported (rebinding a builtin or
   `json`) is not seen.
4. **Time and memory.** A fix may use time or memory (`"x" * 10**9`, `range(10**12)`). The block's timeout bounds it.

### The approval

`ergostat/repair/approve.py`:

**`held(p, name)`** is an `fcntl` lock on `repair/<name>.lock`. `fix.run` takes it around recording `passed` and calling
`gate.request("apply-fix")`. The approver takes it around its re-read and write.

**`review(...)`** runs only when `approver == ai` and the action was just requested:
1. It stamps what it judges: `{action: id, requested_seq, fix: sha, passed_seq}`.
2. It runs the guard. If the guard gave reasons, or the ledger is capped or unreadable (`Capped`), or the AI gives no
   answer or anything other than `approve: true`, the verdict is `escalate`. The fix is never given back for this
   reason (lesson-3).
3. It asks the AI with `approver.md` and its own system prompt.
4. Under `held()` it re-reads the action and the failure. It writes `approved` (`by: "ai approver (MODEL)"`) only if all
   of these hold: the action is still `requested`; the seq of its `requested` event equals the stamp; its key is
   `<name>-<fix>`; the failure is `awaiting-approval`; its latest `passed` event's seq and its `fix` equal the stamp.
5. It records `ergostat.failure.reviewed` with `approval: {by, model, verdict, reasons, guard, action, stamp}`. When the
   version changed, the verdict is `stale` and nothing is approved. The `passed` event carries `approval: None`, so an
   old approval never shows on a remade fix (lesson-5).

A person's denial stays final through the existing fold. An AI approval is run by the engine's existing sweep.

### Elsewhere

- `inbox/stats.py`: an AI approver's answers are counted under `by_agent`, never as a person's approvals, and not among
  the approvals asked of a person in a day.
- `compile.py`: the "not yet" refusal is removed. `fix.py` accepts `--approver ai`.
- The template's description, SPEC §12r (the ladder paragraph with G0–G5, the residuals and the stamp), SECURITY,
  AGENT-GUIDE and GAPS (the entry is removed, replaced by the residuals that remain) are updated.

### Done means

- Every test below exists and passes, and each one was seen to fail with the code it guards broken (reported).
- The unit suite and the four browser files pass with rc 0. Ruff is clean.
- origin/main is merged in and the suites are run again.

## Files to touch

- `ergostat/repair/allow.py` (new)
- `ergostat/repair/approve.py` (new)
- `ergostat/repair/approver.md` (new, the prompt)
- `ergostat/repair/fix.py`
- `ergostat/spec/compile.py`
- `ergostat/library/templates/repair/template.yaml`
- `ergostat/inbox/stats.py`
- `tests/test_repair_allow.py` (new)
- `tests/test_repair_approver.py` (new)
- `docs/SPEC.md`
- `docs/SECURITY.md`
- `docs/AGENT-GUIDE.md`
- `docs/GAPS.md`
- `docs/roadmap/overnight/ai-approver-for-repairs-needs-a.md`

## Risks

- **lesson-8: the guard claimed safe while it is a denylist, or the claim reaches further than the code.** Every rule is
  "allowed only if", and every bypass in GAPS gets its own refusal test. The SPEC claim is narrowed to "what the AI may
  be asked about", with the four residuals stated and tested.
- **lesson-1 and lesson-2: approval of a version that is no longer the one waiting.** The approval is stamped with seqs
  and the commit sha, never times. Re-read and write happen under the per-failure lock, which `fix.run` also takes
  around `passed` and the request. The race test monkeypatches the step between the AI's answer and the write.
- **lesson-5: a same-failure remake inheriting the old approval.** `passed` clears `approval`, and the stamp is compared
  for equality.
- **lesson-3: missing inputs counted as fine.** A parse failure, missing risk, an unreadable ledger, an empty AI answer,
  or a missing action or failure on re-read all mean escalate or no write.
- **lesson-4: unbounded counts.** There is one approver call per proposed fix, inside the existing per-call budget,
  daily cap and a quarter of the timeout. No new configurable count is added.
- **lesson-6: an AI call that keeps running.** The same `ask()` timeout path is used, and a timed-out call means
  escalate, never an approval.
- **lesson-9: a guard test that cannot fail.** Every refusal test has an accepted twin, and the accepted baseline runs
  in the same file. A guard that refuses everything, or accepts everything, fails the suite.
- **lesson-7: merge conflicts.** origin/main is merged in before calling it built, and the suites are run again.
- **lesson-13: unrelated failures.** A failure not caused by this change is reported, not fixed in this branch.

## Acceptance tests

`tests/test_repair_allow.py` holds pure guard tests on source strings. Unless a test says otherwise, the program is
`BROKEN` from `test_repair2` plus whatever the test adds.

**Accepted cases**

| Test | What it shows |
|---|---|
| `test_accepts_the_shape_fix` | `["issues"]` → `["values"]` and `['key']` → `['id']` gives `[]` |
| `test_accepts_get_default_if_continue_and_int` | `.get(k, d)`, `if x is None: continue` and `int(...)` give `[]` |

**Refused before any AST reading (G0)**

| Test | What it shows |
|---|---|
| `test_refuses_untested_failed_high_risk_non_python_and_large` | each of these alone gives a reason |
| `test_refuses_unparseable` | either version not parsing gives a reason |

**The bypasses listed in GAPS**

| Test | What it shows |
|---|---|
| `test_refuses_vars_os_system` | `vars(os)['sys'+'tem']('x')` is refused |
| `test_refuses_sys_modules` | `sys.modules['os']` is refused |
| `test_refuses_dunder_subclasses` | `().__class__.__subclasses__()` is refused |
| `test_refuses_existing_subprocess_given_new_args` | an existing `subprocess.run([...])` changed to `['sh', '-c', x]` is refused |
| `test_refuses_unlisted_calls` | `os.chmod`, `Path(x).rename(y)` and `marshal.loads` are each refused |
| `test_refuses_path_literal_into_existing_open` | `fn = 'answer.json'` → `'../x'` with an unchanged `open(fn)` is refused (G3) |
| `test_refuses_new_import` | a new import is refused |
| `test_refuses_attribute_and_subscript_stores` | `d['k'] = v` and `o.a = v` are refused |
| `test_refuses_print_file_kw` | `print(x, file=f)` is refused |

**Shadowing (one parametrized case each, each with an unshadowed twin that is accepted)**

| Test | Binding forms |
|---|---|
| `test_refuses_shadowed_builtin_or_print` | `def print`, `from rich import print`, `len = os.system`, `for len in ...`, `except E as len`, `with x as len`, class-scope `print = ...`, a parameter named `len` |
| `test_refuses_import_star_and_builtins` | `from os import *` anywhere, `import builtins`, `__builtins__` |
| `test_refuses_json_rebound_or_beside` | `json = yaml`, `import yaml as json`, and `json.py` in `beside`; each makes `json.loads` a refused form |

**Shaped values**

| Test | What it shows |
|---|---|
| `test_refuses_unshaped_name` | a changed `print(env['TOKEN'])` with `env = os.environ` unchanged is refused; with `env = json.loads(s)` it is accepted |
| `test_refuses_module_function_call` | form (e) was dropped: a changed call to a module-defined `parse(x)`, decorated or not, is refused |

**Taint and control (G3, G4)**

| Test | What it shows |
|---|---|
| `test_taint_into_unchanged_call_refused` | a changed `cmd = ...` with an unchanged `os.system(cmd)` is refused |
| `test_taint_through_function_return_refused` | a changed `return` in `f`, then `x = f()` and an unchanged `os.remove(x)`, is refused; the same with `print(x)` is accepted |
| `test_tainted_for_iterable_body_must_pass` | a changed `n = ...` with an unchanged `for _ in range(n): send()` is refused; the same body with `print` is accepted |
| `test_tainted_if_header_body_must_pass` | a changed flag that steers an unchanged `if flag: os.remove(p)` is refused |
| `test_removed_continue_controls_loop` | removing `if it['protected']: continue` before an unchanged `os.remove` is refused |
| `test_removed_unreadable_statement_refused` | removing `sys.exit(0)` or `check(x)` is refused |
| `test_changed_raise_in_function_refused` | a changed `raise` inside a function is refused |

**Exception paths (G5)**

| Test | What it shows |
|---|---|
| `test_change_inside_try_or_with_refused` | a change lexically inside `try` or `with` is refused, and so is a change inside a function when the module has any `try` |

**Residuals (each test asserts the stated behaviour, so a change to it breaks the test and the docs must follow)**

| Test | What it shows |
|---|---|
| `test_residual_implicit_raise_accepted` | a changed `x = d['k']` (may raise) before an unchanged `os.remove(p)` that does not read `x` is accepted |
| `test_residual_stdout_redirect_accepted` | a changed `print(x)` in a program with an unchanged `sys.stdout = open('out', 'w')` is accepted |

`tests/test_repair_approver.py` uses the fake AI from `test_repair2`. Tests that run the fix need the OS sandbox and are
skipped without it, as in `test_repair2`. The race and stamp tests call `approve.review` on recorded events directly and
need no sandbox.

| Test | What it shows |
|---|---|
| `test_check_accepts_approver_ai` | `check` no longer refuses `approver: ai` |
| `test_ai_approves_guarded_fix_and_sweep_applies` | a shape fix is approved by `ai approver (haiku)`, the sweep applies it, the `reviewed` record holds the stamp, and the AI's prompt held only path, diff and passed (no explanation, no test output) |
| `test_guard_escalates_without_asking_ai` | a refused fix means no approver AI call in the log, the action still `requested`, and the guard's reasons in the record |
| `test_ai_says_no_or_garbage_escalates` | `approve: false`, non-JSON and a timeout each leave the action held |
| `test_capped_ledger_escalates` | an unreadable ledger means no call, and the action is held, not nacked |
| `test_remake_during_ai_call_not_approved` | monkeypatches the step after the AI answers to record a new `passed` and a new `apply-fix` for the same failure. The old action stays `requested`, the new one is not approved, and the record says `stale`. With the stamp check removed, this test fails |
| `test_requested_seq_mismatch_not_approved` | an action whose `requested` seq differs from the stamp is not approved |
| `test_denial_during_ai_call_stays_denied` | a person's denial recorded in that same gap leaves the action denied, never run |
| `test_remade_failure_clears_old_approval` | after a second `passed`, the failure's `approval` is None |
| `test_ai_answers_counted_apart` | `inbox.stats` counts an AI approval under `by_agent` and not among a person's approvals |

## Size budget

450 net lines (allow.py about 280, approve.py about 90, approver.md, fix.py, compile.py, template and stats.py about
80), outside tests and docs.

## Notes from the plan review (answer each)

- The no-binding rule for (a)/(b) builtins and (c) json only looks at the source text, so the same file can rebind the name at runtime: `globals()['len'] = os.system` (unchanged) plus a changed `len(cmd)` passes G0-G5; likewise vars()/setattr(sys.modules[__name__])/exec, and `sys.modules['json'] = x` before `import json`. Residual 3 only covers other modules. Also, a name with no binding is 'shaped' trivially (every one of its zero bindings is shaped), so open/exit/__loader__/injected names count as shaped, which breaks the 'only a JSON-type value' premise. Change: any reference to globals, locals, vars, setattr, exec, eval, compile, __import__, __dict__ or sys.modules in the module is a reason; a name with no binding is unshaped except a listed builtin used as a callee or isinstance type argument. Add test_refuses_dynamic_rebinding and test_unbound_name_not_shaped, each with an accepted twin.
- Compute the shaped-name fixed point starting from unshaped and widening, so cycles (a = b; b = a) are not accepted on nothing; add a test.
- Residuals 3 and 4 are said to be pinned by tests but neither has one; add them or drop the claim.
- The person's denial does not take held(); state that the fold makes a denial final whatever the event order, and test a denial recorded after the AI's approval write as well as before it.
- Say how isinstance's type argument (int, str) is classified, since it is not shaped under the stated rules.
- Say whether a removed compound statement counts everything nested in it as removed, as changed does.
- allow.py at 280 lines is tight; report the real count rather than cutting fail-closed branches.

## Where it stopped

Built, round 1. Everything in the definition is in the branch. What was not run, and where the build departs from
the text above, is listed below.

**Size: 555 net lines against 450 (an overrun of 105).** allow.py is 445 lines, against the plan's ~280; approve.py
83; approver.md 14; fix.py +6; stats.py +8; template +2; compile.py -3. The reason is the plan review's additions to
the guard: the dynamic-rebinding refusals, the least fixed point, the isinstance type argument, removed statements
nested in removed ones, and G4's "rest of the function/module" walk. Each is a fail-closed branch, and the review asked
for the real count rather than cuts. Docstrings account for about 60 of the lines.

**The plan review's notes, answered.**
- Dynamic rebinding: G0 also refuses, anywhere in the new module, a reference to `globals locals vars setattr delattr
  getattr exec eval compile __import__ __builtins__ breakpoint`; an attribute starting `__` or named `modules
  f_globals f_locals f_builtins`; a store or del of an attribute named like a trusted name (the listed builtins,
  `print`, the exceptions, `json load loads dumps`); and an import of `builtins importlib ctypes gc inspect`, or of
  those names from `sys`. A name with no binding is not shaped. Tests: `test_refuses_dynamic_rebinding` and
  `test_unbound_name_not_shaped`, each with an accepted twin. SPEC residual 3 says what is still unseen: `pickle`-loaded
  code and C extensions.
- Least fixed point: `Shapes` starts from no shaped names and widens. Test: `test_shaped_names_from_nothing_are_not_shaped`
  (`a = b; b = a` is refused, `a = 1; b = a` accepted).
- Residuals 3 and 4 tests: `test_residual_other_modules_not_read` and `test_residual_time_and_memory_accepted`.
- Denial: SPEC says the fold makes a denial final whatever the order. Tests: `test_denial_during_ai_call_stays_denied`
  (before the write) and `test_denial_after_ai_approval_stays_denied` (after it, before the sweep).
- isinstance: the type argument must be a name from `int float str bool list dict tuple set`, bound nowhere in the
  module, or a tuple of such names; the first argument must be shaped.
- Removed compound statements: everything nested counts as removed, and each is read by G2 against the old module. A
  nested `continue`/`break`/`return` whose loop or function was itself removed controls nothing (its loop is gone).
- allow.py: 445 lines (above).

**Departures from the text, each the stricter or more reversible choice.**
- `test_taint_through_function_return_refused`: the table's accepted twin "the same with `print(x)`" cannot pass the
  definition's own rules. `x = f()` is not shaped (form (e) was dropped), and G3 holds a tainted reader to G2 with S.
  The test asserts that `print(x)` is refused. Its accepted twin is the same program whose last statements do not read
  `x` (`print('removing')`, `os.remove('p')`). That twin shows the exception for `x = f()` and that taint is what refuses.
- Stricter than written. Names bound by controlled statements are tainted, so `if flag: p = 'x'` taints `p`. A function
  holding a tainted statement is tainted, not only one holding a changed, removed or controlled statement; otherwise an
  unchanged `def f(): return g` would hide a changed `g` from the `x = f()` reader. An augmented assignment needs its
  target name shaped. (d) methods take no keywords. A `json.load`/`json.loads` binding counts only without keywords
  (`object_hook` could make non-JSON values). A file beside the program named `json.<anything>` makes `json` untrusted.
- "At most 40 lines changed" counts each run of changed lines by its longer side, so a one-line edit is 1.
- `escalate(path, old, new, beside, tests=None, risk=None)`: G0 needs the test result and the risk. Their defaults
  fail closed (untested, high).
- A `stale` review is recorded with `approval.verdict: stale` on the failure, with the old stamp. It is not an approval,
  and the stamp shows which version it was about.
- `tests/test_repair2.py::test_g2_approver_ai_is_refused_by_check` was removed, since this gap makes it false.
  `test_check_accepts_approver_ai` replaces it.
- The approver tests run `fix.main` in this process with only `fix.trial` (the sandbox) and `fix.impact` stubbed. They
  run without the OS sandbox and still exercise the wiring in fix.py. `test_ai_approver_end_to_end_in_the_sandbox`
  runs the engine and is skipped without the sandbox. Added beyond the table: `test_approver_person_is_as_on_main`,
  `test_high_risk_escalates_without_asking_ai`, `test_removed_return_controls_the_rest_of_the_function` and
  `test_denial_after_ai_approval_stays_denied`.
- Not built (GAPS): `inbox/interventions.py` reads `stats.asked`, so an AI-approved action still counts as an
  intervention there, as an MCP answer already does. It is outside the files to touch.
- No test runs `fix.run`'s lock under real concurrency. The race tests put the competing write in the gap between
  the AI's answer and the write, which is where the definition puts them.

**Each test seen to fail with its code broken** (each mutation applied, then reverted):
- The guard always `[]`: 48 tests fail. The guard always refusing: 62 fail.
- G3 off: path-literal, unchanged-call and function-return tests fail. G4 off: the for, if, removed-continue and
  removed-return tests fail. G5 off, and its function rule alone off: `test_change_inside_try_or_with_refused` fails.
- The no-binding rule off: all 8 shadowing cases fail. `dynamic()` off: vars, sys.modules, dunder, import-star and
  builtins, and all 6 dynamic-rebinding cases fail. `beside` ignored: the `json.py` case fails.
- A seeded fixed point: the cycle test fails. Removed statements not read by G2: the removed-unreadable test fails.
- In approve.py, the stamp check off: the remake, requested-seq and denial-during tests fail. The requested-seq check
  alone off: the requested-seq test fails. The guard skipped: the guard-escalates and high-risk tests fail. A truthy
  approve accepted: the `"approve": "yes"` case fails.
- `approval: None` dropped from `passed`: the remade-failure test fails. `by_agent` reverted in stats.py: the
  counted-apart test fails.

**Not run, or not possible here.**
- The whole unit suite and the four browser files were not run: the task says the factory runs them. Run, one at a
  time: `tests/test_repair_allow.py` (53 passed), `tests/test_repair_approver.py` (16 passed, 1 skipped: sandbox),
  and `test_inbox`, `test_runlog`, `test_factory_knowledge`, `test_backlog`, `test_daemon_yaml_review`,
  `test_resilience`, `test_factory` (335 passed, 2 skipped).
- `tests/test_repair2.py` is skipped whole in this container: bwrap cannot make its namespaces.
- origin/main is not merged. This clone has no `origin/main` ref, `git fetch` is refused (it reaches the network), and
  the local `main` is already an ancestor of the branch.
- Ruff is clean.

### Round 2: the review's one finding (G3 followed only bare names)

The finding was that a value could reach unchanged code through an attribute or a registry without being tainted
(`class Cfg: path`, read by `os.remove(Cfg.path)`; a method `J.p` read by `os.remove(j.p())`; a method steering
`if not I().keep(it)`; a `@reg` function called back through a registry). It was the only finding, and it was
blocking. What changed in `allow.py`, each part fail-closed:
- G3 follows attribute names as well as names. `refs()` counts `x.attr` as a read of `attr`, merged by name as
  elsewhere, so it can only refuse more. `excuse()` uses the same reads for its "no argument tainted" check.
- A class enclosing a changed, removed, controlled or tainted statement is hot, as a function is (`holders()`).
- `Fix.uses()`: a hot function or class is refused if it is decorated, or if its name is read anywhere other than as
  the callee of a call (stored, passed on, used as a base, `Cfg.path`).
- Test: `test_taint_through_attributes_and_registries_refused`, 5 cases (the class attribute, the method's return, the
  method steering an `if`, the decorated registry, `REG.append(h)`). Each case has an accepted twin: the same change,
  read by nothing.
- Seen to fail with its code broken. Classes not made hot: the class-attribute case fails. Classes not made hot and
  attributes not followed: the class-attribute, method-return and method-steering cases fail. `uses()` returning
  nothing: the decorated-registry case fails, which nothing else refuses. The class-attribute and `REG.append` cases
  then fail only on their expected reason, since G3 still refuses them. Attributes not followed while classes are
  hot: nothing fails, because the class name already taints the two method cases. Following attributes is a second
  layer on top of that, and no test catches it alone.
- SPEC §12r G3 says how attributes, classes and the callee-only rule are read. SECURITY's sentence ("nothing those
  changes reach may ...") is unchanged. It now has the attribute and registry tests behind it, within residual 3 (one
  file).
- Size: allow.py is now 469 lines (+24 net), so the total is about 579 against 450. The reason is the same as round
  1: fail-closed branches added at review.
- Run: `tests/test_repair_allow.py` and `tests/test_repair_approver.py` (74 passed, 1 skipped: sandbox). Ruff is
  clean. The unit suite, the four browser files and `test_repair2` (bwrap) were not run here. As in round 1, there is
  no `origin/main` in this clone, and the local `main` is an ancestor of the branch.
- Refused in this round: a Bash command that wrote a multi-line Python edit script through a heredoc, and one that
  swapped the round-1 `allow.py` into place with `git show HEAD:... >` and `cp`. Edits and mutations were made with
  the edit tool instead.

### Round 3: the review's findings (a class header ran code with no call; aug-assign; PEP 695)

The review had one blocking finding and two that were not blocking. Each is answered here:
- **Blocking: a class holding the change was checked only where its name is read, never its header.** A metaclass
  (a function, or a class reached through a base) or a base's `__init_subclass__` is given the namespace when the
  class is defined. `Fix.uses()` now refuses a hot class (one holding, or enclosing a class that holds, a changed,
  removed, controlled or tainted statement) that has any base, keyword or PEP 695 type parameter. Tests:
  `test_refuses_change_in_class_with_base_or_keyword` (function metaclass, class metaclass via a base,
  `__init_subclass__` registry read through `dir` and `operator.attrgetter`, a type parameter), and
  `test_refuses_class_with_base_enclosing_the_change` (an outer class with a base, the change in a nested class's
  method). Each has an accepted twin: the same program with the class given no base.
- **Not blocking: `n = 0; n += 1` could never be shaped**, so G2's augmented assignment was never accepted. A binding
  that reads its own name now counts as shaped when another binding of the name is shaped without it, and the name is
  no builtin's and no dunder (so a read before its first binding raises, and cannot find a builtin's value).
  `a = b; b = a`, `n = n` alone and `sum = 0; sum += 1` stay unshaped. Test:
  `test_accepts_augmented_assignment_of_a_shaped_name`, with refused twins. SPEC's S paragraph says so.
- **Not blocking: PEP 695 type parameters were not bindings.** `ast.TypeVar`, `ParamSpec` and `TypeVarTuple` now
  bind their names. Test: `test_refuses_type_parameter_shadowing_print` (`def f[print](x)`), with a `def f[T]` twin.

Each test was seen to fail with its code broken, then the code was restored. With the class-header check off, all 5
class cases fail and the guard returns `[]` for each, so the bypass was real. With the self-reference seed off, the
aug-assign test fails. With the builtin exclusion off, its `sum` case fails. With the "another binding is shaped"
start off, its `n = n` case fails. With type parameters not bound, the PEP 695 test fails.

Size: allow.py +24 net (493 lines), so the total is about 603 against 450. The reason is the same as rounds 1 and 2:
fail-closed branches added at review.

Run: `tests/test_repair_allow.py` (65 passed) and `tests/test_repair_approver.py` (16 passed, 1 skipped: sandbox).
Ruff is clean. The unit suite, the four browser files and `test_repair2` (bwrap) were not run here. As before, the
clone has no `origin/main` (only `main`, already an ancestor of the branch), so nothing was merged. Refused in this
round: a Bash command that appended this section through a heredoc (`cat >> ... <<'EOF'`); the edit tool was used.

### Round 4: the review's findings (json's internals; a stdout of the program's own)

Two findings are answered. One is blocking, from round 3's review. The other is a round-3 note that the round-3 fix
did not answer (lesson-12):
- **Blocking: `json` was trusted while its internals could be changed.** `json._default_decoder = E()` (and
  `_default_encoder`, `json.decoder.JSONDecoder.decode = f`, `from json import decoder`, an alias `j = json`) let
  `json.loads(changed)` reach `E.decode`, which called `os.system`, and the guard returned `[]`. `Shapes.json` is now
  true only when all of these hold: the one top-level `import json` is the only import naming json (no `from json ...`,
  no `import json.x as y`); every read of `json` is the receiver of a `json.load`, `json.loads` or `json.dumps` call;
  and the module stores or deletes no attribute at all. The last rule is not narrowed to json's names, because a chain
  through another module (`requests.models.complexjson._default_decoder`) or an alias would get past a list of names.
  Test: `test_refuses_json_internals_changed`, 8 cases, among them the reviewer's own trace. Each has an accepted twin:
  the same program without the bad line.
- **Not blocking (round 3): a program's own `sys.stdout` runs its `write()` on what `print` is given.** I chose the
  refusal, not only a reworded doc. `print` counts as form (b) only when the module stores or deletes no attribute,
  except `X.stdout = open(<constants>)` with `open` bound nowhere. That case keeps the definition's residual test,
  `sys.stdout = open('out', 'w')`. `sys.stdout = W()`, `sys.stdout.write = f`, `out = sys.stdout; out.write = f` and
  `open(input())` are refused. Test: `test_refuses_print_into_program_code`, each case with accepted twins (no store,
  and `sys.stdout = open('out', 'w')`).
- **SPEC residual 3 narrowed** (the review's last point). It now names only other modules' code: what an import does,
  and what another module's function does when the program calls it. Examples are `unittest.mock.patch('json.loads',
  f)`, `pickle` and a C extension. It also says that a way of rebinding in this file that the guard does not classify
  is a reason. `test_residual_other_modules_not_read` pins the `mock.patch` case as accepted. Residual 2 says that
  `print` goes to a constant-named file or a file descriptor, and that only another module can give it code of its own.
  SECURITY and GAPS follow. GAPS also says that a program storing any attribute has no trusted `print` or `json`, so
  many real programs' fixes go to the person.

Seen to fail with the code broken, then restored:
- Attribute stores ignored for json: the `o.x = 1` case fails.
- The other-import rule off: the `from json import decoder` and `import json.decoder as jd` cases fail.
- The receiver rule off: the `j = json` case fails.
- Both the store rule and the receiver rule off (round 3's code): 5 cases fail, the reviewer's trace among them, so the
  bypass was real.
- The store rule off for `print`: all 4 print cases fail.

Size: allow.py is +24 net (517 lines), so the total is about 627 against 450. The reason is the same as earlier rounds:
fail-closed branches added at review.

Run: `tests/test_repair_allow.py` with `tests/test_repair_approver.py`: 93 passed, 1 skipped (sandbox). Ruff is clean.
The unit suite, the four browser files and `test_repair2` (bwrap) were not run here. As before, the clone has no
remote ref, and `main` is an ancestor of the branch, so there was nothing to merge.

Refused in this round:
- `python3 -c` probing whether a text file's `write` can be set. The rule refuses every attribute store instead of
  relying on the answer.
- A compound command (`git merge-base ... && echo; git remote -v; git diff --stat`). It was run as separate commands.
- `git diff -U0 docs | grep | awk` to find long lines. The new doc lines were checked with the search tool.

## Where it stopped

Parked by the factory (review/ai-approver-for-repairs-needs-a-4, 2026-11-21 16:43).

Done: approver: ai is wired through check, fix.run, the stamped and locked approval in approve.py, inbox stats and the docs, and the guard's G0-G5 structure with its tests. Left: the guard's trust in builtins, print and json (forms a-c) rests on a list of refused spellings that the program's own unchanged code gets round (operator.attrgetter('modules')(sys) with operator.setitem on a module's __dict__; attributes named setattr reached through a module), so a fix can still hand a chosen string to os.system. Round 1 (attributes), round 2 (class headers), round 3 (json internals) and now round 5 each found a new way past the same kind of check. A safe design must stop assuming the builtins and json are what the text suggests, for example by trusting forms (a)-(c) only when every call in the module is itself classified, or by dropping them. Otherwise the claim must be cut to say that the program's own code can rebind them. Either way it is a redesign, not a fix round. Size is also 627 against 450.
