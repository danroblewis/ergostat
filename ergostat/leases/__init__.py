"""Leases on items, and the work queues they make (SPEC §9.5).

A block that ``takes`` items (a projection, in a state) is started once per item, each run holding a lease on its item:
taken, renewed by what the run causes about it, and ended by the run (ack: the work moved the item on; nack: given
back, with a reason) or by its expiry (silent past its TTL). An item given back or expired returns to the state it
was taken from, its attempts counted; after the most attempts its terms allow, it is a dead letter. Each lease has a
fencing number, so what a run says about its item after its lease ended is refused.

- ``terms``: a lease's TTL and attempts, by tier, kind and block;
- ``fold``: the lease folded onto its item, from the events (the fold is the truth);
- ``dispatch``: the engine's dispatcher and watchdog;
- ``measures``: ``ergostat.leases.*``;
- ``compile``: ``leases:``, a block's ``takes:``, ``pool:`` and ``lease:``, a projection's ``lease:``."""

PREFIX = "ergostat.lease."
TAKEN = PREFIX + "taken"
RENEWED = PREFIX + "renewed"
ENDED = PREFIX + "ended"
EXPIRED = PREFIX + "expired"
REDRIVEN = PREFIX + "redriven"
TYPES = (TAKEN, RENEWED, ENDED, EXPIRED, REDRIVEN)
