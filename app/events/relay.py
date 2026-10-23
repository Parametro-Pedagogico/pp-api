"""Relay da outbox: lê pendentes e publica no barramento, com retry por tentativa.

Rodar periodicamente (Cloud Run job/cron). Cada item usa a sua própria transação: publicar e
marcar como enviado, ou marcar como falho (incrementa attempts) sem derrubar o lote.
"""

from __future__ import annotations

from app.db.session import AsyncSessionLocal
from app.events import outbox
from app.events.publisher import publish


async def relay_once(batch: int = 100) -> int:
    """Publica as pendentes. Retorna quantas foram enviadas."""
    async with AsyncSessionLocal() as db:
        pending = await outbox.fetch_pending(db, limit=batch)

    sent = 0
    for row in pending:
        envelope = outbox.payload_to_envelope(row["payload"])
        async with AsyncSessionLocal() as db:
            try:
                publish(row["topic"], envelope)
                await outbox.mark_sent(db, row["id"])
                await db.commit()
                sent += 1
            except Exception as e:  # noqa: BLE001 - registra e segue para o próximo
                await outbox.mark_failed(db, row["id"], str(e))
                await db.commit()
    return sent
