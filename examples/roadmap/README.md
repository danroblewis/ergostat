# A roadmap: items related to items

Epics, each a fan-out of tickets that wait on one another, worked by stand-ins. It is the smallest model that shows
**relations between items** (SPEC §5a, *Relations*):

- `ticket.blocked_by` names other tickets (precedence: a ticket is ready only once each one it names is done);
- `ticket.parent` names its epic (cross-kind; a group: the Graph view hangs the tickets off their epic);
- `epic.after` names the epic before it.

The planner (`bin/plan.py`) records each epic and its tickets with their relations as plain data
(`{"event": "ticket.planned", "item": "ticket/e1-integrate", "data": {"parent": "epic/e1", "blocked_by": [...]}}`).
The developer block takes only **unblocked** tickets, the critical ones first (`takes: {..., unblocked: true}`);
the reviewer approves them; each epic is moved along by its tickets, a rule on its kind (`join:`, SPEC §5a, *Join*):
underway once one has started, shipped once every one is done.

```bash
ergostat -C examples/roadmap run            # then open the Items page: Graph, Timeline
```

On the Items page, **Graph** draws the tickets left to right, each after what it waits on, hanging off its epic;
the critical path is drawn heavier. **Frontier** keeps only the unfinished and what they wait on; **collapse done**
folds the finished into "via N done". **Timeline** is the Gantt chart: each ticket's states over time, and for the
unfinished, bars projected from the median time per state, each after what it waits on.
