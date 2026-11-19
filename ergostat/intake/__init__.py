"""Events pushed to the running ergostat (docs/proposals/latency.md; SPEC §5c): recorded and folded at once, instead of
waiting for a collector's next poll.

- ``envelope``: an event or a batch, in the envelope a block's output lines use (``{"event", "item", "data"}``, or
  ``patch``/``set``, and an ``id`` that makes a retry the same event), checked and recorded in one write;
- ``token``: the local token in the state directory every push carries (a header, or an HMAC of the body as GitHub and
  PagerDuty sign theirs), and who may push from where (``intake: allow:``);
- ``hooks``: a webhook's payload (Jira, GitHub, PagerDuty, anything) made into events by a small mapping per source,
  ``intake: hooks:`` in the model;
- ``config``: ``intake:`` as written.

Collectors stay as they are: what nobody pushes is still polled."""
