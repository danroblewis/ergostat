# faults-hold-by-a-field: failures that cluster on a field hold only that group

depends-on: [faults-healthy-pauses-the-queue]

Level 2 of the fault-isolating queue. Owner's use: to-dos on a bastion or a VPN, which fail together when that access is down, while everything else should carry on.

Change. `faults: {hold-by: [vpn]}` names item fields.

- When recent failures in a queue cluster on one value of the field (a stated, conservative rule, with its defaults documented), that value's items are **held**: not taken, and given back uncounted when they fail.
- Other values keep flowing.
- A held group is probed by retrying one item after a back-off, as a circuit breaker does (open, half-open, closed). One success releases the group.
- The hold records the field, value, evidence and when it began, for example "12 items held: vpn=prod, 5 of 5 failed since 14:02".
- An item with no value for the field is never held by this rule.

Definition of done.
1. All failures on `vpn: prod` hold that group, and `vpn: corp` items keep running.
2. A single failure holds nothing.
3. A probe's success releases the group, a probe's failure lengthens the back-off, and only one probe runs at a time.
4. Held items spend no attempts.
5. A restart of the engine keeps the holds (they are events).

Files: ergostat/leases/ (a small new module for holds), tests/test_faults_hold_by.py (new), docs/SPEC.md section 9.5.
