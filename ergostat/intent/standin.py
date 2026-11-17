"""The intent judge's free stand-in (SPEC §12i): no model, no tokens; rules on words, for tests, examples and a first
look. It reads what the owner ruled out and looks for it in what the work brought in.

What the owner ruled out, from each thing the work is held to:

- a decision's **rejected alternatives**: the words of each option (``WebP``, ``a table per kind``);
- a **negated clause** in a decision, a correction, the owner's words for either, or a message: the words after
  ``never``, ``no``, ``not``, ``don't``, ``without``, ``stop``, ``instead of`` ... up to the end of the clause.

What the work brought in: the words of the lines its change **adds** that are new to it (in none of the files it
touches as they were, nor in the lines it removes), identifiers split at ``_`` and case (``image.resize`` gives
``image`` and ``resize``; ``image`` was there before, ``resize`` is new). A word the owner ruled out that the work
brought in is a contradiction, with the line as its evidence. Common words and words of two letters are never
terms. Nothing found: **met**, if the work has something to show (a change, or fields beyond its state); a work
with a done-when and nothing to show is **unmet**; a work held to nothing is **unjudged**. The stand-in never reads
what a done-when means: it says so, in its evidence."""

from __future__ import annotations

import re

NEGATION = re.compile(r"\b(?:never|no|not|don'?t|do not|without|stop|instead of|rather than|avoid|nor)\b\s+([^.;:!?\n()]+)",
                      re.I)
COMMON = set("""a an the and or but of to in on for with at by from is are be it its this that these those we i you our
my as so if then than when where what which who how all any each every some more most less many much few one two
new old use used using make makes made do does done get got set put go keep kept take let lets can could should would
must may might will shall need needs want wants work works way ways thing things also just only even still yet again
there here very own same other into out up down over under about after before while because what's it's isn't
file files code line lines value values data""".split())
RUN = re.compile(r"[A-Za-z0-9]+")
PLAIN = {"title", "idea", "by", "done_when", "done-when", "note", "reopened", "follows", "message", "missed"}   # what it was
# asked, not what it did
CAMEL = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+")


def terms_of(text: str) -> list[str]:
    """Content words, lower case, in order, without repeats."""
    out: list[str] = []
    for w in RUN.findall(text or ""):
        w = w.lower()
        if len(w) > 2 and w not in COMMON and not w.isdigit() and w not in out:
            out.append(w)
    return out


def ruled_out(x: dict) -> list[tuple[str, str]]:
    """(term, where it was ruled out) for one thing the work is held to."""
    out: list[tuple[str, str]] = []
    for a in x.get("rejected") or []:
        opt = str(a.get("option") or "")
        for t in terms_of(opt)[:3]:
            out.append((t, f"rejected: {opt}" + (f" ({a['why']})" if a.get("why") else "")))
    texts = [x.get("text") or "", *(x.get("words") or [])]
    for text in texts:
        for m in NEGATION.finditer(text):
            clause = m.group(1)
            for t in terms_of(clause)[:4]:
                out.append((t, f"{m.group(0).strip()[:160]}"))
    seen, uniq = set(), []
    for t, why in out:
        if t not in seen:
            seen.add(t)
            uniq.append((t, why))
    return uniq


def added(diff: str) -> list[tuple[str, int, str]]:
    """(file, line in the new version, text) of each line the diff adds."""
    out, path, n = [], None, 0
    for raw in (diff or "").splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else raw[4:]
            continue
        if raw.startswith("--- "):
            continue
        h = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", raw)
        if h:
            n = int(h.group(1))
            continue
        if raw.startswith("+"):
            out.append((path or "?", n, raw[1:]))
            n += 1
        elif raw.startswith(" "):
            n += 1
    return out


def removed_and_kept(diff: str) -> str:
    return "\n".join(r[1:] for r in (diff or "").splitlines() if (r.startswith("-") and not r.startswith("---")) or r.startswith(" "))


def words_in(text: str) -> set[str]:
    """Every word of it, lower case: whole (``WebP``: ``webp``) and in its camel-case pieces (``web``, ``p``)."""
    out = set()
    for w in RUN.findall(text or ""):
        out.add(w.lower())
        out.update(x.lower() for x in CAMEL.findall(w))
    return out


def judge(brief: dict) -> tuple[str, str, list[dict]]:
    """(verdict, why, evidence)."""
    against = brief["against"]
    work = brief["work"]
    if not against:
        return "unjudged", "nothing to hold it to: no done-when, and no confirmed decision, correction or message of the " \
            "owner's in its scope", []
    diff = brief.get("diff") or ""
    before = words_in(" ".join(brief.get("files", {}).values()) + "\n" + removed_and_kept(diff))
    lines = added(diff)
    found: list[dict] = []
    for x in against:
        if x["type"] == "done-when":
            continue
        for term, where in ruled_out(x):
            if term in before:
                continue                                   # the work found it there: it did not bring it in
            hit = next(((f, n, t) for f, n, t in lines if term in words_in(t)), None)
            if hit is None:
                fw = " ".join(str(v) for k, v in work["fields"].items() if k in ("title", "summary", "note", "says"))
                if term in words_in(fw):
                    found.append({"against": x["id"], "says": f"its own words say {term!r}, which the owner ruled out "
                                  f"({where})", "quote": term})
                continue
            f, n, t = hit
            found.append({"against": x["id"], "says": f"it brings in {term!r}, which the owner ruled out ({where})",
                          "at": f"{f}:{n}", "quote": t.strip()[:300]})
            break                                          # one line is evidence enough for one decision
    if found:
        named = sorted({e["against"] for e in found})
        return "contradicted", f"it does what {', '.join(named)} rules out: " + "; ".join(e["says"] for e in found)[:600], found
    has = bool(lines) or any(k not in PLAIN for k in work["fields"])
    held = [x["id"] for x in against]
    if work.get("done_when") and not has:
        return "unmet", "it has a done-when and nothing to show for it: no change, no fields of its own", \
            [{"against": "done-when", "says": "no change and no fields: nothing done"}]
    ev = [{"says": "nothing it brings in is what the owner ruled out", "held_to": held}]
    if work.get("done_when"):
        ev.append({"against": "done-when", "says": "the stand-in does not read what a done-when means: an AI judge does "
                   "(model: on the judge)"})
    return "met", f"held to {len(held)} ({', '.join(held[:4])}{', ...' if len(held) > 4 else ''}): nothing it brings in " \
        "is ruled out", ev
