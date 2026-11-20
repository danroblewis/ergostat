"""researcher: takes a research item at asked (a question, from the coordinator's `dev/bin/ask.py`, a
`research.asked` event, or a planner) and answers it. In a read-only clone of main, a session reads the code, the docs
and, where its session allows it, the web; its report, with sources, is written to run/research/<name>.md and its
summary said on the item (research.answered). A planner waiting on it is given the report."""

from __future__ import annotations

import re
import sys
import time

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import fac  # noqa: E402


def report(cfg: dict, item: dict) -> str:
    """An answered item's report, read only from run/research/ (anything else is refused: "")."""
    d = fac.run_dir(cfg, "research").resolve()
    p = (fac.MODEL / str(item["fields"].get("report") or "")).resolve()
    return p.read_text() if d in p.parents and p.is_file() else ""


def main() -> int:
    fac.stop_on_term()
    cfg = fac.config()
    item = fac.read_input()["item"]
    f = item["fields"]
    name = fac.slug(item["id"].split("/", 1)[1], 64)
    _, work = agents.clone(cfg, name, "researcher", at=f"origin/{cfg['git']['base']}")
    asked = {**item, "fields": {**f, "branch": name, "title": str(f.get("question") or "")}}
    text, context = brief.assemble(cfg, "researcher", asked, work, definition="", branch=name,
                                   question=str(f.get("question") or ""))
    context["brief"] = brief.save(cfg, "researcher", asked, text)
    got = fac.attempt(cfg, "researcher", text, work)
    if got is None:
        return 0
    said = str(got.get("result", ""))
    body = re.search(r"<report>\s*(.*?)</report>", said, re.S)
    if not body:
        raise RuntimeError("the researcher wrote no <report>")
    summary = re.search(r"<summary>\s*(.*?)</summary>", said, re.S)
    p = fac.run_dir(cfg, "research") / f"{name}.md"
    p.write_text(body[1].strip() + "\n")
    sources = re.findall(r"^- (.+)$", body[1].split("## Sources", 1)[-1] if "## Sources" in body[1] else "", re.M)
    fac.say("research.answered", report=fac.rel(p), summary=" ".join((summary[1] if summary else "").split())[:1000],
            sources=sources[:30], answered_at=time.time(), contexts=[context],
            ai_cost_usd=round(float(got.get("total_cost_usd") or 0), 4))
    return 0


if __name__ == "__main__":
    sys.exit(main())
