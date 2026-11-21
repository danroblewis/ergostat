# ai-call-failures-are-failures: a failed AI call is recorded as failed and charged

depends-on: []

Audit of `ergostat/numbers/modeller.py` `call()`: it ignores the process's exit code and the response's `is_error`, and a missing `total_cost_usd` becomes $0. Demonstrated with a stand-in: during a 429 outage each run recorded $0, used up a try, and the requests ended `held` with "the ai tier proposed nothing", the 429 appearing nowhere. With a cap fitting one call, a response with no cost allowed 3 of 3 calls.

## Definition of done
- A non-zero exit, `is_error`, or a missing or invalid cost returns an `error` carrying what the call said, charged at the reservation (`unsaid`), as a timeout already is.
- An errored call does not use up a request's tries and never reads as "proposed nothing". The error is visible on the request.
- Every caller sharing `call()` (modeller, reviewer, redesigner) handles it.

## Files to touch
`ergostat/numbers/modeller.py`, `ergostat/library/run/modelling.py`, the tests of the AI tier.

## Risks
- lesson-3: an unknown cost is charged as the most it could be, never $0.

## Acceptance tests
- `tests/test_modeller.py::test_a_failed_call_is_an_error_and_keeps_its_try`
- `tests/test_modeller.py::test_an_is_error_response_is_an_error`
- `tests/test_modeller.py::test_a_response_with_no_cost_is_charged_its_reservation`
- `tests/test_modeller.py::test_the_cap_holds_when_responses_omit_their_cost`

## Size budget
50 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1: 34 net lines outside `tests/` and `docs/` (48 added, 14 removed). The four acceptance tests pass, and
so do three more in `tests/test_modeller.py`: a good call is charged what it said, the reviewer's failed calls are no
try, and a redesigner run whose calls failed ends `error`. Each new guard was broken once and its test seen to fail.

Choices made alone (the most reversible one each time):
- `call()` charges a failed call its reservation, or the cost it said if that is more (a call over its budget can say
  more than `unsaid`). A cost counts as said when it is a finite number, 0 or more, and not a bool. A said `$0` on a
  successful call is believed.
- The AI tier: when its first call fails, its requests keep their state and tries, are charged their share, and carry
  `why` and `error`. They wait for the next run, which can call again during an outage. Only the daily cap bounds
  those calls, each charged its whole reservation. When the go-back call fails after a first answer, that first answer
  used the try as before, and the held `why` says the second call failed rather than "proposed nothing".
- "Every caller" reached two files outside "Files to touch", in a few lines each. `numbers/reviewer.py`: a failed call
  is stamped `error`, does not count in `tries()`, and stops the pass. `numbers/redesigner.py` with
  `numbers/redesign_due.py`: the run's result is `error`, its request stays open saying so, and the unit takes no rest
  for it. SPEC §12e says all of this.
- This clone has no `origin` remote, and its `main` is the branch's base, so there was nothing newer to merge. The
  merge and the full suites are left to the factory.
