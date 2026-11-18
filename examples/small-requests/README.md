# Small requests

Five standing requests of an engineer's job, each written as one use of a template (`docs/ADDING.md`):

| Request | Template |
|---|---|
| draft an answer for each question in the help queue, and none waits four hours | `respond-to` |
| remind reviewers daily until they answer, three times, then hand it back to me | `re-ping` |
| every weekday at 8:30, a report of what is open | `daily-report` |
| keep the build cache under 20 GB, pruning back to 15 | `keep-under` |
| work each regression ticket through: label, find the culprit, draft a revert | `steps` |

Each is a system of its own within `work`, drawn as a box in both views. Nothing is given a real source or action,
so each runs on its free stand-ins: a made-up feed of questions, reminders that send nothing, a summary of the
model as the report, a cache level that creeps up and a pretend prune, steps that do nothing. `ergostat check` lists
them (`template-stand-in`).

```bash
cp -r examples/small-requests /tmp/small && cd /tmp/small
ergostat run            # then the Diagram page: open work, then any of the five
```
