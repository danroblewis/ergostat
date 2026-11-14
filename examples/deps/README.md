# Two loops in series, a person behind

A program opens dependency-update pull requests, at most two a run (`max = 2`); a person reviews them and has fallen behind.

```bash
cd examples/deps
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- The status explains it: the first loop is at its valve's limit, and work piles up behind the second.
- The person's valve is manual; a person records what they did with `ergostat valve merge-update --opened N`.

Shows: people filling roles, valve `max`, saturation, work piling up downstream.
