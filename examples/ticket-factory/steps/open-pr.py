"""open-pr: push the branch, open the pull request (its description links the issue and says how the work was
done), and move the issue to In Review (JIRA_IN_REVIEW) with a comment linking the pull request. Runs with the
ticket's workspace (workspace: code), where the push is made."""

import github
from gated import act, act_json
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
    key, repo = key_of(ticket), f["repo"]
    act("git-push", _key=f["head"])
    who = f"the AI agent (Claude Code, {conf('AI_MODEL')})" if conf("AI") == "claude" else "the stand-in (no AI)"
    cost = f", for ${f.get('ai_cost_usd', 0):.4f}" if f.get("ai_cost_usd") else ""
    body = BODY.format(key=key, url=f.get("url", ""), title=f.get("title", ""), said=f.get("work_said", "").strip(),
                       branch=f["branch"], who=who, cost=cost, approve=conf("APPROVE_WORD"))
    pr = act_json("open-pr", repo=repo, title=f"{key}: {f.get('title', '')}", body=body, base=github.default_branch())
    act("jira-transition", key=key, status=conf("JIRA_IN_REVIEW"))
    act("jira-comment", key=key, text=f"Pull request: {pr['url']}")
    return Move({"pr": pr["number"], "pr_url": pr["url"], "opened_at": now()})
