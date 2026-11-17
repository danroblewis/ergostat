"""The extractor's cheap stand-in: heuristics on the owner's turns, no model and no tokens, so tests and examples
run as the AI extractor would (the same event lines) and its precision can be compared with the AI's.

Each owner sentence is read alone. One that pushes back on what was just done ("no", "not like that", "again",
"why did you", "justify", "stop") is a correction of the assistant's turn before it; one that states a rule or a
choice ("we decided", "I want", "let's", "always", "never", "don't", "instead of", "must") is a decision. A
question is neither, unless it asks why something was done. The sentence is the owner's words, verbatim."""

from __future__ import annotations

import re

from .transcript import Turn

SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
CORRECTION = re.compile(r"^(no|nope|wrong)\b|\b(not like that|that'?s (wrong|not (it|right|what))|"
                        r"again[.!]?$|i (already )?(said|told you|asked)|why did you|you (forgot|missed|broke|didn'?t|ignored)|"
                        r"justify|stop (doing|adding|making)|you keep)\b", re.I)
DECISION = re.compile(r"\b(we (decided|agreed|'ll|will|should|need to|want|must)|let'?s|i want|i'?d (like|rather|prefer)|"
                      r"always|never|don'?t|do not|must|instead of|rather than|decided|the rule|should (be|not|never|always))\b",
                      re.I)
TOPICS = {                     # words in a sentence: the scope (and kind of work) they suggest
    "ui": ("page", "panel", "button", "ui", "screen", "diagram", "view", "layout", "chart", "css"),
    "git": ("commit", "merge", "push", "branch", "worktree", "rebase", "trailer"),
    "testing": ("test", "tests", "suite", "pytest", "playwright"),
    "docs": ("doc", "docs", "spec", "readme", "document", "wording", "words", "write"),
    "modelling": ("stock", "flow", "model", "loop", "goal", "equation", "sensor"),
    "review": ("review", "reviewer", "judge", "verify", "check"),
}
MIN, MAX = 15, 300


def topics(text: str) -> list[str]:
    ws = set(re.findall(r"[a-z]+", text.lower()))
    return [t for t, keys in TOPICS.items() if ws & set(keys)]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE.split(text) if s and s.strip()]


def _gist(text: str) -> str:
    s = sentences(text[-600:])
    return (s[-1] if s else "")[:200]


def read(turn: Turn, before: str, after: str) -> list[tuple[str, dict]]:
    """What one owner turn proposes: ``[(kind, data), ...]``, each with the sentence it rests on, verbatim."""
    out: list[tuple[str, dict]] = []
    seen: set[str] = set()
    ss = sentences(turn.text)
    for n, s in enumerate(ss):
        if not (MIN <= len(s) <= MAX) or s in seen:
            continue
        seen.add(s)
        question = s.endswith("?")
        words = [{"text": s, **turn.where()}]
        scope = topics(s)
        if CORRECTION.search(s) and before and (not question or re.search(r"why did you", s, re.I)):
            nxt = ss[n + 1] if n + 1 < len(ss) else ""      # "No, not like that. Do it this way.": what to do instead
            if nxt and DECISION.search(nxt) and not nxt.endswith("?") and len(s) + len(nxt) < MAX:
                s = f"{s} {nxt}"
                words = [{"text": s, **turn.where()}] if s in turn.text else words + [{"text": nxt, **turn.where()}]
                scope = topics(s)
            out.append(("correction", {"correction": s, "words": words, "corrects": _gist(before),
                                       "kind_of_work": scope or ["general"], "scope": scope, "confidence": 0.3,
                                       "source": {"type": "transcript", **turn.where()},
                                       "extractor": {"name": "standin"}}))
        elif DECISION.search(s) and not question:
            out.append(("decision", {"decision": s, "words": words, "scope": scope, "confidence": 0.3,
                                     "extractor": {"name": "standin"}}))
    return out
