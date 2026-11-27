# My to-dos, grouped by where they must be done

A person's own to-dos, each with its instructions (the steps in order, each with its command and how to check it
worked), who asked for it, when it is due, and where it must be done: on a bastion, on a VPN, on a named host, or
anywhere. They are read from `todos.jsonl`, across three places (`bastion-1`, `lab-vpn`, `build-host`) and
anywhere. The template, `use: todo`, regroups the ready ones into one batch a place, so everything for one bastion
or VPN is done in one sitting.

```bash
cd examples/todo-list
ergostat check
ergostat run                                  # prints the page's address
ergostat item --projection todo                     # every to-do and its state
ergostat item --projection todo-batch               # one batch a place: bastion-1, lab-vpn, anywhere
ergostat item todo-batch/bastion-1            # its sitting: both to-dos, the one due first first, every step in order
ergostat why todo/clean-cache                 # waiting: on todo/request-access, and what happens next
ergostat inbox                                # the person asked to do a sitting (and to write up the new one)
```

Working through them:

- Add one in one step: `ergostat event --add todo.ready --item todo/ID --data '{"title": "...", "where":
  "bastion-1", "instructions": [{"do": "...", "run": "...", "check": "..."}]}'`, or a line in `todos.jsonl`, or
  from an agent with MCP's `record_event`. `todo.added` records one not written up yet.
- Say how each went: `ergostat event --add todo.done --item todo/rotate-logs` (or `todo.started`, `todo.waiting`
  with `{"waits_on": "..."}`, `todo.dropped`; `{"notes": "..."}` adds a note). After a sitting, answer the ask:
  `ergostat inbox person/todo-do --done 2`.
- Waiting on someone else: `ergostat event --add todo-wait.asked --item todo-wait/firewall-ok --data '{"title":
  "the network team says yes", "who": "the network team"}'`, then `{"waits_on": "todo-wait/firewall-ok"}` on the
  to-do; `todo-wait.answered` once they answer. A waiting to-do whose every wait has happened (done, answered) is ready
  again by itself, in its place's batch; one whose prerequisite was dropped stays waiting, and its `stuck` field
  says so (cleared on the batcher's next pass once it leaves waiting, by `todo.ready` or any other). Only what `waits_on` named since it last entered waiting counts.
- When someone asks how theirs is going, `ergostat why todo/ID` says its state and for how long, what it waits on,
  and who must do what next, from the record, in one paragraph to paste.

Nothing the template adds acts outside ergostat: the person does the work and records it; the batcher only reads the
record and prints events; `cat todos.jsonl` is this demo's own source.

Shows: items as a person's own units of work, a precedence relation (`waits_on`), a kind's own finished states, person
blocks that only ask, a rule-rung program regrouping items, `why` as a stakeholder update.
