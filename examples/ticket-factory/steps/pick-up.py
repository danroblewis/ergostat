"""pick-up: the Jira issue to In Progress (JIRA_IN_PROGRESS), by whichever transition the project has."""

from gated import act
from step import Move
from tf import conf, key_of, now


def run(ticket):
    act("jira-transition", key=key_of(ticket), status=conf("JIRA_IN_PROGRESS"))
    return Move({"picked_at": now()})
