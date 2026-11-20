"""fix-ci: triage the failing CI log and fix it (prompts/ci.md) in the ticket's workspace, push, and let CI run
again; a failure with nothing to fix (a flaky run) is run again as it was. After CI_MAX_FIXES (3) fixes it
stops, for a person. Back to `sailed`, where `ci` watches the new run."""

from pathlib import Path

import agent
from gated import act
from step import Move, Stop
from tf import conf, env, key_of, now, once


def run(ticket):
    f = ticket["fields"]
    key, ws, repo, pr = key_of(ticket), Path(env("ERGOSTAT_WORKSPACE")), f["repo"], f["pr"]
    if int(f.get("ci_fixes") or 0) >= int(conf("CI_MAX_FIXES", "3")):
        return Stop(f"CI still fails after {f.get('ci_fixes')} fixes: a person should look")
    def fix():
        got = agent.run("ci", ticket, ws, log=f.get("ci_log", ""))
        return {**got, "head": agent.commit(ws, f"{key}: fix CI") or f.get("head")}
    got = once(f"{key}.fix-ci.{f.get('ci_failed_run')}.{f.get('ci_failures')}", fix)
    head = got["head"]
    if head != f.get("head"):
        act("git-push", _key=head)
        act("pr-comment", repo=repo, pr=pr, body=f"CI failed; triaged and fixed in {head[:10]}: {got['said'].strip()[:1200]}")
    elif f.get("ci_failed_run"):
        act("ci-rerun", repo=repo, run_id=f["ci_failed_run"], _key=str(f.get("ci_failures")))
    return Move({**agent.spent(got), "head": head, "ci_fix_said": got["said"], "ci_fixes": 1, "ci_since": now()})
