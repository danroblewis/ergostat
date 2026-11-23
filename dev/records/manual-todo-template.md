# manual-todo-template: a person's own to-dos, with instructions, grouped by where they must be done

The owner, 2026-11-22: "a list of ToDo items I am supposed to do manually and providing clear accurate instructions ... At times, I have to do certain tasks on a bastion host or on a different VPN, and I would like those to be grouped together ... I am regularly pinged about from stakeholders, and I want to be able to track and explain their progress in a reliable and consistent way."

Change: a library template `todo` (`ergostat/library/templates/todo/`), generic and with no organisation's names:
- An item kind with states such as new, ready, in-progress, waiting, done, dropped. Fields: title, requester or stakeholder, **where** (the access context: a named host, bastion, VPN or "anywhere"), instructions (ordered steps, with commands and how to check each worked), due, waits on (another item, a person or an external thing), and notes.
- **Batches:** ready to-dos grouped by `where`, so everything for one bastion or VPN is done in one sitting, with its instructions in order.
- **A stakeholder update:** `ergostat why` on a to-do gives a consistent status, what it waits on and what happens next, from the record.
- Adding one from the command line or through an agent is one step; a person's "done" is recorded through the inbox's existing `--done`.

Definition of done: a demo under `examples/` with to-dos across three access contexts; tests for grouping, waiting, the status text, and that the template adds no action that writes to any outside system.
