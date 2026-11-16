# A folder as a queue

Files land in `inbox/`, a processor moves them to `outbox/`, an archiver keeps `outbox/` small. Plain shell scripts on real files.

```bash
cd examples/file-queue
ergostat check        # ok; one finding: the dropper acts on its own (it is the load)
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat event -n 40  # loop.off, block.commanded, valve.opened, loop.holding
ergostat run --stop
```

Things to look at:

- Two loops in series: the processor's flow is the archiver's load. Each block names its goal (`goal:`); ergostat runs it while that goal is off.
- The thresholds live in the goals, not the scripts: `process.sh` only processes three files, `archive.sh` only archives five. `until: "<= 10"` keeps the archiver going until `outbox/` is down to 10.
- `ergostat block` lists the implied `keep-inbox-empty` and `keep-outbox-small` controllers.
- Each script says what it moved as JSON lines, and an event per file: `file.dropped`, `file.processed`, `file.archived`.
- Items: each file is one (`file/note-….txt`), moving `inbox`, `outbox`, `archived` on those events. The stocks still count the folders (`ls`): a file someone drops by hand is in `inbox/` but not in the record.

Shows: loops in series, `goal:` and `until:` on a machine block, a load generator.

To see a valve too slow for its load: add `every: 1m` to `archive-oldest`. A commanded block's
`every` is the least time between its runs, so it can now archive at most 5 files a minute; the
outbox fills faster than that, `outbox-small` stays off, and `ergostat findings` says so.
