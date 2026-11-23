# compute-node-status: Each node's round trips measured, and a pool's status in the heartbeat and /api/status

depends-on: [compute-node-connection]

Problem: the lease rule for node runs needs each node's least round trip, and nothing shows whether a pool's nodes are in service. Change in ergostat/compute/connection.py: a ping every 2 s per node, least_rtt(window=60) from the pongs; a per-pool status() (nodes in service, lost, slots, free, last error, least round trip) that goes in the heartbeat and in /api/status under `compute` (ergostat/web/server.py:447-455) only when the model has pools. No page changes: the status is data in an existing answer. Done: least_rtt is the least of the window and has no value before the first pong; a lost node's slots leave the pool's status at the next reading; a model without pools has no `compute` key; another v's error is in status; no host name, address or user appears in status. Files: ergostat/compute/connection.py, ergostat/web/server.py, tests/test_compute_connection.py (four tests), docs/SPEC.md. Full text: wave2-compute.md (compute-node-connection, the status half). Budget: 90 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
