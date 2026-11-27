"""Events pushed to the running ergostat (docs/proposals/latency.md): one event or a batch in the output lines' envelope,
checked whole and recorded in one write; a webhook's payload made into events by its mapping; the token, carried as a
header, in the query, or as the secret of the sender's HMAC; only from this machine unless ``intake: allow:`` names
more; and ``POST /api/events`` on the page, recorded and folded at once."""

import hashlib
import hmac
import json
import textwrap
import urllib.error
import urllib.request

import pytest

from ergostat import model as mdl
from ergostat.intake import envelope, hooks
from ergostat.intake.config import parse
from ergostat.intake.token import allowed, carried, token
from ergostat.spec import items as its
from ergostat.store import Project
from tests.ports import free_port

MODEL = """
name: pushed
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [new, picked]
    events:
      ticket-found:
        when: type == 'ticket.found'
        '...': data
        state: set('new')
      ticket-picked:
        when: type == 'ticket.picked'
        '...': data
        state: set('picked')
      other:
        when: true
        '...': data
  pr:
    query: key.startswith('pr/')
    fields:
      state:
        type: one of [open, reviewed]
    events:
      pr-reviewed:
        when: type == 'pr.reviewed'
        '...': data
        state: set('reviewed')
      other:
        when: true
        '...': data
  alert:
    query: key.startswith('alert/')
    fields:
      state:
        type: one of [open, resolved]
    events:
      alert-triggered:
        when: type == 'alert.triggered'
        '...': data
        state: set('open')
      alert-resolved:
        when: type == 'alert.resolved'
        '...': data
        state: set('resolved')
      other:
        when: true
        '...': data
intake:
  hooks:
    jira:
      event: {from: webhookEvent, map: {"jira:issue_created": ticket.found}}
      item: "ticket/{issue.key}"
      id: "jira-{issue.id}-{timestamp}"
      data: {title: issue.fields.summary, labels: issue.fields.labels}
    github:
      event: {from: "header:X-GitHub-Event", map: {pull_request_review: pr.reviewed}}
      item: "pr/{repository.name}-{pull_request.number}"
      id: "{header:X-GitHub-Delivery}"
      data: {state: review.state, by: review.user.login, note: "review by {review.user.login}"}
    pagerduty:
      event: {from: event.event_type, map: {incident.triggered: alert.triggered, incident.resolved: alert.resolved}}
      item: "alert/{event.data.id}"
      id: "{event.id}"
      data: {title: event.data.title, urgency: event.data.urgency}
"""

JIRA = {"webhookEvent": "jira:issue_created", "timestamp": 1700000000000,
        "issue": {"id": "10023", "key": "SCRUM-12", "fields": {"summary": "Fix the login page", "labels": ["factory"]}}}
GITHUB = {"action": "submitted", "review": {"state": "approved", "user": {"login": "sam"}},
          "pull_request": {"number": 7}, "repository": {"name": "sample"}}
PAGERDUTY = {"event": {"id": "01ABC", "event_type": "incident.triggered",
                       "data": {"id": "PXYZ", "title": "disk full on db-1", "urgency": "high"}}}


def project(tmp_path, text: str = MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


# ---- the envelope


def test_one_event_or_a_batch_in_the_output_lines_envelope():
    assert envelope.parse(b'{"event": "ticket.found", "item": "ticket/1"}') == [{"event": "ticket.found", "item": "ticket/1"}]
    assert len(envelope.parse('[{"event": "a.b"}, {"type": "a.c"}]')) == 2
    assert len(envelope.parse({"events": [{"event": "a.b"}]})) == 1
    assert envelope.check({"type": "a.b", "data": {"x": 1}})["type"] == "a.b"


@pytest.mark.parametrize("bad, why", [
    (b"not json", "not JSON"),
    (b"[]", "an event"),
    (b"[1, 2]", "an event"),
    (b'{"event": "agent.ran"}', "not ergostat's own"),
    (b'{"event": "Ticket Found"}', "lowercase words"),
    (b'{"event": "a.b", "data": [1]}', "data: a JSON object"),
    (b'{"event": "a.b", "colour": "red"}', "unknown keys"),
    (b'{"event": "a.b", "patch": [{"op": "add", "path": "/x", "value": 1}]}', "name it"),
])
def test_a_push_that_is_not_events_is_refused(bad, why):
    with pytest.raises(envelope.Refused, match=why):
        for i, e in enumerate(envelope.parse(bad)):
            envelope.check(e, i)


def test_a_batch_is_refused_whole_and_recorded_in_one_write(tmp_path):
    p = project(tmp_path)
    with pytest.raises(envelope.Refused, match="event 1"):
        envelope.record(p, [{"event": "ticket.found", "item": "ticket/1"}, {"event": "loop.off"}])
    assert p.events.count() == 0
    got = envelope.record(p, [{"event": "ticket.found", "item": f"ticket/{i}", "data": {"n": i}} for i in range(5)])
    assert got["recorded"] == 5
    assert its.one(p.events, p.model.spec, "ticket/3").state == "new"
    assert {e["source"] for e in p.events.query(n=None)} == {"push"}


def test_a_retry_with_the_same_id_is_the_same_event(tmp_path):
    p = project(tmp_path)
    one = [{"event": "ticket.found", "item": "ticket/1", "id": "delivery-1"}]
    assert envelope.record(p, one)["recorded"] == 1
    assert envelope.record(p, one)["recorded"] == 0
    two = [{"event": "ticket.found", "item": "ticket/2", "id": "d-2"}, {"event": "ticket.found", "item": "ticket/3", "id": "d-3"}]
    assert envelope.record(p, two)["recorded"] == 2
    assert envelope.record(p, two)["recorded"] == 0
    assert p.events.count() == 3


# ---- the webhooks' mappings


def test_jira_github_and_pagerduty_payloads_become_events(tmp_path):
    spec = project(tmp_path).model.spec
    evs, left = hooks.events(spec.intake.hooks["jira"], JIRA)
    assert left == [] and evs == [{"event": "ticket.found", "source": "jira", "item": "ticket/SCRUM-12",
                                   "id": "jira-10023-1700000000000",
                                   "data": {"title": "Fix the login page", "labels": ["factory"]}}]
    evs, _ = hooks.events(spec.intake.hooks["github"], GITHUB,
                          {"X-GitHub-Event": "pull_request_review", "X-GitHub-Delivery": "abc-1"})
    assert evs[0]["event"] == "pr.reviewed" and evs[0]["item"] == "pr/sample-7" and evs[0]["id"] == "abc-1"
    assert evs[0]["data"] == {"state": "approved", "by": "sam", "note": "review by sam"}
    evs, _ = hooks.events(spec.intake.hooks["pagerduty"], PAGERDUTY)
    assert evs[0]["item"] == "alert/PXYZ" and evs[0]["data"]["urgency"] == "high"


def test_a_senders_event_the_mapping_leaves_out_is_ignored_and_a_missing_item_refused(tmp_path):
    spec = project(tmp_path).model.spec
    evs, left = hooks.events(spec.intake.hooks["jira"], {**JIRA, "webhookEvent": "comment_created"})
    assert evs == [] and "comment_created" in left[0]
    with pytest.raises(envelope.Refused, match="item"):
        hooks.events(spec.intake.hooks["jira"], {"webhookEvent": "jira:issue_created", "issue": {"id": "1"}})


def test_intake_as_written_is_checked(tmp_path):
    wrong: list[str] = []
    parse({"allow": ["10.0.0.0/8", "nowhere"], "bind": "here", "hooks": {"x": {"evnt": "a.b"}}, "colour": 1}, wrong)
    assert any("nowhere" in w for w in wrong) and any("bind" in w for w in wrong)
    assert any("evnt" in w for w in wrong) and any("colour" in w for w in wrong) and any("x.event" in w for w in wrong)
    (tmp_path / "ergostat.yaml").write_text("name: x\nintake: {allow: [nowhere]}\n")
    with pytest.raises(mdl.ModelError, match="intake.allow"):
        mdl.load(tmp_path)


# ---- the token, and who may push


def test_the_token_is_kept_in_the_state_directory_for_its_owner_only(tmp_path):
    t = token(tmp_path)
    assert t == token(tmp_path) and len(t) > 30
    assert (tmp_path / "intake.token").stat().st_mode & 0o077 == 0


def test_the_token_is_carried_as_a_header_in_the_query_or_as_the_hmac_secret():
    body = b'{"event": "a.b"}'
    sig = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert carried("s3cret", {"Authorization": "Bearer s3cret"}, {}, body)
    assert carried("s3cret", {"X-Ergostat-Token": "s3cret"}, {}, body)
    assert carried("s3cret", {}, {"token": ["s3cret"]}, body)
    assert carried("s3cret", {"X-Hub-Signature-256": f"sha256={sig}"}, {}, body)
    assert carried("s3cret", {"X-PagerDuty-Signature": f"v1=0000,v1={sig}"}, {}, body)
    assert not carried("s3cret", {"Authorization": "Bearer nope", "X-Hub-Signature-256": "sha256=00"}, {"token": ["x"]}, body)
    assert not carried("s3cret", {"X-Hub-Signature-256": f"sha256={sig}"}, {}, body + b" ")


def test_only_this_machine_pushes_unless_allow_names_more():
    assert allowed("127.0.0.1", []) and allowed("::1", []) and allowed("::ffff:127.0.0.1", [])
    assert not allowed("10.1.2.3", []) and allowed("10.1.2.3", ["10.0.0.0/8"]) and not allowed("192.168.1.1", ["10.0.0.0/8"])


# ---- POST /api/events and /api/hooks/NAME on the page


def _post(url: str, body: bytes, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


@pytest.fixture
def page(tmp_path):
    from ergostat.web import serve
    p = project(tmp_path)
    server, url = serve(p, free_port())
    yield p, url
    server.shutdown()
    server.server_close()


def test_events_pushed_to_the_page_are_recorded_and_folded_at_once(page):
    p, url = page
    t = (p.dir / "intake.token").read_text().strip()
    body = json.dumps([{"event": "ticket.found", "item": "ticket/9", "data": {"title": "x"}},
                       {"event": "ticket.picked", "item": "ticket/9"}]).encode()
    assert _post(f"{url}/api/events", body, {})[0] == 401
    assert _post(f"{url}/api/events", body, {"Authorization": "Bearer wrong"})[0] == 401
    code, got = _post(f"{url}/api/events", body, {"Authorization": f"Bearer {t}"})
    assert code == 200 and got["recorded"] == 2
    it = its.one(p.events, p.model.spec, "ticket/9")
    assert it.state == "picked" and it.fields["title"] == "x"
    assert _post(f"{url}/api/events", b'{"event": "loop.off"}', {"X-Ergostat-Token": t})[0] == 400


def test_a_webhook_signed_as_github_signs_it_is_recorded_once(page):
    p, url = page
    t = (p.dir / "intake.token").read_text().strip()
    body = json.dumps(GITHUB).encode()
    sig = "sha256=" + hmac.new(t.encode(), body, hashlib.sha256).hexdigest()
    hdr = {"X-GitHub-Event": "pull_request_review", "X-GitHub-Delivery": "d-77", "X-Hub-Signature-256": sig}
    code, got = _post(f"{url}/api/hooks/github", body, hdr)
    assert code == 200 and got["recorded"] == 1
    assert _post(f"{url}/api/hooks/github", body, hdr)[1]["recorded"] == 0            # delivered again: the same event
    assert its.one(p.events, p.model.spec, "pr/sample-7").state == "reviewed"
    code, got = _post(f"{url}/api/hooks/github", body, {**hdr, "X-GitHub-Event": "push"})
    assert code == 202 and got["recorded"] == 0
    assert _post(f"{url}/api/hooks/nobody?token={t}", b"{}", {})[0] == 404


def test_the_pages_own_writes_still_need_the_page(page):
    p, url = page
    t = (p.dir / "intake.token").read_text().strip()
    assert _post(f"{url}/api/message", b"{}", {"Authorization": f"Bearer {t}"})[0] == 403


def test_a_template_takes_part_of_a_value_by_a_regular_expression():
    got = hooks.fill("ticket/{pull_request.head.ref~^ergostat/([A-Z]+-[0-9]+)}",
                     {"pull_request": {"head": {"ref": "ergostat/SCRUM-12-fix-the-login"}}})
    assert got == "ticket/SCRUM-12"
    assert hooks.fill("x/{a~^([0-9]{2})}", {"a": "12345"}) == "x/12"
    assert hooks.fill("x/{a~^zz}", {"a": "12345"}) is None
