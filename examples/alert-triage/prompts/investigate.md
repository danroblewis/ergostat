You investigate one facet of an alert: its logs, its deploys or its metrics (the facet's `facet` field). Record what
you found at once, with `$ERGOSTAT_CMD event --add facet.done --item <the facet> --data '{"finding": "..."}'` (it is
written before the command returns, and recorded as caused by this run). Then read the alert's other facets of the
same round (`$ERGOSTAT_CMD item --projection facet --json`, those whose `alert` and `round` are this one's): if every one
has a `finding`, you finished the last, so say `{"event": "alert.investigated", "item": "<the alert>"}`.
