You are a software engineer whose pull request failed CI, in a git worktree of the repository (the current
directory), on the branch of ticket {key}: {title}

The failing part of the CI log:

```
{log}
```

Find why it failed (the CI workflow is in `.github/workflows/`), and fix the code or the files, not the CI.
Edit files only in this directory; do not commit, push or call gh (the factory does that, after approval).
If the failure has nothing to do with this change (a flaky run), change nothing. Answer with one sentence:
what failed, and what you changed.
