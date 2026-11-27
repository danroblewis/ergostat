# Claims and trust

What a block says it did is a sensor reading like any other, and only as good as the block's honesty. A run that
says "tests pass" while a pipe hid their failing exit code misleads every loop that reads it, and the owner. So in
ergostat a block's report is a **claim**, and ergostat checks it by itself after the run, against the record (what
ran, what moved, which state an item is in) and the world (the tests run again, the repository read). Each block
earns a **trust**: how far its claims held, as a measure a goal can read. The format is in `docs/SPEC.md` §12g
(`ergostat help spec`); this page is how to use it. The screenshots are from a run of `examples/image-squeeze` with
its stand-ins and a planted lying developer (`FACTORY_LIE=1`).

| Your question | Where |
|---|---|
| [How does a block say what it did?](#saying-what-was-done) | its output lines |
| [What does ergostat check, and how?](#the-checks) | after every run |
| [How do I declare my project's tests?](#declaring-the-tests) | `claims:` in the YAML |
| [Where do I see the verdicts?](#where-it-shows) | Items → `ergostat.claim`, a claim's page, `ergostat claims`, needs attention |
| [How do I hold a block to it?](#trust-as-a-goal) | `ergostat.trust.*` measures, a goal |

## Saying what was done

A block prints one JSON line per claim, with its other output lines:

```json
{"claim": {"says": "tests pass", "about": "hypothesis/3"}}
{"claim": {"says": "submitted hypothesis/3", "about": "hypothesis/3", "check": {"state": "testing"}}}
```

`says` is the claim in words. `about` is what it is about: an item id, a part (`stock.queue`), a file, a commit
(`{"commit": "1a2b3c", "repo": "run/product"}`), a folder (`{"dir": "build"}`), a run. `check` says which check
judges it, when its words do not: `tests`, `changed`, `state` (with the state), `exit` (with the code), `level`
(with the level), or a check the project declares. An AI block's prompt asks for the same lines; ergostat's own
footer for `ai` blocks shows the form. Say only what was seen to happen: a claim the record contradicts is a finding
against the block.

A claim is never checked by a command it names itself (`"check": {"run": "true"}` is ignored, and the evidence says
so): what checks a claim belongs to the model, not to the claimant.

## The checks

Run by ergostat after the run ends, one claim at a time (the block is not run again until they are done):

| Check | For a claim like | Verified when |
|---|---|---|
| `tests` | "tests pass", "all tests passing" | the project's test command, run by ergostat where the claim says (a folder; a copy of a commit, or of the commit or branch its item names), exits 0. Without a declared command, the latest `tests.ran` / `tests.passed` / `tests.failed` event in the record |
| `changed` | "changed squeeze.py", "fixed stock.x" | git shows the file changed during the run (or in the commit named); a part: a change written to the model touches it; a commit alone: it exists |
| `state` | "submitted hypothesis/3" with `{"state": "testing"}`, "ticket/12 is done" | the item, folded, is in that state, or moved into it since the run began |
| `exit` | "the command succeeded" | the run's recorded exit code is 0 (or the code claimed) |
| `level` | "the queue is down to 3" with `{"level": "<= 3"}` | the part's latest reading is within the level |
| declared | "lint is clean" | the command the project declares for that kind exits 0 |

A claim no check knows, or one its check cannot run (no test command and no test run recorded, no reading yet, a
command that times out), is **unchecked**, with why. Unchecked is recorded and never counted as trust.

**Why the tests are run again.** This project's own history had it: an AI agent ran `pytest | tail -n 3`, saw the
summary scroll by, and reported the tests passed. The pipe's exit code is `tail`'s, so the run exited 0 and an
exit-code check agrees with the claim. Only running the declared test command catches it.
`tests/test_claims.py::test_a_pipe_that_hid_a_failing_exit_code_is_caught_by_running_the_declared_tests` is that
case, exactly: the exit check verifies "the command succeeded", and the tests check contradicts "tests pass" with
pytest's own output as the evidence.

## Declaring the tests

```yaml
claims:
  tests:
    run: '"$ERGOSTAT_ROOT/bin/py" test_squeeze.py'   # the project's test command
    in: run/product                                  # where it runs, and the repository a commit is taken from
    timeout: 3m
  lint:                                              # a kind of claim of the project's own
    says: "lint (is )?clean"
    run: ruff check .
```

A claim about a commit, or about an item whose fields name a `commit` or a `branch` (image-squeeze's hypotheses
name their branch), is checked on a copy of that revision exported into a scratch folder: nothing is checked out,
the working tree is left alone. The command's environment carries `ERGOSTAT_ROOT`, the model's folder, for a command
that needs the project's own tools from inside the copy.

## Where it shows

**Items → `ergostat.claim`**: every claim, with what it says, what it is about, who made it, which check judged it
and the verdict; under the table, **Trust**: per block, per rung and per model, the claims made, verified,
contradicted and unchecked, and the share contradicted.

![Items: the claims](screenshots/claims/items-claims.png)

![The trust table under them](screenshots/claims/trust.png)

**A claim's page** (click a row): the verdict first, with the evidence (the command, the commit it ran at, its exit
code, the end of what it printed), then its fields and their history.

![A contradicted claim](screenshots/claims/claim-contradicted.png)

**Needs attention** (the Diagram's list, `ergostat`): an agent whose claims were contradicted in the window, as
bad, with the latest one's reason. **Findings** (`ergostat findings`, the MCP `findings`): `contradicted-claim`,
about the block.

![Needs attention](screenshots/claims/attention.png)

**The command line**: `ergostat claims` (the trust table and the latest contradicted claims), `ergostat claims ID`
(one claim with its evidence), `ergostat claims --check` (check what was made and left unchecked when ergostat
stopped), `ergostat item --projection ergostat.claim`; for an AI agent, the MCP tool `trust`.

## Trust as a goal

Trust is a set of built-in measures, read like the model's own (`ergostat.model.fit`), each over the last week:
`ergostat.trust.contradicted` (the share of checked claims contradicted), `.contradictions`, `.verified`,
`.unchecked` and `.claims` (counts). `@WHO` narrows one to a block (`@developer`), a rung (`@rung:ai`) or a model
(`@model:haiku`). A sensor reads one on an auxiliary or a stock, so a goal holds it:

```yaml
auxiliaries:
  developer-contradicted:
    unit: share
    driven-by: +stock.contradicted-claims
    sensor:
      builtin: ergostat.trust.contradicted@developer
      every: 30s
goals:
  developer-honest:
    auxiliary: developer-contradicted
    hold: "<= 0.1"
```

and the claims are counted like any items (`projection: ergostat.claim, state: contradicted`), so their flow is in the
model too (image-squeeze's `contradicted-claims` and `claims-contradicted`). Nothing in image-squeeze acts on the
goal (`check` says so: missing feedback): nothing makes an agent truthful, and a loop that reads trust, such as one
that sends a less trusted block's work to a deeper review, is for a project to design.

## In image-squeeze

The developer, a stand-in or a Claude Code session (`prompts/developer.md`), ends every run with its claims: "tests
pass" about its hypothesis (ergostat runs squeeze's tests on the hypothesis's branch, in `run/product`) and
"submitted hypothesis/N" (the hypothesis is testing) or "abandoned hypothesis/N" (dropped). A Claude session's
claims carry the session and its model (`bin/session.py`), so trust is kept per model as well.

`FACTORY_LIE=1 ergostat run` plants a liar: on every other hypothesis the stand-in writes a test that fails, runs the
tests through `tail` (so it sees an exit code of 0), and claims the tests pass and that it submitted, whatever
`submit` said. `submit` runs the tests itself and abandons the hypothesis; ergostat's checks contradict both claims:
the tests fail on the branch, and the hypothesis is dropped, not testing.

Measured (2026-11-17, stand-ins, about eight minutes each): with `FACTORY_LIE=1`, 16 claims, 8 verified and 8
contradicted: every lie told (two claims on each of hypotheses 1, 3, 5 and 7) caught, every true claim verified,
none unchecked; `developer-contradicted` read 0.5 and the goal was off. Without it, 10 claims, all verified.
