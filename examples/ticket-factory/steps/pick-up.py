"""pick-up: the Jira issue to In Progress (JIRA_IN_PROGRESS), by whichever transition the project has."""

import jira
from act import act
from step import Move
from tf import conf, key_of, now


def run(ticket):
    key = key_of(ticket)
    to = conf("JIRA_IN_PROGRESS")
    act("jira.transition", key, "pick-up", f"Move {key} to {to}", jira.transition, key, to)
    return Move({"picked_at": now()})
