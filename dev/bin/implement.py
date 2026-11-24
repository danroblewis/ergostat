"""implementor: takes a gap at ready (or at fix, sent back with its findings), under a lease, and builds it:

1. a clone of the factory's drop repository (agents.py: never the owner's), on the branch factory/<branch> from main;
   with [suites] build_browser = true only, Playwright's Chromium launched once in the image, in a suite container
   and the slot (agents.browser_ready): no browser stops the round before it starts (given back uncounted, its
   reason said), never a browser file skipped;
   the definition of done committed first (`dev/records/<branch>.md`) when the branch lacks it, by this
   program; a branch behind main (a continued one, a fix round) has main merged in by this program (a conflict is
   left for the session, its files in the brief); then published to the drop. A gap whose every unfinished
   dependency is approved, queued or push-pending (fac.stack_base) is stacked: main and each one's reviewed head merged
   in rank order (`--no-ff`, never a rebase or a squash) as a commit in the drop, refs/stack/factory/<branch>, by this
   program, and that commit merged in instead of main; it is the base the strays, net lines, check findings and the
   run on main are measured against, and `finish` holds main and each base's sha. `stacked_on` [{gap, sha}] is on
   gap.started and gap.built. Bases that conflict (with each other or main) give the gap back uncounted for 30m, the
   files named; so does a base whose reviewed head is no longer its branch's tip (it waits for the merge-forward). A
   gap with no unfinished dependency builds on main alone, as before;
2. a session in a container of its own (or the stand-in) on a brief assembled from dev/prompts/implementor.md;
3. what it left uncommitted committed and bundled back to the drop (in a container with no network); before the
   suites, a branch adding scratch files (`strays`: [gates] scratch_patterns, or a new top-level file or folder the
   definition's Files to touch does not name) is refused, back to the session's next round with the list (uncounted;
   still there after the last, a failed build), and so is one adding `ergostat check` findings (`new_findings`); the
   fast suites (ruff, then the unit suite and the four browser files under the watchdog, a browser test skipped
   counting as a failure) in a container with no network, in a machine-wide slot; a failure
   that names tests is triaged first (onmain.py: run alone on the branch, a flake retried once; run on clean main, a
   test failing there too is main's), and a failure of the gap's is given back to a session to fix, `suite_fix_rounds`
   times;
4. `gap.built`, with its head, net lines, budget, suites, cost and the context it was given.

The kill rule ([gates]): fast suites that fail on `build_failures` runs of it, or building past `build_hours`, park the
gap with where it stopped. Each failed run adds one to `build_failures` (summed by the gap kind's fold), over the gap's
life: a later successful build does not reset it; a continued gap is a new item and starts from none. A failure
whose every test fails on main too is not counted: the gap waits for main to move (`waits_on_main`). Within the day's
dollar cap only (fails closed): over it, the gap is given back for an hour, uncounted."""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import fac  # noqa: E402
import onmain  # noqa: E402
import pools  # noqa: E402


def definition_first(cfg: dict, gap: dict, work: Path) -> tuple[str, str]:
    """The definition file (fac.definition_file), committed as the branch's first commit when the branch does not have
    it (by this program, in the clone it made, before any session); (its text, the commit that holds it). A record
    that holds only its GAPS.md `## Entry` (gapsdoc split's) is given the definition, put before that Entry, which
    stays the record's last section; one whose definition is in the old folder is never given a second
    (fac.definition_file() names the old file)."""
    branch, rel = fac.branch_of(gap), fac.definition_file(gap, work)
    target = work / rel
    entry = target.read_text() if target.is_file() and fac.entry_only(target.read_text()) else ""
    if not target.is_file() or entry:
        text = brief.definition_text(cfg, str(gap["fields"].get("definition", "")), branch)
        if not text.strip():
            raise RuntimeError(f"{gap['id']} has no definition of done to commit")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text.rstrip("\n") + "\n" + (f"\n{entry.lstrip()}" if entry else ""))
        fac.git(work, "add", rel)
        fac.git(work, "-c", "user.name=factory", "-c", "user.email=factory@localhost", "commit", "-q", "-m",
                f"{branch}: the definition of done\n\n{fac.TRAILER}")
    held = fac.git(work, "log", "--reverse", "--format=%H", "-1", "--", rel) or fac.git(work, "rev-parse", "HEAD")
    return target.read_text(), held


def merge_main(work: Path, main: str, what: str = "main") -> list[str]:
    """main (or a stacked gap's stack: `what`) merged into a branch that is behind it (by this program, before the
    session): a clean merge committed as the factory; a conflicted one left in progress for the session to finish. The
    files in conflict (none: clean, or nothing to merge)."""
    if fac.git_ok(work, "merge-base", "--is-ancestor", main, "HEAD"):
        return []
    who = ["-c", "user.name=factory", "-c", "user.email=factory@localhost", "-c", "commit.gpgsign=false"]
    if fac.git_ok(work, *who, "merge", "--no-ff", "-m", f"Merge {what} ({main[:12]}) into the branch\n\n{fac.TRAILER}",
                  main):
        return []
    conflicts = fac.conflicted(work)
    if not conflicts:                                 # failed for another reason than a conflict: stop, never guess
        raise RuntimeError(f"merging main {main[:12]} failed without conflicts: {fac.git(work, 'status', '--short')}")
    return conflicts


def stack(cfg: dict, branch: str, main: str, bases: list[dict], write: bool = True) -> tuple[str, list[str]]:
    """main and each base's reviewed head merged in rank order (by this program, `--no-ff`, never a rebase or a
    squash), in the drop with no work tree, as a commit under refs/stack/factory/<branch> (on no branch): (that commit,
    or ""; the files where two of them conflict). Each merge is dated as the base it adds, so the same main and bases
    make the same commit in every round, and a branch that holds it is not merged again. ``write`` False: the commit
    only, the ref left as it is (stack.py moves it after the gap has said its new head and `stack_base`)."""
    d, at = agents.drop(cfg), main
    for b in bases:
        out = fac.git(d, "merge-tree", "--write-tree", "--name-only", "--no-messages", "-z", at, b["sha"], check=False)
        tree, *files = [p for p in re.split(r"[\0\n]", out) if p] or [""]
        if not re.fullmatch(r"[0-9a-f]{40,64}", tree):                  # (failed for another reason: stop, never guess)
            raise RuntimeError(f"git merge-tree {at[:12]} {b['sha'][:12]} in the drop said nothing readable")
        if files:
            return "", sorted(set(files))
        when = fac.git(d, "show", "-s", "--format=%ci", b["sha"])
        at = subprocess.run(["git", "-C", str(d), "-c", "commit.gpgsign=false", "commit-tree", tree, "-p", at, "-p",
                             b["sha"], "-m", f"Merge {b['gap']} ({b['sha'][:12]}) under {branch}\n\n{fac.TRAILER}"],
                            env={**os.environ, **WHO, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when},
                            capture_output=True, text=True, check=True, timeout=600).stdout.strip()
    if write:
        fac.git(d, "update-ref", f"refs/stack/{fac.git_branch(branch)}", at)
    return at, []


WHO = {f"GIT_{who}_{what.upper()}": v for who in ("AUTHOR", "COMMITTER") for what, v in (("name", "factory"),
                                                                                         ("email", "factory@localhost"))}
SCRATCH = [".scratch*", "scratch*", "tmp*", "_probe*", "*_probe*.py", "*.orig", "*.rej", "test_zz*", "*_tmp.py",
           "*.tail", ".bench*", ".mut*"]                                           # [gates] scratch_patterns


def unlisted(repo: Path, base: str, head: str, definition: str) -> list[str]:
    """The files the branch adds or changes against main (`base`) that main does not have and the definition's "Files
    to touch" does not name (the file, or a folder above it). With no such section, every one: none is named."""
    on_main = set(fac.git(repo, "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", base).splitlines())
    named = [p for p, _ in brief.files_of(definition)]
    changed = fac.git(repo, "-c", "core.quotePath=false", "diff", "--name-only", "--no-renames", "--diff-filter=d",
                      f"{base}...{head}").splitlines()
    return [p for p in changed if p not in on_main and not any(p == n or p.startswith(n + "/") for n in named)]


PATHS_MOST = 200        # paths a gap's record keeps (the risk score reads them: ergostat.yaml, gap's risk-score)


def touched(repo: Path, base: str, head: str) -> list[str] | None:
    """The paths a branch changes against its base, the gaps' records left out (each gap's own, telling nothing of
    another), for the gap's risk score; None when git cannot say (the score learns a missing value as its own, never
    as safe)."""
    try:
        out = fac.git(repo, "diff", "-z", "--name-only", f"{base}...{head}", "--", ".", f":(exclude){fac.DEFS}")
    except Exception:
        return None
    return sorted(p for p in out.split("\0") if p)[:PATHS_MOST]


def strays(cfg: dict, repo: Path, base: str, head: str, definition: str) -> list[str]:
    """The `unlisted` files that look like a session's scratch: one with a path part matching a [gates]
    scratch_patterns glob, or under a new top-level file or folder the definition's "Files to touch" does not name
    (when it has that section). A file on main, or one the definition names, is never one."""
    pats = cfg.get("gates", {}).get("scratch_patterns", SCRATCH)
    if not isinstance(pats, list) or not all(isinstance(p, str) for p in pats):
        raise ValueError(f"[gates] scratch_patterns must be a list of globs, not {pats!r}")
    tops = set(fac.git(repo, "-c", "core.quotePath=false", "ls-tree", "--name-only", base).splitlines())
    tops |= {p.split("/", 1)[0] for p, _ in brief.files_of(definition)} | {
        fac.DEFS.split("/", 1)[0]}                                         # (the definition's own folder: dev/records)
    listed = brief.section(definition, "Files to touch") is not None
    return [p for p in unlisted(repo, base, head, definition) if
            any(fnmatch.fnmatchcase(part, pat) for part in p.split("/") for pat in pats)
            or listed and p.split("/", 1)[0] not in tops]


def stray_brief(text: str, stray: list[str]) -> str:
    return (f"{text}\n\n# Scratch files refused\n\nThe factory refused your build before the suites: the branch adds "
            "files that look like scratch ([gates] scratch_patterns), or a new top-level file or folder the definition's "
            "Files to touch does not name:\n\n" + "\n".join(f"- `{p}`" for p in stray) + "\n\nRemove each (`git rm`), "
            "or move what belongs to the gap under a folder main has, commit, and stop.\n")


def gaps_md_edited(repo: Path, base: str, head: str) -> bool:
    """Whether the branch's own commits change docs/GAPS.md (since it left ``base``: main, or the stack of main and
    its approved bases, whose own edits are judged on them): the queue writes GAPS.md from the records as it lands
    (queue.gaps_md()) and gives back an approved gap that edits it (queue.gaps_md_edited()), so a gap's entry is
    written as its record's `## Entry`."""
    return bool(fac.git(repo, "diff", "--name-only", f"{base}...{head}", "--", "docs/GAPS.md"))


def gaps_md_brief(text: str, base: str, branch: str, what: str = "main") -> str:
    return (f"{text}\n\n# docs/GAPS.md edited\n\nThe factory refused your build before the suites (uncounted): the "
            "branch changes docs/GAPS.md, which the merge queue writes from the records as it lands. Write the gap's "
            f"entry as the `## Entry` section of `{fac.DEFS}/{branch}.md` (its shape is in dev/prompts/definition.md), "
            f"put docs/GAPS.md back as {what} has it (`git checkout {base[:12]} -- docs/GAPS.md`), commit, and stop.\n")


def new_findings(cfg: dict, home: Path, branch: str, base_sha: str, definition: str, logs: Path, tag: str,
                 mains: dict) -> tuple[list[str], list[str]]:
    """`ergostat check` ([suites] check) on the work and on main at ``base_sha`` (once a run: ``mains``), by code and
    part (fac.findings): (new ones the definition does not allow, the allowances used, "code part: why"). A side that
    said nothing readable is a failure to compare, never "none new"."""
    def side(h: Path, name: str) -> set[str] | None:
        agents.suites(cfg, h, ("check",), logs, f"{tag}-{name}")
        log = logs / f"{tag}-{name}-check.txt"
        return fac.findings(log.read_text() if log.is_file() else "", fac.RECORD_FINDINGS)
    if mains.get(base_sha) is None:
        mhome, _ = agents.clone(cfg, branch, "main", at=base_sha)
        try:
            mains[base_sha] = side(mhome, "main")
        finally:
            shutil.rmtree(mhome, ignore_errors=True)
    mine, theirs, allowed = side(home, "branch"), mains[base_sha], fac.allowances(definition)
    if mine is None or theirs is None:
        sides = " and ".join(s for s, got in (("main", theirs), ("the branch", mine)) if got is None)
        return [f"could not compare: `ergostat check` said nothing readable on {sides}"], []
    if fac.UNFINISHED & (mine | theirs):     # extreme-conditions compared only when both sides finished every test
        mine, theirs = ({k for k in s if k.split()[0] != "extreme-conditions"} for s in (mine, theirs))
    new = sorted((mine - fac.UNFINISHED) - theirs)
    return [k for k in new if k not in allowed], [f"{k}: {allowed[k]}" for k in new if k in allowed]


def findings_brief(text: str, new: list[str]) -> str:
    return (f"{text}\n\n# New `ergostat check` findings\n\nSent back before the suites: `ergostat check` finds these on "
            "the branch, not on main (by code and part):\n\n" + "\n".join(f"- `{k}`" for k in new) +"\n\nChange the "
            "model so each goes, commit, and stop. Only the definition's `allows-findings` line allows one: never edit "
            "it; say so in your report.\n")


def conflict_brief(main: str, conflicts: list[str]) -> str:
    return ("\n\n# First: finish the merge of main\n\nThe factory merged main (" + main + ") into your branch, and it "
            "conflicted in:\n\n" + "\n".join(f"- `{c}`" for c in conflicts) + "\n\nResolve each (keep what main changed "
            "and what the branch adds), `git add` them and `git commit --no-edit` before any other work; `git status` "
            "shows what is left. Never `git merge --abort`: a branch that does not hold main is refused.\n")


def park(cfg: dict, gap: dict, why: str) -> None:
    """The kill rule on the implementor's side: where it stopped, on its branch and its item."""
    import review
    review.park(cfg, gap, why, "implementor", where="building", kind="kill-rule")


def main() -> int:
    fac.stop_on_term()
    cfg = fac.config()
    given = fac.read_input()
    began = time.time()
    try:
        return build(cfg, given, began)
    except agents.Refused as e:                       # no token: not the gap's fault, and not a dead letter
        fac.nack(str(e), after="1h", count=False)
        return 0
    except Exception:  # noqa: BLE001 - every other failure: parked on its last attempt, never a dead letter
        return fac.guarded(given, began, "build_hours", lambda why: park(cfg, given["item"], why))


def build(cfg: dict, given: dict, began: float) -> int:
    gap = given["item"]
    f = gap["fields"]
    if fac.ai_holds(cfg):
        return 0
    refused = fac.may_spend(cfg, float(cfg["ai"]["implementor_session_usd"]))
    if refused:
        fac.nack(f"budget: {refused}", after="1h", count=False)
        return 0
    if not pools.my_turn(cfg, "implementor", "implementor", gap["id"]):   # (put off under a minute: it keeps its rank
        # for the next free slot; implement-when holds the block shut while no session fits, so it does not spin)
        fac.nack("the implementor pool is full (run/pools.json): waits its turn", after="45s", count=False)
        return 0
    rework = (given.get("lease") or {}).get("back", gap["state"]) == "fix"
    rounds = int(f.get("rounds") or 0) + 1
    branch = fac.branch_of(gap)
    hours = fac.gate(cfg, "build_hours")
    if float(f.get("build_hours") or 0) >= hours:
        park(cfg, gap, f"Building took {float(f['build_hours']):.1f} hours over its rounds, past the kill rule's "
                       f"{hours:g}: stopped. Its last findings: {f.get('findings') or 'none'}")
        return 0
    bases = fac.stack_base(cfg, gap) or []
    moved = [b["gap"] for b in bases if fac.git(agents.drop(cfg), "rev-parse", "--verify", "-q",
                                                f"refs/heads/{fac.git_branch(b['branch'])}", check=False) != b["sha"]]
    if moved:
        fac.nack(f"its base {', '.join(moved)} moved past its reviewed head: waits for the merge-forward", after="30m",
                 count=False)
        return 0
    stacked = [{"gap": b["gap"], "sha": b["sha"]} for b in bases]       # ([] once, over a stack an earlier round had)
    on = {"stacked_on": stacked} if stacked or f.get("stacked_on") else {}
    fac.say("gap.started", branch=branch, rework=rework, building_at=began, **on)
    home, work = agents.clone(cfg, branch, "implementor")
    logs = fac.run_dir(cfg, "logs")
    if "browser" in onmain.fast(cfg):                  # (only with [suites] build_browser; no browser: stopped, uncounted)
        agents.browser_ready(cfg, home, logs, f"{fac.run_tag(branch, began)}-ready")
    base_sha = against = fac.git(work, "rev-parse", f"origin/{cfg['git']['base']}")
    if bases:                                          # (against: main, or the stack of main and the bases)
        against, clash = stack(cfg, branch, base_sha, bases)
        if clash:
            fac.nack(f"its bases {', '.join(b['gap'] for b in bases)} conflict with each other (or with main "
                     f"{base_sha[:12]}) in: {', '.join(clash)}", after="30m", count=False)
            return 0
        fac.git(work, "fetch", "-q", "origin", f"refs/stack/{fac.git_branch(branch)}")
    definition, held = definition_first(cfg, gap, work)
    what = "main and its bases " + ", ".join(b["gap"] for b in bases) if bases else "main"
    conflicts = merge_main(work, against, what)
    was = agents.publish(cfg, work, branch)           # (in a merge left in progress: the branch as it was before it)
    text, context = brief.assemble(cfg, "implementor", gap, work, definition=definition)
    text += conflict_brief(against, conflicts) if conflicts else ""
    text = gaps_md_brief(text, against, branch, what) if gaps_md_edited(work, against, "HEAD") else text
    context["brief"] = brief.save(cfg, "implementor", gap, text)
    context["round"], context["merge_conflicts"] = rounds, conflicts
    cost, sessions, used = 0.0, 0, []
    suites: dict = {}
    fast_seconds = 0.0                                  # every try's fast suites (times.py's gate `fast`)
    mains, allowed = {}, []                       # main's check findings by its sha; the allowances the branch used
    seen: dict[str, bool] = {}                                # tests run on main in this run: failed there?
    retried, deadline = False, began + (hours - float(f.get("build_hours") or 0)) * 3600
    for i in range(1 + int(cfg["ai"]["suite_fix_rounds"])):
        prompt = text if i == 0 else gaps_md_brief(text, against, branch, what) if suites.get(
            "gaps_md") else stray_brief(text, suites["stray"]) if suites.get("stray") else findings_brief(
            text, suites["findings"]) if suites.get("findings") else (
            f"{text}\n\n# The fast suites failed after your work\n\n`{suites['failed']}` failed"
            f" ({', '.join(suites['tests']) or 'see the tail'}{onmain.whose(suites, gap['id'])})."
            " Fix the code (not the tests' bounds), commit, and"
            f" stop. The tail of its output:\n\n```\n{suites['tail']}\n```\n")
        try:
            got = fac.session(cfg, "implementor", prompt, work)
        except fac.OverBudget as e:
            fac.nack(f"budget: {e}", after="1h", count=False)
            return 0
        cost, sessions = cost + float(got.get("total_cost_usd") or 0), sessions + 1
        used += [got["resources"]] if got.get("resources") else []
        head = was = agents.finish(cfg, home, branch, against, held, base_sha, *(b["sha"] for b in bases), was=was)
        stray = strays(cfg, agents.drop(cfg), against, head, definition)    # (main and each base merged in, and the
        # branch where it was given:
        if stray:                                               # refused when not); scratch refused before the suites
            suites = {"failed": "scratch files", "tests": stray, "stray": stray, "tail": "\n".join(stray)}
            continue
        if gaps_md_edited(agents.drop(cfg), against, head):            # the entry belongs in the record: uncounted
            suites = {"failed": "docs/GAPS.md edited", "tests": [], "gaps_md": True, "tail": "docs/GAPS.md"}
            continue
        fac.wait_quiet(cfg)
        new, allowed = new_findings(cfg, home, branch, against, definition, logs, f"{fac.run_tag(branch, began)}-{i}",
                                    mains)
        if new:                                                 # findings added to the model: back before the suites
            suites = {"failed": "check findings", "tests": new, "findings": new, "tail": "\n".join(new)}
            continue
        suites, retried = onmain.check(cfg, gap["id"], home, branch, base_sha, logs, f"{fac.run_tag(branch, began)}-{i}",
                                       deadline, seen, retried, bases)   # (on main itself: only main's can be main's)
        fast_seconds += sum(float((suites.get(s) or {}).get("seconds") or 0) for s in onmain.fast(cfg))
        used += [v["resources"] for v in suites.values() if isinstance(v, dict) and v.get("resources")]
        if not suites.get("failed") or suites.get("main_broken"):    # (main's failures are never the session's)
            break
    net = fac.net_lines(agents.drop(cfg), against if bases else cfg["git"]["base"], head)
    record = dict(**on, rounds=1, ai_cost_usd=round(cost, 4), sessions=sessions, contexts=[context], head=head,
                  paths=touched(agents.drop(cfg), against if bases else cfg["git"]["base"], head),
                  built_by=os.environ.get("ERGOSTAT_AGENT"),
                  stack_base=against if bases else "",
                  net_lines=net, budget=fac.budget_of(definition), built_main=base_sha, suites_fast=suites, session_dir=str(home),
                  fast_seconds=round(fast_seconds, 1),
                  build_hours=round((time.time() - began) / 3600, 3), said=str(got.get("result", ""))[-600:],
                  resources=used, allowed_findings=allowed)
    if suites.get("flakes"):
        record["flakes"] = suites["flakes"]
    broken = sorted(t for t, bad in seen.items() if bad)        # (found in any round of this run)
    record["main_broken_tests"] = broken
    if broken:
        onmain.record(gap["id"], base_sha, broken)
    if suites.get("gaps_md"):                         # never a build failure: its next try is told why (gaps_md_brief)
        fac.say("gap.measured", **record)
        fac.nack("refused before the suites, uncounted: the branch edits docs/GAPS.md; the entry goes in its record's "
                 "## Entry", count=False, after="1m")
        return 0
    if suites.get("failed") and suites.get("main_broken"):
        fac.say("gap.measured", waits_on_main=base_sha, **record)
        fac.nack(f"its fast suites failed only on tests that fail on main {base_sha[:12]} too "
                 f"({', '.join(suites['on_main'][:5])}): not the gap's; it waits for main to move", count=False, after="5m")
        return 0
    if suites.get("failed"):
        fails = int(f.get("build_failures") or 0) + 1
        fac.say("gap.measured", build_failures=1, **record)
        why = (f"refused before the suites, its scratch files still on the branch: {', '.join(suites['stray'])}"
               if suites.get("stray") else "sent back before the suites, new `ergostat check` findings: "
               + ", ".join(suites["findings"]) if suites.get("findings") else
               f"the fast suites failed ({suites['failed']}: {', '.join(suites['tests'][:5])}"
               f"{onmain.whose(suites, gap['id'])})")
        if fails >= fac.gate(cfg, "build_failures"):
            park(cfg, gap, f"Its fast suites failed {fails} times (the kill rule); the last: {why}.\n\n"
                           f"```\n{suites['tail'][-1500:]}\n```")
        else:
            fac.nack(why, count=False, after="1m")
        return 0
    fac.say("gap.built", built_at=time.time(), **record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
