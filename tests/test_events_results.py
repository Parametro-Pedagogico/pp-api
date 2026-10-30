"""Consumidor de resultado (F1.3): decode do push e validação (lógica pura)."""

import base64
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.events.envelope import make_envelope
from app.events.inbound import decode_pubsub_push
from app.events.oidc import verify_pubsub_push
from app.events.results_consumer import consolidate_result


def test_decode_pubsub_push_roundtrip():
    env = make_envelope(
        "resultado.aluno.v1", "prova:p:schedule:s:aluno:a:rev:1", {"aluno_id": "a"}
    )
    body = {
        "message": {"data": base64.b64encode(env.model_dump_json().encode()).decode()}
    }
    back = decode_pubsub_push(body)
    assert back.event_type == "resultado.aluno.v1"
    assert back.event_id == env.event_id
    assert back.data["aluno_id"] == "a"


def test_decode_rejects_missing_data():
    with pytest.raises(ValueError):
        decode_pubsub_push({"message": {}})


@pytest.mark.asyncio
async def test_consolidate_requires_business_key():
    # Faltando schedule_id/aluno_id: valida antes de tocar o banco (db=None).
    with pytest.raises(ValueError):
        await consolidate_result(None, {"prova_id": "p"})


@pytest.mark.asyncio
async def test_oidc_disabled_when_no_audience(monkeypatch):
    monkeypatch.setattr(settings, "pubsub_push_audience", "")
    # Sem audiência configurada, a validação é pulada (dev) — não levanta.
    await verify_pubsub_push(SimpleNamespace(headers={}))


@pytest.mark.asyncio
async def test_oidc_requires_token_when_enabled(monkeypatch):
    monkeypatch.setattr(
        settings, "pubsub_push_audience", "https://pp-api/v1/events/resultado"
    )
    with pytest.raises(HTTPException) as ei:
        await verify_pubsub_push(SimpleNamespace(headers={}))
    assert ei.value.status_code == 401
