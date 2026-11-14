# Your first loop: an inbox folder kept short

The smallest whole loop, written by hand: a stock (the inbox), a disturbance (files arriving), a sensor, a controller, a valve, and three one-line agents that print plain numbers. The worker is too slow on purpose.

```bash
cd examples/first-loop
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- Run it and watch `ergostat` report the loop off within a few minutes.
- Change `head -5` to `head -20` in `ergostat.toml`; the running ergostat reloads it and the loop holds again.
- Look at `ergostat system --blocks` and the page's blocks view.

Shows: one-line agents, bare numbers, live reload, falling behind and recovering.
