# status-reads-the-projections: the status answer reads the indexed tables and never scans the event log

Depends on `status-projections-in-the-index`. Move every event-log read of the status snapshot (`state.snapshot`, `inbox/`, `actions/record.py`, `numbers/requests.py`, `numbers/proposals.py`, `leases/measures.py`) onto those tables, and delete the old folding code it replaces.

Definition of done:
1. On a generated record of the factory's size, a status request makes no event-log scan once the index is current (a test counts segment queries) and answers in under 100 ms.
2. The status answer is equal, field by field, to the answer from the old code on that record, apart from fields that were capped before.
3. The answer says how old it is.
