"""simplifier (dev/model/code-health.yaml; docs/roadmap/overnight/code-health-simplifier.md): one area of the code
chosen by evidence (a program: the arithmetic), and a gap asked for whose definition names it and the rules of a
simplification (the AI part is the ordinary implementor who builds that gap). Pool 1: at most one simplification gap
that has not merged, parked or closed, fixed here and not read from config.

    simplify.py           the block: under run/simplify.lock, the open simplification gaps read again, and the pick
                          asked for as gap/simplify-<module>-<yyyymmdd> only when there are none
    simplify.py pick      the module it would pick, with the evidence that chose it (asks for nothing)
    simplify.py removals  on gap.merged: each `Removed:` trailer of a simplifier gap's merged commits a removal item
    simplify.py age | in-flight   the sensors: days since the last simplification gap was asked for; how many are open

Evidence that cannot be read (git, the coverage report, an in-flight gap's definition) means no pick, said and asked
for nothing."""

from __future__ import annotations

import fcntl
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

POOL = 1                                                   # the owner's: the factory starts small; never from config
DONE = {"merged", "parked", "closed"}
RECENT_DAYS = 30
CLASSES = {"dead", "duplicate", "over-general", "wrong-layer", "speculative"}
MODULE = re.compile(r"\b((?:ergostat|dev/bin|scripts)/[\w/.-]*)")
TRAILER = re.compile(r"^Removed:[ \t]*(.*?)\s*$", re.M)
EVIDENCE = fac.HERE.parent / "scripts" / "code_evidence.py"


class NoPick(RuntimeError):
    pass


def simplifier_gaps(gaps: list[dict]) -> list[dict]:
    return [g for g in gaps if g["fields"].get("source") == "simplifier"]


def in_flight(gaps: list[dict]) -> list[dict]:
    """Open simplification gaps: every state but merged, parked and closed (queued, in review and fix included)."""
    return [g for g in simplifier_gaps(gaps) if g["state"] not in DONE]


def coverage_file(cfg: dict) -> Path:
    """The coverage report to read: ``[code_health] coverage`` when a file is named, else main's latest report under
    run/coverage/ as measure.py chooses it (by seq, on main, not stale), its shares written to run/simplify-coverage.json.
    None, or one unreadable, is NoPick (lesson-3)."""
    if cfg["code_health"].get("coverage"):
        cov = Path(cfg["code_health"]["coverage"]).expanduser()
        return cov if cov.is_absolute() else fac.MODEL / cov
    import measure
    try:
        shares = measure.coverage_report(cfg)
    except SystemExit as e:
        raise NoPick(str(e)) from None
    p = fac.run_dir(cfg) / "simplify-coverage.json"
    p.write_text(json.dumps({m: {"share": s} for m, s in shares.items()}))
    return p


def evidence(cfg: dict) -> list[dict]:
    repo, cov = fac.path(cfg, "checkout"), coverage_file(cfg)
    r = subprocess.run([sys.executable, str(EVIDENCE), "--root", str(repo), "--ref", cfg["git"]["base"],
                        "--coverage", str(cov)], capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise NoPick(r.stderr.strip()[-400:] or f"code_evidence.py: exit {r.returncode}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def touched(cfg: dict, gaps: list[dict]) -> set[str]:
    """The module paths (or folders) named in the definitions of the gaps in flight. A gap that has a definition or a
    plan that cannot be read stops the pick; one not yet defined (open, sent back to the planner) names none yet."""
    import brief
    out: set[str] = set()
    for g in gaps:
        f = g["fields"]
        if g["state"] in DONE or not (f.get("definition") or f.get("plan")):
            continue
        if f.get("definition"):
            text = brief.definition_text(cfg, str(f["definition"]), fac.branch_of(g))
        else:
            p = (fac.MODEL / str(f["plan"])).resolve()
            text = p.read_text() if fac.run_dir(cfg, "plans").resolve() in p.parents and p.is_file() else ""
        if not text.strip():
            raise NoPick(f"{g['id']}'s definition cannot be read, so what it touches is not known")
        out |= {m.rstrip(".") for m in MODULE.findall(text)}
    return out


def score(cfg: dict, rows: list[dict]) -> list[tuple[float, dict]]:
    w = cfg["code_health"]
    sizes = sorted(r["lines"] for r in rows)
    p75 = max(sizes[min(len(sizes) - 1, int(0.75 * len(sizes)))], 1)
    return sorted(((float(w["size"]) * max(0.0, r["lines"] / p75 - 1) + float(w["churn"]) * r["churn"]
                    + float(w["duplicates"]) * len(r["duplicates"]) + float(w["dead"]) * len(r["dead_candidates"]), r)
                   for r in rows), key=lambda x: -x[0])


def choose(cfg: dict, gaps: list[dict], now: float) -> tuple[dict, float, dict]:
    """The best-scoring module not skipped: (its evidence, its score, why the others above it were passed over)."""
    rows = evidence(cfg)
    floor, busy = float(cfg["code_health"]["coverage_floor"]), touched(cfg, gaps)
    recent = {g["fields"].get("module") for g in simplifier_gaps(gaps)
              if now - float(g["fields"].get("requested_at") or now) < RECENT_DAYS * 86400}
    passed = {}
    for s, r in score(cfg, rows):
        m = r["module"]
        if s <= 0:
            break
        if r["coverage"] is None or r["coverage"] < floor:
            passed[m] = f"coverage {r['coverage']} under the floor {floor}"
        elif any(m == t or (t.endswith("/") and m.startswith(t)) for t in busy):
            passed[m] = "a gap in flight touches it"
        elif m in recent:
            passed[m] = f"picked in the last {RECENT_DAYS} days"
        else:
            return r, s, passed
    raise NoPick("no module scores above 0 that is covered, untouched and not picked lately"
                 + (f" (passed over: {json.dumps(passed)[:300]})" if passed else ""))


def name_of(cfg: dict, module: str, now: float) -> str:
    """simplify-<module-slug>-<yyyymmdd>: the date makes a later run of the same module a new item (lesson-5)."""
    repo = fac.path(cfg, "checkout").resolve()
    if repo not in (repo / module).resolve().parents:
        raise NoPick(f"{module!r} is not under the checkout")
    branch = f"simplify-{fac.slug(module.removesuffix('.py'), 45)}-{time.strftime('%Y%m%d', time.gmtime(now))}"
    if not fac.SAFE.match(branch):
        raise NoPick(f"{branch!r} is not a safe branch name")
    return branch


def definition(branch: str, module: str, s: float, row: dict) -> str:
    text = (fac.HERE / "prompts" / "simplify.md").read_text()
    for k, v in {"branch": branch, "module": module, "score": f"{s:.2f}",
                 "evidence": json.dumps(row, indent=2)}.items():
        text = text.replace("{" + k + "}", v)
    return text


def request(cfg: dict, now: float | None = None) -> int:
    """Pool 1, held: the lock is taken before the open gaps are read and given back after the request is written."""
    now = time.time() if now is None else now
    with open(fac.run_dir(cfg) / "simplify.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            gaps = fac.items("gap")
            if len(in_flight(gaps)) >= POOL:
                print(f"asked for nothing: {', '.join(g['id'] for g in in_flight(gaps))} is in flight (pool {POOL})")
                return 0
            try:
                row, s, passed = choose(cfg, gaps, now)
                branch = name_of(cfg, row["module"], now)
                p = fac.run_dir(cfg, "defs") / f"{branch}.md"
                if f"gap/{branch}" in {g["id"] for g in gaps} or p.exists():
                    raise NoPick(f"gap/{branch} (or its definition) exists already")
            except NoPick as e:
                print(f"no pick, asked for nothing: {e}")
                return 0
            p.write_text(definition(branch, row["module"], s, row))
            fac.add("gap.requested", f"gap/{branch}", title=f"simplify {row['module']}", source="simplifier",
                    branch=branch, depends_on=[], requested_at=now, definition=fac.rel(p), module=row["module"],
                    score=round(s, 3), evidence=row, passed_over=passed)
            print(f"gap/{branch} requested: {row['module']} (score {s:.2f})")
            return 0
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def removals(cfg: dict, given: dict) -> int:
    """One removal/<gap>-<n> per `Removed: <class> <path>[::<name>] <lines>` trailer of the merged commits (pre..main);
    a class off the allowlist, or a trailer that does not parse, is recorded as unclassified, never dropped."""
    ev = given.get("event") or {}
    gid, data = ev.get("item"), ev.get("data") or {}
    gap = json.loads(fac.ergostat("item", gid, "--json").stdout)
    if gap["fields"].get("source") != "simplifier":
        return 0
    if not (data.get("pre") and data.get("main_sha")):
        raise RuntimeError(f"{gid}'s gap.merged names no pre and main_sha")
    log = fac.git(fac.path(cfg, "checkout"), "log", "--topo-order", "--reverse", "--format=%B%x1e", f"{data['pre']}..{data['main_sha']}")
    branch = fac.branch_of(gap)
    for n, raw in enumerate((t for body in log.split("\x1e") for t in TRAILER.findall(body)), 1):
        m = re.fullmatch(r"(\S+)\s+([^\s:]+(?:::\S+)?)\s+(\d+)", raw)
        cls, where, lines = (m.groups() if m else ("", raw, "0"))
        path, _, name = where.partition("::")
        fac.say("removal.recorded", f"removal/{branch}-{n}", gap=gid, merge=data["main_sha"], path=path, name=name,
                lines=int(lines), trailer=raw, **{"class": cls if cls in CLASSES else "unclassified"})
    return 0


def main(argv: list[str]) -> int:
    cfg = fac.config()
    what = argv[0] if argv else "request"
    if what == "removals":
        return removals(cfg, json.loads(sys.stdin.read() or "{}"))
    if what not in ("request", "pick", "age", "in-flight"):
        raise SystemExit(__doc__)
    fac.cli(cfg)
    if what == "request":
        return request(cfg)
    gaps = fac.items("gap")
    if what == "in-flight":
        print(len(in_flight(gaps)))
    elif what == "age":
        last = max((float(g["fields"].get("requested_at") or 0) for g in simplifier_gaps(gaps)), default=0.0)
        print(round((time.time() - last) / 86400, 3) if last else 9999)
    else:
        try:
            row, s, passed = choose(cfg, gaps, time.time())
        except NoPick as e:
            print(f"no pick: {e}")
            return 1
        print(json.dumps({"module": row["module"], "score": round(s, 3), "evidence": row, "passed_over": passed},
                         indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
