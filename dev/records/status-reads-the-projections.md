# status-reads-the-projections: the status answer reads the indexed tables and never scans the event log

Depends on `status-projections-in-the-index`. Move every event-log read of the status snapshot (`state.snapshot`, `inbox/`, `actions/record.py`, `numbers/requests.py`, `numbers/proposals.py`, `leases/measures.py`) onto those tables, and delete the old folding code it replaces.

Definition of done:
1. On a generated record of the factory's size, a status request makes no event-log scan once the index is current (a test counts segment queries) and answers in under 100 ms.
2. The status answer is equal, field by field, to the answer from the old code on that record, apart from fields that were capped before.
3. The answer says how old it is.

## Where it stopped

Not started: this gap waits for `status-projections-in-the-index`, which is not on main as of the clone (63439d64).
The item index (`ergostat/spec/itemindex.py`, layout VERSION 5) holds only `items`, `moves`, `left`, `reached` and
`links`. No tables project the inbox, actions, requests, proposals or leases for the status snapshot to read, and no
record of that gap exists in `dev/records/`. Building those tables here would mean building the dependency inside
this gap, so nothing in `ergostat/` was changed (the most reversible option). The whole definition of done above is
left: once that gap is on main, move the status snapshot's event-log reads (`state.snapshot`, `inbox/`,
`actions/record.py`, `numbers/requests.py`, `numbers/proposals.py`, `leases/measures.py`) onto its tables, delete
the folding code they replace, and write the three acceptance tests: no segment query once the index is current, and
an answer in under 100 ms, on a record of the factory's size; field-by-field equality with the old answer; the
answer's age.
