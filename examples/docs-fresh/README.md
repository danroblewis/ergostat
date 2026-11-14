# Docs kept in step with the code

An AI agent (simulated) rewrites pages; a cheap decision picks which; code changes are measured as they arrive.

```bash
cd examples/docs-fresh
ergostat check
ergostat run          # prints the page's address
ergostat              # what needs attention
ergostat run --stop
```

Things to look at:

- The controller reads the disturbance's own meter: feedforward, drawn in the blocks view.
- The Agents page puts each agent on the ladder, from AI down to rule.

Shows: AI agents, the ladder, feedforward.
