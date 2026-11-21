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
