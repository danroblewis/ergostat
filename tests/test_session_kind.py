"""An ai block's sessions are items without the model declaring a kind for them (the built-in session kind), and a
model that declares its own session kind keeps it."""
import textwrap

from ergostat import model as mdl
from ergostat.spec.ir import SESSION


def write(tmp_path, body):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(body))
    return mdl.load(tmp_path)


def test_a_model_gets_the_built_in_session_kind_with_its_transcript_shown_as_a_conversation(tmp_path):
    m = write(tmp_path, """
        name: t
        items:
          ticket: {id: ticket/*, states: [open, done]}
        blocks:
          dev:
            type: ai
            prompt: do it
            takes: {kind: ticket, at: open, to: [done]}
        """)
    k = m.spec.items[SESSION]
    assert k.matches("session/dev-12") and k.formats == {"transcript": "claude-session"}
    assert k.on["session.started"] == "running" and k.on["session.ran"] == "ran" and k.on["session.failed"] == "failed"
    assert {"model", "turns", "cost_usd"} <= set(k.show)


def test_a_declared_session_kind_is_kept_and_not_replaced(tmp_path):
    m = write(tmp_path, """
        name: t
        items:
          talk: {id: session/*, states: [open, closed], show: [model]}
        """)
    assert SESSION not in m.spec.items and m.spec.items["talk"].show == ["model"]
