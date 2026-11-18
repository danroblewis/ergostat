You triage one alert from the pager. Read the alert (its service and summary) and the service's alerts of the
last day (`$ERGOSTAT_CMD item --kind alert --json`). If it is noise (a known flapping check, a duplicate), say
`{"event": "alert.dismissed", "item": "<the alert>", "data": {"why": "..."}}`; otherwise say
`{"event": "alert.triaged", "item": "<the alert>", "data": {"via": "triage", "severity": "low|high"}}`.
