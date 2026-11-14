# Nightly backups and off-site copies

A policy listens for `loop.off` and requests a backup; a job runs on that event; a second loop keeps the off-site copies current. One simulated hour passes every two seconds.

```bash
cd examples/backups
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- The wiring view shows how each agent's output reaches the next, and the cycles among them.
- `ergostat event --follow` shows the requests and openings as they happen.

Shows: events between agents, `on`, a declared disturbance rate.
