"""open-pr: push the branch, open the pull request (its description links the issue and says how the work was
done), and move the issue to In Review (JIRA_IN_REVIEW) with a comment linking the pull request."""

from pathlib import Path

import github
import jira
import workspace
from act import act
from step import Move
from tf import conf, key_of, now

BODY = """Resolves [{key}]({url}): {title}

## What changed
{said}

## How
- Branch `{branch}`, from a workspace of the ticket factory (ergostat).
- Done by {who}{cost}.
- Review: comment, or `{approve}` when it is good to go.
"""


def run(ticket):
    f = ticket["fields"]
    key, ws, repo = key_of(ticket), Path(f["workspace"]), f["repo"]
    act("github.push", key, "open-pr", f"Push {f['branch']} to {repo}", github.push, ws, f["branch"],
        extra=f["head"])
    who = f"the AI agent (Claude Code, {conf('AI_MODEL')})" if conf("AI") == "claude" else "the stand-in (no AI)"
    cost = f", for ${f.get('ai_cost_usd', 0):.4f}" if f.get("ai_cost_usd") else ""
    body = BODY.format(key=key, url=f.get("url", ""), title=f.get("title", ""), said=f.get("work_said", "").strip(),
                       branch=f["branch"], who=who, cost=cost, approve=conf("APPROVE_WORD"))
    base = workspace.default_branch(workspace.REPOS / repo.replace("/", "__"))
    pr = act("github.open-pr", key, "open-pr", f"Open a pull request for {key} on {repo}", github.open_pr,
             repo, f["branch"], f"{key}: {f.get('title', '')}", body, base)
    act("jira.transition", key, "open-pr", f"Move {key} to {conf('JIRA_IN_REVIEW')}", jira.transition, key,
        conf("JIRA_IN_REVIEW"))
    act("jira.comment", key, "open-pr", f"Comment on {key}: the pull request", jira.comment, key,
        f"Pull request: {pr['url']}")
    return Move({"pr": pr["number"], "pr_url": pr["url"], "opened_at": now()})
