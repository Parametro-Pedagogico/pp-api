"""Decodificação de entrega por push do Pub/Sub.

Formato do push: {"message": {"data": "<base64>", "attributes": {...}, "messageId": "..."}}.
O corpo (data) é o envelope do evento em JSON.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from app.events.envelope import EventEnvelope


def decode_pubsub_push(body: dict[str, Any]) -> EventEnvelope:
    """Decodifica o corpo de um POST de assinatura push do Pub/Sub num EventEnvelope."""
    message = body.get("message") or {}
    data_b64 = message.get("data")
    if not data_b64:
        raise ValueError("push sem message.data")
    raw = base64.b64decode(data_b64)
    return EventEnvelope.model_validate(json.loads(raw))
