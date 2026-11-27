# Projection handlers: ideas for later

Not built, but for the spread (below). The owner's design for projections (2026-11-27: `match:`, `key:`, `states:`, `events:` with one handler per
event type, each field's value an expression such as `data.reason`, `add(1)`, `set('done')`) is in SPEC §5a. These
are the ideas discussed with it and kept for later, written down so they are not lost.

## Spreading an object into the item

Built (2026-11-27): the `"..."` handler key, with `pick`, `omit` and `rename`. See SPEC §5a, *Handlers*.

## Moving an item by a condition

A state entered when a condition on the folded item holds (`when:`), discussed before the handlers were designed:
with handlers it is an expression, for example `state: set('ongoing') if current_state == 'started' and
data.turpitude > 0.5 else current`. Whether conditions only move an item forward (so a value hovering at a threshold
does not flap between states) is not decided.

## Raw events from other sources

Events from other systems (cloud audit and change streams) arrive as nested JSON in their own shape. `match:` reads
paths into the event and `key:` is an expression, so a projection can read them as they come; what is not settled is
how such a stream is taken in (whole records kept as the event, and which field is its type for `events:`).
