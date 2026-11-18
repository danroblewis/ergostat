"""sail: on approval, the SAIL label (SAIL_LABEL) on the pull request."""

import github
from act import act
from step import Move
from tf import conf, key_of, now


def run(ticket):
    f = ticket["fields"]
    key, label = key_of(ticket), conf("SAIL_LABEL", "SAIL")
    act("github.label", key, "sail", f"Label #{f['pr']} {label}", github.add_label, f["repo"], f["pr"], label)
    return Move({"sailed_at": now()})
