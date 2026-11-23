## Entry

section: Modelling

- **Triggers on an event type** (done on `triggers2`, after `triggers` was parked; SPEC §9.3, *Started by an event*):
  `on: {event: TYPE, where:, emits:, max-age:, most:}`, a run per event; loops refused when the model is read
  (`trigger-loop`, any length) and stopped at run time by the depth every run carries, whatever started it (8 at
  most, `trigger.stopped`); a breaker per block (`most:` a minute, reset by the owner); advise asks per event, answers
  naming their ask; lookups by id and prefix types indexed. *Left*: a relay outside ergostat that drops `causedby`
  is caught only by the breaker; `max-age` reads the event's own clock.
