"""Publicação no Pub/Sub. Isolado para o relay; desligado até a infra existir.

Enquanto `settings.events_publish_enabled` for False (padrão), publicar lança RuntimeError e o
relay não roda — a outbox apenas acumula com segurança. Ao provisionar os tópicos (ver
pp-api/docs/infra-gcp.md), ligar a flag.
"""

from __future__ import annotations

from app.core.config import settings
from app.events.envelope import EventEnvelope

try:  # SDK só é necessário em runtime com a flag ligada.
    from google.cloud import pubsub_v1
except Exception:  # pragma: no cover - ambiente sem o SDK
    pubsub_v1 = None  # type: ignore[assignment]

_publisher = None


def _client():
    global _publisher
    if _publisher is None:
        if pubsub_v1 is None:
            raise RuntimeError("google-cloud-pubsub não instalado")
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def publish(topic: str, envelope: EventEnvelope) -> str:
    """Publica um envelope e retorna o message_id. Levanta se a publicação estiver desligada."""
    if not settings.events_publish_enabled:
        raise RuntimeError(
            "events_publish_enabled=False: publicação desligada até provisionar o Pub/Sub"
        )
    if not settings.gcp_project:
        raise RuntimeError("GCP_PROJECT não configurado")
    client = _client()
    topic_path = client.topic_path(settings.gcp_project, topic)
    future = client.publish(
        topic_path,
        envelope.model_dump_json().encode("utf-8"),
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        idempotency_key=envelope.idempotency_key,
    )
    return future.result()
