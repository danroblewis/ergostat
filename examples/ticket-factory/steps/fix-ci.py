"""fix-ci: triage the failing CI log and fix it (prompts/ci.md), push, and let CI run again; a failure with
nothing to fix (a flaky run) is run again as it was. After CI_MAX_FIXES (3)
fixes it stops, for a person. Back to `sailed`, where `ci` watches the new run."""

from pathlib import Path

import agent
import github
from act import act
from step import Move, Stop
from tf import conf, key_of, now, once


def run(ticket):
    f = ticket["fields"]
    key, ws, repo, pr = key_of(ticket), Path(f["workspace"]), f["repo"], f["pr"]
    if int(f.get("ci_fixes") or 0) >= int(conf("CI_MAX_FIXES", "3")):
        return Stop(f"CI still fails after {f.get('ci_fixes')} fixes: a person should look")
    def fix():
        got = agent.run("ci", ticket, ws, log=f.get("ci_log", ""))
        return {**got, "head": agent.commit(ws, f"{key}: fix CI") or f.get("head")}
    got = once(f"{key}.fix-ci.{f.get('ci_failed_run')}.{f.get('ci_failures')}", fix)
    head = got["head"]
    if head != f.get("head"):
        act("github.push", key, "fix-ci", f"Push the CI fix for #{pr}", github.push, ws, f["branch"], extra=head)
        act("github.comment", key, "fix-ci", f"Say what failed on #{pr} and how it was fixed", github.comment,
            repo, pr, f"CI failed; triaged and fixed in {head[:10]}: {got['said'].strip()[:1200]}", extra=head)
    elif f.get("ci_failed_run"):
        act("github.rerun", key, "fix-ci", f"Run CI again on #{pr}", github.rerun, repo, f["ci_failed_run"],
            extra=f"{f['ci_failed_run']}.{f.get('ci_failures')}")
    return Move({**agent.spent(got), "head": head, "ci_fix_said": got["said"], "ci_fixes": 1, "ci_since": now()})
