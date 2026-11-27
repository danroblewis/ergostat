# Projection handlers: ideas for later

Not built. The owner's design for projections (2026-11-27: `match:`, `key:`, `states:`, `events:` with one handler per
event type, each field's value an expression such as `data.reason`, `add(1)`, `set('done')`) is in SPEC §5a. These
are the ideas discussed with it and kept for later, written down so they are not lost.

## Spreading an object into the item

A handler often maps many fields one to one. A JavaScript-style spread as a handler key would set each field of an
object at once; the fields written after it in the same handler apply after it, so they override it or fold by their
own rule.

```yaml
events:
  mission.planned:
    "...": data                                   # every field of data, as is
    state: set('planned')                         # then these, which win
    retry_count: 0

  mission.updated:
    "...": pick(data, 'name', 'crew', 'priority') # only these fields
    started_by: data.by                           # and one renamed

  instance.changed:                               # a cloud provider's nested JSON
    "...": data.detail                            # one level down
    region: data["aws-region"]
```

- `"...": EXPR`: EXPR gives an object; each of its fields sets the item's field of that name.
- The key is quoted: YAML reads a bare `...` as the end of the document.
- Helpers, as ordinary functions: `pick(obj, 'a', 'b')` (only those fields), `omit(obj, 'secret')` (all but those),
  `rename(obj, by='started_by')`.
- `otherwise: merge` is already the spread of the whole `data` for a type with no handler; this lets a handler spread,
  and choose what.
- Left out on purpose: destructuring patterns with renames inside them (`{name, by: started_by} = data`), a second
  syntax for what `pick` and `rename` do.

## Moving an item by a condition

A state entered when a condition on the folded item holds (`when:`), discussed before the handlers were designed:
with handlers it is an expression, for example `state: set('ongoing') if current_state == 'started' and
data.turpitude > 0.5 else current`. Whether conditions only move an item forward (so a value hovering at a threshold
does not flap between states) is not decided.

## Raw events from other sources

Events from other systems (cloud audit and change streams) arrive as nested JSON in their own shape. `match:` reads
paths into the event and `key:` is an expression, so a projection can read them as they come; what is not settled is
how such a stream is taken in (whole records kept as the event, and which field is its type for `events:`).
