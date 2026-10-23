"""Envelope comum de todo evento do barramento (igual ao do pp-service-template)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Producer(BaseModel):
    service: str
    version: str


class EventEnvelope(BaseModel):
    """Envelope padrão. `data` é o payload específico do evento."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    schema_version: str = "1.0"
    occurred_at: str = Field(default_factory=_now_iso)
    producer: Producer
    idempotency_key: str
    correlation_id: str | None = None
    data: dict[str, Any]


def make_envelope(
    event_type: str,
    idempotency_key: str,
    data: dict[str, Any],
    correlation_id: str | None = None,
) -> EventEnvelope:
    """Monta o envelope preenchendo o producer com a identidade do serviço central."""
    return EventEnvelope(
        event_type=event_type,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        producer=Producer(
            service=settings.service_name, version=settings.service_version
        ),
        data=data,
    )
