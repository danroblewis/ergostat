# A folder as a queue

Files land in `inbox/`, a processor moves them to `outbox/`, an archiver keeps `outbox/` small. Plain shell scripts on real files.

```bash
cd examples/file-queue
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- Two loops in series: the processor's flow is the archiver's load.
- The archiver runs once a minute and is too slow: the loop panel shows how fast it answers, and the hint how often it would have to run.
- The diagram folds the chain into rows where one loop feeds the next.

Shows: loops in series, folding, answer and recovery times, a load agent.
