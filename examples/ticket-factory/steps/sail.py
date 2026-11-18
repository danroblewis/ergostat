"""sail: on approval, the SAIL label (SAIL_LABEL) on the pull request."""

from gated import act
from step import Move
from tf import conf, now


def run(ticket):
    f = ticket["fields"]
    act("pr-label", repo=f["repo"], pr=f["pr"], label=conf("SAIL_LABEL", "SAIL"))
    return Move({"sailed_at": now()})
