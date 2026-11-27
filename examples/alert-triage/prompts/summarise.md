You summarise one investigated alert from its facets' findings (`$ERGOSTAT_CMD item --projection facet --json`, those
whose `alert` is this one). If it needs a person (a deploy coincides, customers are affected), say
`{"event": "alert.escalated", "item": "<the alert>", "data": {"summary": "..."}}`; otherwise
`{"event": "alert.summarised", "item": "<the alert>", "data": {"via": "summary", "summary": "..."}}`.
