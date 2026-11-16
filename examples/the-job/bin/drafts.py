"""What the stand-in preparers write: one Markdown draft per item, for me to read, change and use by hand.

Each is built from the item and from what the work systems' read APIs show (the simulated world,
or the code host with JOB_GH=1). They stand in for an AI agent's pass (prompts/): the same
sections, filled by rules. None of them is ever sent: every one ends saying what is mine to do."""

from __future__ import annotations

import random

from job import DAY

MINE = "\n---\n*Drafted for me; nothing was sent. {what}*\n"


def related(w: dict, service: str, before: float, within: float, n: int = 4) -> list[str]:
    """Recent deploys, flag changes and merges on a service, within `within` working days: what could relate to this."""
    rows = [x for x in w.get("log", []) if x["service"] == service and before - within * DAY <= x["t"] <= before]
    return [f"- {x['what']}: {x['ref']}" for x in rows[-n:]] or ["- nothing on this service in that window"]


def review_brief(it: dict, th: dict, w: dict) -> str:
    risky = [f for f in th.get("files", []) if any(k in f for k in ("migrations", "auth", "values.yaml", "limits"))]
    risk = "high" if risky or th.get("additions", 0) > 300 else "medium" if th.get("additions", 0) > 120 else "low"
    checks = {"retry": "retries bounded, with jitter; idempotent calls only", "config": "limits match the capacity plan; "
              "a rollback is one revert", "auth": "old tokens still verify during the overlap; no secret in logs",
              "schema": "the index is built concurrently; the migration is reversible", "metrics": "label cardinality "
              "bounded; dashboards not broken", "pipeline": "stages still gate the deploy; caches keyed by the lockfile"}
    return f"""# Review brief: {th.get('title', it['id'])}

{th.get('url', '')} · by {th.get('author', '?')} · {th.get('repo', '')} · +{th.get('additions', 0)} −{th.get('deletions', 0)}

## What it does
Changes {', '.join(th.get('files', [])) or 'files not listed'} in **{th.get('service', '?')}**.

## Risk: {risk}
{('Touches ' + ', '.join(risky) + '.') if risky else 'No migration, auth or limits file.'}

## Look for
- {checks.get(th.get('area', ''), 'tests cover the change; the failure path is handled')}
- error handling on the new path; a test for the unhappy case

## Related recent commits and deploys
{chr(10).join(related(w, th.get('service', ''), th.get('t', 0), 3))}
""" + MINE.format(what="The comments, the verdict and the tone are mine: I write them on the code host.")


def pr_nudge(it: dict, th: dict, w: dict) -> str:
    who = " and ".join(th.get("reviewers", [])) or "the reviewers"
    return f"""# Nudge: {th.get('title', it['id'])}

To {who}, in chat or on the PR:

> Hi! {th.get('url', 'My PR')} has been waiting a day for a first look. It's
> {th.get('additions', 0)} lines in {th.get('repo', 'the repo')}, mostly {', '.join(th.get('files', [])[:2])}.
> If you're swamped, tell me who else knows this area and I'll ask them.
""" + MINE.format(what="I send it myself, or ask in person.")


def team_nudge(it: dict, th: dict, w: dict) -> str:
    return f"""# Stale teammate PR: {th.get('title', it['id'])}

{th.get('url', '')} by {th.get('author', '?')}, waiting over 3 working days for review.

To {th.get('author', 'them')}:

> {th.get('url', 'Your PR')} has been open a few days. Want me to find a reviewer, or is it blocked on something?
""" + MINE.format(what="I send it, or raise it at standup.")


def mention_reply(it: dict, th: dict, w: dict) -> str:
    text = th.get("text", "")
    kind = "question" if "?" in text else "FYI"
    urgent = any(k in text for k in ("safe to ship", "today", "outage"))
    return f"""# {th.get('channel', '')}: {th.get('author', '?')} asked

> {text}

Triage: **{kind}**{', urgent' if urgent else ''}.

Suggested reply:

> Looking now; I'll come back with an answer within the hour.
""" + MINE.format(what="I answer as myself, in the channel.")


def secret_ticket(it: dict, th: dict, w: dict) -> str:
    return f"""# Rotation ticket (draft): {th.get('name', it['id'])}

**Summary:** Rotate `{th.get('name')}` before it expires on {th.get('expires', '?')} ({th.get('days_left', '?')} days).

**Service:** {th.get('service', '?')}

**Steps:** issue the new secret; deploy it alongside the old one; switch readers; revoke the old one;
confirm nothing still uses it (logs, then the store's last-used time).

**Rollback:** the old secret stays valid until the last step.
""" + MINE.format(what="I file it in the tracker myself.")


def alert_comment(it: dict, th: dict, w: dict) -> str:
    oncall = random.Random(th.get("service", "")).choice(["Ana", "Ben", "Chen", "Dara", "Eli", "Femi", "Gus", "Hana"])
    part = f"part of {th['outage']}" if th.get("outage") else "on its own (no outage open on this service)"
    return f"""# Alert: {th.get('summary', it['id'])}

**Seems:** {part}; severity {th.get('severity', '?')}.

## Suggested usefulness comment
> Actionable: it fired {'with' if th.get('outage') else 'without'} a user-visible problem. {
'Keep it; it led the outage.' if th.get('outage') else 'Consider a longer window before it pages.'}

## What changed on {th.get('service', '?')} before it
{chr(10).join(related(w, th.get('service', ''), th.get('t', 0), 0.5))}

## Who is on call for {th.get('service', '?')}
{oncall} (primary)
""" + MINE.format(what="I post the comment on its alert ticket myself.")


def action_plan(it: dict, th: dict, w: dict) -> str:
    return f"""# Postmortem action: {th.get('title', it['id'])}

From {th.get('outage', '?')} on {th.get('service', '?')}.

- **Owner:** me
- **Date:** within two weeks
- **First step:** a short proposal to the owning team, with the incident's timeline attached
- **Progress this week:** none yet
""" + MINE.format(what="The plan and the conclusions are mine to agree.")


def ramp_brief(it: dict, th: dict, w: dict) -> str:
    return f"""# Flag ramp: {th.get('flag', it['id'])}

Team {th.get('team', '?')} on **{th.get('service', '?')}** · schedule {th.get('schedule', '?')} · {th.get('pr', '')}

## The implementation
The flag guards the new path; the old path stays the default. Check: the flag is read once per request,
the off state is the old behaviour, and the kill switch works without a deploy.

## The schedule
{'Too fast for a first ramp: suggest 1% for a day.' if 'tomorrow' in th.get('schedule', '') else 'Reasonable stages.'}

## Recent on this service
{chr(10).join(related(w, th.get('service', ''), th.get('t', 0), 2))}

## Recommendation
{'Ask for a slower first stage, then approve.' if 'tomorrow' in th.get('schedule', '') else 'Approve, with an alert on the error rate.'}
""" + MINE.format(what="The approval is mine, and so is my name on it.")


def ci_plan(it: dict, th: dict, w: dict) -> str:
    return f"""# CI server upgrade plan: to {th.get('version', '?')}

Running {th.get('installed', '?')}. This release: {th.get('notes', 'see its changelog')}.

1. Read the changelog for plugin API changes; list our pipelines that use them.
2. Upgrade the staging server; run every pipeline once.
3. Upgrade production in the maintenance window; keep the old image for rollback.
""" + MINE.format(what="I do the upgrade myself, in the window.")


def ticket_explanation(it: dict, th: dict, w: dict) -> str:
    return f"""# Customer ticket: {th.get('title', it['id'])} ({th.get('customer', '?')})

**They ask me to:** {th.get('asks', '?')}

## What that command does
It acts on the customer's own data only, for {th.get('customer', 'the account')}; it is safe to run twice.

## Checked against the ticket
The account in the request matches the ticket's; the time range matches the report.

## Recommendation
Run it, then tell the customer what was done. SLA: {th.get('sla', '?')}.
""" + MINE.format(what="Nothing was run. Whether it runs is mine to decide, and I run it.")


def doc_draft(it: dict, th: dict, w: dict) -> str:
    stage = th.get("stage", "")
    body = {"problem": "## The problem\n## Who it hurts, and how much\n## What is out of scope",
            "proposal": "## The proposal\n## Alternatives considered\n## Who must review it",
            "design": "## Design\n## Failure modes\n## Rollout and rollback\n## Compliance notes",
            "board": "## Change\n## Risk and impact\n## Rollout window: " + th.get("rollout", "?") +
                     "\n## Rollback\n## Approvals so far"}.get(stage, "")
    return f"""# {th.get('title', it['id'])}

Drafted from my notes on: *{th.get('change', '')}*

{body}
""" + MINE.format(what="The thinking is mine: I finish it and take it to its reviewers (or the board).")


def update_draft(it: dict, th: dict, w: dict, ledger: str) -> str:
    return f"""# Weekly update, week of {th.get('week_of', '?')}

## Done this week (from the ledger)
{ledger or '- (nothing recorded yet)'}

## Next week
- the top three from Friday's ledger
""" + MINE.format(what="I send it to my manager myself.")


DRAFTS = {"review": review_brief, "pr": pr_nudge, "team-pr": team_nudge, "mention": mention_reply,
          "secret": secret_ticket, "alert": alert_comment, "action": action_plan, "ramp": ramp_brief, "ci": ci_plan,
          "ticket": ticket_explanation, "doc": doc_draft}
