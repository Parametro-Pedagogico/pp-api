"""Publicação de replicação de dados mestres (central → satélites).

O central enfileira na outbox um snapshot do registro mestre; o relay entrega no tópico de
replicação. O satélite aplica de forma idempotente por `version` (ver o contrato de replicação e o
consumidor em pp-service-template/app/replication.py).

Uso (dentro da transação que alterou o dado):

    await publish_replication(db, "escolas", {"id": str(school_id), "version": v, ...})

`version` deve crescer a cada mudança do registro (ex.: epoch do updated_at, ou um contador).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.events.envelope import make_envelope
from app.events.outbox import enqueue


async def publish_replication(
    db: AsyncSession, collection: str, record: dict[str, Any]
) -> None:
    """Enfileira a replicação de um registro mestre. Exige `id` e `version` em `record`.

    Não faz commit: roda na transação do chamador, para o dado e o evento irem juntos.
    """
    if "id" not in record or "version" not in record:
        raise ValueError(
            "record precisa de 'id' e 'version' para replicação idempotente"
        )
    record_id = str(record["id"])
    version = int(record["version"])
    envelope = make_envelope(
        event_type=f"replicacao.{collection}",
        idempotency_key=f"{collection}:{record_id}:v{version}",
        data={"collection": collection, **record},
    )
    await enqueue(db, settings.pubsub_topic_replication, envelope)
