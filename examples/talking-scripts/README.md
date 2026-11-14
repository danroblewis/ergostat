# Scripts that print sentences, used unchanged

Three ordinary shell scripts print lines for people ("cleanup done: removed 12 stale uploads"). Each agent's `parse` takes the number from its own words.

```bash
cd examples/talking-scripts
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- `ergostat agent clean --now` shows the number taken and the line it came from.
- The cleanup's valve declares `max = 25`: one run never removes more.

Shows: `parse`, valve `max`, open loops, a declared disturbance rate.
