## Entry

section: Remote systems and libraries

- **External event logs** (mirroring done on `external-event-logs`; reading in place open): systems that keep their
  own event log (Kafka, a ticket history, an incident log): copy in (works through collectors), read in place, or
  mirror with a cursor that cites the original.
  - *Done*: mirroring (`collect` with `mirror: true`, SPEC §2, *Mirroring an outside log*): each entry recorded once
    under `cite:<sensor>:<type>:<position>`, only by the sensor it names (pushes refuse a `cite:` id); the cursor
    confirmed against the record each poll and recovered from it (snapshots included) when the collector's memory is
    lost; a log that went back stops the mirror when the source shows it.
  - *Left*: reading in place for logs other than another ergostat's (Kafka and the like; remote systems, SPEC §4c,
    are the one case built); a restart seen when the source reads only after the cursor (a Kafka offset), which needs
    the source's own epoch or generation in the cite; entries mirrored again after the record forgot them and the
    memory was lost.
