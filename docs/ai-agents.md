# AI agents in ergostat

The first use case: an AI agent fills a role, usually a controller, while the sensing and acting
are plain programs. ergostat does not run AI itself; an agent's command can be anything, including
`claude -p`.

## A controller filled by Claude

`examples/ai-controller.sh` takes a prompt file, gives Claude the run's stdin (the state, the
setpoint, the error), and turns Claude's one-object answer into ergostat lines:

```toml
[[controller]]
name = "docs-current"
holds = "stale-pages"
setpoint = "<= 3"
reads = ["stale-scan"]
drives = ["rewrite-page"]
agent = "page-picker"

[[agent]]
name = "page-picker"
kind = "ai"
command = "examples/ai-controller.sh prompts/page-picker.md"
every = "30m"
timeout = "5m"
```

The prompt says what the loop is for, what Claude may decide, and the answer's shape:

```markdown
You keep the user guide in step with the code. Pick the stale page that matters most to readers,
or wait when few are stale. Answer with one JSON object:
{"decision": "rewrite install.md: the CLI flags changed", "act": true, "amount": 1, "why": "..."}
```

Keep the valve a program you trust (here it only reports the decision's amount). An AI agent
deciding and a program acting is the safe split: the valve is where the owner's grant lives.

## Then move it down the ladder

Every run's decision is recorded. When `ergostat` shows a hint like
`page-picker (ai) decided "few enough: wait" 41 of 48 times: a decision or a rule could fill
controller docs-current`, the evidence for a cheaper agent is on the record:

1. `ergostat loop docs-current` lists the decisions, grouped, with how often each came up.
2. Write the cheaper agent (a short model call with fixed answers, then a rule) that says the same
   lines.
3. Point the controller's `agent` at it. The model does not change; the diagram's badge does.

The `docs-fresh` demo simulates this shape (its AI agent is a stand-in, so the demo costs nothing).
