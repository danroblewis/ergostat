# The projection workbench

The owner's design (2026-11-27). Turning an event log into projected objects can't be automated reliably across
sources (the process-mining experiments: near-perfect on data shaped like what a method was written against, poor on
real SAP, GitHub and CloudTrail logs and on GCP- and Azure-shaped ones). So a person does it — an AI agent may draft,
reviewed the same way — and the tool's job is to make it quick and checkable. The workbench is a regulating feedback
loop for the user: the setpoint is nothing unexplained (every event in the query's result accounted for, every
object's history consistent), and the user goes round its steps until they get there, then saves.

## The definition (YAML)

```yaml
projections:
  instance:
    # updated 2026-11-27
    query: data.source == 'aws.ec2' and not data.detail.eventName.startswith('Describe')
    key: [data.account, data.region, data.detail['instance-id']]

    fields:                                   # what an instance is
      state:         {values: [pending, running, stopping, stopped, shutting-down, terminated]}
      instance_type: {type: text}
      launched_by:   {type: text, fold: first}
      launched_at:   {type: time, fold: first}
      restarts:      {type: integer, fold: add}
      tags:          {type: map, fold: merge}

    events:                                   # the kinds of event it reads, and what each tells it
      # updated 2026-11-27
      state-change:
        when: data['detail-type'] == 'EC2 Instance State-change Notification'
        state: data.detail.state
      # updated 2026-11-27
      launch:
        when: data.detail.eventName == 'RunInstances'
        key: [data.account, data.region, each(data.detail.responseElements.instancesSet.items, 'instanceId')]
        instance_type: data.detail.requestParameters.instanceType
        launched_by: data.detail.userIdentity.arn
        launched_at: time
      # updated 2026-11-27
      restart:
        when: data.detail.eventName == 'RebootInstances'
        key: [data.account, data.region, each(data.detail.requestParameters.instancesSet.items, 'instanceId')]
        restarts: 1
```

- `query:` which events the projection reads: an expression over the event (the handlers' expression language:
  `data`, `type`, `key`, `source`, `time`; missing paths are null). The language can change later; what matters is
  that its results can be used.
- `key:` the usual key: an expression, or a list (a composite key, joined by /). An event kind whose key sits elsewhere
  gives its own `key:`. `each(LIST, 'field')` in a key applies the event to every object named there (one event,
  several objects).
- `fields:` the object: each field's `type` (`text`, `number`, `integer`, `boolean`, `time`, `duration`, `map`,
  `list of T`; or `values: [...]`, the only values it may hold) and `fold` (how values from events combine: `replace`, the default, newest by event time
  wins; `first`, `add`, `min`, `max`, `append(N)`, `union`, `merge`, `count`, `mean`, `stdev`, `rms`, a model's own
  function). Optional `description`.
- `events:` the kinds of event it reads, named by the user (an event log can't be relied on to have a field naming its
  type). Each has a `when:` (an expression, within the query's result) and, for the fields it tells, an expression for
  each value, folded by the field's rule; a fold call (`set(...)`, `add(...)`) overrides the field's rule for that kind
  of event. An entry may fill only declared fields. The first kind whose `when:` holds takes an event.
- Events in the query's result that no kind takes are the remainder: shown, counted, never silently dropped.
- Comments record when each part was last updated (`# updated DATE`); Save rewrites only the parts that changed and
  keeps the rest of the file, comments included.
- The fold is by event time (the event's own time when the definition names it, else the recorded time), and an
  event delivered twice (the same envelope id, or the same type and data whole) counts once.

## The workbench (on the projection's list page, in edit mode; and for a new projection, from the nav bar's `+`)

1. **What it is.** The object's identity first: its key and its fields (type, values, fold, description). Then the
   query finds its parts (the owner, 2026-11-27: "I want to know what my thing is first, then I query to make sure I
   have all the parts").
2. **Query.** The whole record searchable, refined step by step; every change shows what it adds and drops
   (+212 events, −3). A time range. Right after its count, what the kinds of event in the result cover, and Accept all.
   The result's newest events, folded.
3. **Kinds of event.** The result set broken down by shape (the fields present and the values that split it),
   suggested from the data, only from the events no accepted kind takes, and never a kind that would take nothing;
   the user confirms, renames and edits them into `events:` entries with their `when:`.
4. **Mapping.** Per kind of event: its key (default or its own), the fields it tells, and one of its events shown as
   the draft reads it (each value tagged with the field it fills, the values nothing reads marked, ignored paths
   hidden) beside the record it makes. A value clicked goes into a field, the key, a new field made there, or
   `ignore:` (every kind's events); what another kind maps by the same path is offered in one click.
5. **Review.** What each kind took, the paths left to decide (neither mapped nor ignored), the comparison with the
   saved definition (objects that appear, disappear or change). Save writes the YAML.

Beside the steps, a panel of its own: one object's record and lifespan (its events in time order, which kind took
each, what each changed), every field's distribution, the lifecycles, and the residual (the remainder, events with no
key, refused values, contradictions, splits, merges), each shown only when not 0.

Coming back to an existing projection starts at step 4: the current distributions and residual show what drifted
(new shapes in the remainder, a kind of event no longer matching anything).

## Speed

The query runs over the whole record interactively, and must stay fast as the record grows (a long-running ergostat
must never get slower with its record's age): the paths queries and `when:`s use are indexed as events arrive; a query
reads candidates from the index, never scans the record; the workbench samples where an answer doesn't need every
event and says so.
