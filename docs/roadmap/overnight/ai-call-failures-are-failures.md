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
