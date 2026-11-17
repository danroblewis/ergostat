"""The two built-in item kinds of the owner's intent (SPEC §5a): ``ergostat.decision`` (what was decided, its
reasons, the alternatives rejected, the owner's words) and ``ergostat.correction`` (what the owner corrected,
in their words, and the kind of work it applies to). Like ``ergostat.model-change``, present in every project
and never declared; their events are ``ergostat.decision.*`` and ``ergostat.correction.*``."""

from __future__ import annotations

import hashlib
import re

from ..spec.ir import CORRECTION, DECISION, ItemKind

KINDS = (DECISION, CORRECTION)

DECISION_STATES = ["proposed", "confirmed", "superseded", "dismissed"]
CORRECTION_STATES = ["proposed", "confirmed", "retired", "dismissed"]
STATES = {DECISION: DECISION_STATES, CORRECTION: CORRECTION_STATES}

# who may record each event: a proposal comes from anyone (a block, a person, the extractor); the rest are the
# owner's own acts, and ``repeated`` is ergostat's (a later correction found to say the same)
PROPOSED = {f"{DECISION}.proposed", f"{CORRECTION}.proposed"}
OWNERS = {f"{DECISION}.{s}" for s in ("confirmed", "dismissed", "superseded")} | \
    {f"{CORRECTION}.{s}" for s in ("confirmed", "dismissed", "retired")}

STOP = set("a an the and or but of to in on for with at by from is are be it this that we i you our my as so "
           "not no do does don't dont never always should must".split())


# how their events' data folds (SPEC §5a, fold rules): the owner's words and the evidence accumulate, one event at
# a time (a decision seen again in a later session adds its words, never replaces the first); the sets are sets
DECISION_FOLD = {"words": "append", "evidence": "append", "reasons": "union", "alternatives": "append",
                 "scope": "union", "supersedes": "union"}
CORRECTION_FOLD = {"words": "append", "evidence": "append", "kind_of_work": "union", "scope": "union",
                   "repeated_by": "append"}


def _kind(name: str, states: list[str], show: list[str], description: str, fold: dict[str, str]) -> ItemKind:
    on = {f"{name}.{s}": s for s in states}
    return ItemKind(name, f"{name}/*", list(states), on, show, {}, None, description, fold=dict(fold))


def decision_kind() -> ItemKind:
    return _kind(DECISION, DECISION_STATES, ["decision", "scope", "proposed_by"],
                 "what the owner decided, with their words, its reasons and the alternatives rejected: proposed (by "
                 "the extractor or a person), confirmed by the owner, superseded only with a reason (built in, SPEC §5a)",
                 DECISION_FOLD)


def correction_kind() -> ItemKind:
    return _kind(CORRECTION, CORRECTION_STATES, ["correction", "kind_of_work", "repeats"],
                 "a correction the owner gave, in their words, and the kind of work it applies to: proposed from the "
                 "record or a transcript, confirmed by the owner; a repeat is linked to the first (built in, SPEC §5a)",
                 CORRECTION_FOLD)


def builtin() -> dict[str, ItemKind]:
    return {DECISION: decision_kind(), CORRECTION: correction_kind()}


def words_of(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower())]


def slug(text: str, n: int = 6) -> str:
    """An id's tail from its sentence: its first content words and a short hash of all of it, so the same sentence
    always gives the same id and two different ones never share it."""
    ws = [w for w in words_of(text) if w not in STOP][:n] or ["untitled"]
    h = hashlib.sha1(" ".join(words_of(text)).encode()).hexdigest()[:4]
    return "-".join(ws)[:48].strip("-") + "-" + h


def item_id(kind: str, text: str) -> str:
    return f"{kind}/{slug(text)}"


def kind_of_id(id: str) -> str | None:
    head = (id or "").split("/", 1)[0]
    return head if head in KINDS else None
