"""Testes de lógica pura dos eventos (sem banco nem Pub/Sub)."""

from app.events.envelope import make_envelope
from app.events.outbox import payload_to_envelope


def test_envelope_has_producer_and_fields():
    env = make_envelope(
        event_type="replicacao.escolas",
        idempotency_key="escolas:e1:v3",
        data={"collection": "escolas", "id": "e1", "version": 3},
    )
    assert env.event_type == "replicacao.escolas"
    assert env.idempotency_key == "escolas:e1:v3"
    assert env.producer.service == "pp-api"
    assert env.event_id and env.occurred_at
    assert env.data["version"] == 3


def test_envelope_roundtrip_from_payload():
    env = make_envelope("replicacao.turmas", "turmas:t1:v1", {"id": "t1", "version": 1})
    # jsonb volta do banco como dict; o relay reconstrói o envelope.
    back = payload_to_envelope(env.model_dump())
    assert back.event_id == env.event_id
    assert back.idempotency_key == env.idempotency_key
    # e também a partir de string JSON.
    back2 = payload_to_envelope(env.model_dump_json())
    assert back2.event_id == env.event_id
