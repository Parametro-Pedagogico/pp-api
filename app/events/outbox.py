"""Repositório da outbox: enfileirar (na transação) e ler/baixar pendentes (relay)."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.envelope import EventEnvelope
from app.v1._sql import execute, fetch_all


async def enqueue(db: AsyncSession, topic: str, envelope: EventEnvelope) -> None:
    """Grava a mensagem pendente. CHAMAR DENTRO da mesma transação da mudança de estado.

    Não faz commit: quem orquestra a transação é o chamador (a mudança e a outbox commitam juntas).
    """
    await execute(
        db,
        """
        INSERT INTO event_outbox (topic, event_type, idempotency_key, payload)
        VALUES (:topic, :event_type, :idempotency_key, CAST(:payload AS jsonb))
        """,
        {
            "topic": topic,
            "event_type": envelope.event_type,
            "idempotency_key": envelope.idempotency_key,
            "payload": envelope.model_dump_json(),
        },
    )


async def fetch_pending(db: AsyncSession, limit: int = 100) -> list[dict]:
    """Pendentes mais antigas primeiro (status pending ou failed)."""
    return await fetch_all(
        db,
        """
        SELECT id, topic, event_type, idempotency_key, payload, attempts
        FROM event_outbox
        WHERE status <> 'sent'
        ORDER BY created_at ASC
        LIMIT :limit
        """,
        {"limit": limit},
    )


async def mark_sent(db: AsyncSession, outbox_id: str) -> None:
    await execute(
        db,
        "UPDATE event_outbox SET status = 'sent', sent_at = now() WHERE id = CAST(:id AS uuid)",
        {"id": str(outbox_id)},
    )


async def mark_failed(db: AsyncSession, outbox_id: str, error: str) -> None:
    await execute(
        db,
        """
        UPDATE event_outbox
        SET status = 'failed', attempts = attempts + 1, last_error = :error
        WHERE id = CAST(:id AS uuid)
        """,
        {"id": str(outbox_id), "error": error[:2000]},
    )


def payload_to_envelope(payload: dict | str) -> EventEnvelope:
    """Reconstrói o envelope a partir do payload gravado (jsonb vem como dict)."""
    data = json.loads(payload) if isinstance(payload, str) else payload
    return EventEnvelope.model_validate(data)
