"""branch: a workspace (a git worktree of the repository) and a branch named by BRANCH_TEMPLATE ({key},
{slug}: the title, short). Waits while every workspace is out (WORKSPACES).

PLUG POINT (branch `workspaces`): ergostat's worktree pool hands out the workspace instead of bin/workspace.py."""

import workspace
from step import Move, Wait
from tf import conf, key_of, slug


def run(ticket):
    f = ticket["fields"]
    key = key_of(ticket)
    branch = conf("BRANCH_TEMPLATE", "ergostat/{key}-{slug}").format(key=key, slug=slug(f.get("title", ""), 30))
    try:
        ws = workspace.take(key, f["repo"], branch)
    except workspace.Busy as e:
        return Wait(str(e))
    return Move({"branch": branch, "workspace": str(ws)})
